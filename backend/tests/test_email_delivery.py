import json
import logging
import socketserver
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest

from app.platform.email_delivery import (
    EmailDeliveryError,
    EmailMessage,
    LogEmailSender,
    ScalewayEmailSettings,
    ScalewayTransactionalEmailClient,
    SenderIdentity,
    SmtpEmailSender,
    sender_from_environment,
)

MESSAGE = EmailMessage("person@example.test", "Hello", "Body text", "key-1")


class _TemHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict[str, Any]]] = []
    status: ClassVar[int] = 200

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        _TemHandler.requests.append(
            {"path": self.path, "token": self.headers["X-Auth-Token"], "body": body}
        )
        payload = (
            {"emails": [{"id": "tem-123"}]}
            if _TemHandler.status == 200
            else {"message": "secret provider detail"}
        )
        data = json.dumps(payload).encode()
        self.send_response(_TemHandler.status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return None


@pytest.fixture
def tem_server() -> Generator[str, None, None]:
    _TemHandler.requests = []
    _TemHandler.status = 200
    server = HTTPServer(("127.0.0.1", 0), _TemHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


def _settings(base_url: str, **overrides: str) -> ScalewayEmailSettings:
    values = {
        "secret_key": "scw-secret",
        "project_id": "project-1",
        "sender_email": "no-reply@example.test",
        "sender_name": "Shadow",
        "region": "fr-par",
        "api_base_url": base_url,
    }
    values.update(overrides)
    return ScalewayEmailSettings(**values)


def test_scaleway_client_posts_the_message_and_returns_the_provider_id(
    tem_server: str,
) -> None:
    provider_id = ScalewayTransactionalEmailClient(_settings(tem_server)).send(MESSAGE)

    assert provider_id == "tem-123"
    request = _TemHandler.requests[0]
    assert request["path"] == "/v1/fr-par/emails"
    assert request["token"] == "scw-secret"
    assert request["body"]["to"] == [{"email": "person@example.test"}]
    assert request["body"]["from"] == {
        "email": "no-reply@example.test",
        "name": "Shadow",
    }
    assert (
        request["body"]["subject"] == "Hello" and request["body"]["text"] == "Body text"
    )
    assert request["body"]["project_id"] == "project-1"
    assert request["body"]["additional_headers"] == [
        {"key": "Message-ID", "value": "<key-1@shadow>"}
    ]


def test_scaleway_errors_do_not_leak_the_response_body(tem_server: str) -> None:
    _TemHandler.status = 429
    client = ScalewayTransactionalEmailClient(_settings(tem_server))
    with pytest.raises(EmailDeliveryError, match="HTTP 429") as error:
        client.send(MESSAGE)
    assert "secret provider detail" not in str(error.value)


@pytest.mark.parametrize(
    ("status", "permanent"),
    [(400, True), (422, True), (408, False), (429, False), (503, False)],
)
def test_scaleway_client_errors_are_permanent_except_timeouts_and_rate_limits(
    tem_server: str, status: int, permanent: bool
) -> None:
    _TemHandler.status = status
    with pytest.raises(EmailDeliveryError) as error:
        ScalewayTransactionalEmailClient(_settings(tem_server)).send(MESSAGE)
    assert error.value.permanent is permanent


def test_scaleway_client_does_not_follow_redirects_with_the_token(
    tem_server: str,
) -> None:
    _TemHandler.status = 302
    with pytest.raises(EmailDeliveryError, match="HTTP 302"):
        ScalewayTransactionalEmailClient(_settings(tem_server)).send(MESSAGE)
    assert len(_TemHandler.requests) == 1


def test_scaleway_settings_do_not_show_the_secret_key() -> None:
    assert "scw-secret" not in repr(_settings("https://api.example.test"))


def test_scaleway_unreachable_provider_is_a_delivery_error() -> None:
    client = ScalewayTransactionalEmailClient(_settings("http://127.0.0.1:1/v1"))
    with pytest.raises(EmailDeliveryError):
        client.send(MESSAGE)


@pytest.mark.parametrize(
    "overrides",
    [
        {"secret_key": ""},
        {"project_id": ""},
        {"sender_email": ""},
        {"api_base_url": "http://api.example.test/v1"},
        {"api_base_url": "ftp://127.0.0.1/v1"},
    ],
)
def test_scaleway_client_refuses_unsafe_or_incomplete_settings(
    overrides: dict[str, str],
) -> None:
    with pytest.raises(RuntimeError):
        ScalewayTransactionalEmailClient(
            _settings("https://api.example.test", **overrides)
        )


class _SmtpHandler(socketserver.StreamRequestHandler):
    received: ClassVar[list[str]] = []

    def handle(self) -> None:
        self.wfile.write(b"220 test\r\n")
        data: list[str] = []
        in_data = False
        for raw in self.rfile:
            line = raw.decode().rstrip("\r\n")
            if in_data:
                if line == ".":
                    in_data = False
                    _SmtpHandler.received.append("\n".join(data))
                    self.wfile.write(b"250 queued\r\n")
                else:
                    data.append(line)
            elif line.upper().startswith("DATA"):
                in_data = True
                self.wfile.write(b"354 go\r\n")
            elif line.upper().startswith("QUIT"):
                self.wfile.write(b"221 bye\r\n")
                return
            elif line.upper().startswith("EHLO"):
                self.wfile.write(b"250 test\r\n")
            else:
                self.wfile.write(b"250 ok\r\n")


def test_smtp_sender_delivers_to_a_local_catcher() -> None:
    _SmtpHandler.received = []
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SmtpHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        sender = SmtpEmailSender("127.0.0.1", port, SenderIdentity("", "Shadow"))
        message_id = sender.send(MESSAGE)
        server.shutdown()
    assert message_id == "<key-1@shadow>"
    delivered = _SmtpHandler.received[0]
    assert "To: person@example.test" in delivered and "Subject: Hello" in delivered
    assert "From: Shadow <shadow@localhost>" in delivered


@pytest.mark.parametrize(
    "message",
    [
        EmailMessage("a@example.test\r\nBcc: x@example.test", "Hello", "Body", "k"),
        EmailMessage("a@example.test", "Hello\r\nBcc: x@example.test", "Body", "k"),
        EmailMessage("a@example.test, b@example.test", "Hello", "Body", "k"),
    ],
)
def test_smtp_sender_refuses_header_injection_and_several_recipients(
    message: EmailMessage,
) -> None:
    sender = SmtpEmailSender("127.0.0.1", 1, SenderIdentity("a@example.test", "Shadow"))
    with pytest.raises(EmailDeliveryError) as error:
        sender.send(message)
    assert error.value.permanent is True


def test_smtp_failure_is_a_delivery_error() -> None:
    sender = SmtpEmailSender("127.0.0.1", 1, SenderIdentity("a@example.test", "Shadow"))
    with pytest.raises(EmailDeliveryError):
        sender.send(MESSAGE)


def test_log_sender_records_neither_recipient_nor_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="shadow.email"):
        provider_id = LogEmailSender().send(MESSAGE)
    assert provider_id == "log:key-1"
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "key-1" in logged
    assert "person@example.test" not in logged and "Body text" not in logged


def test_backend_selection_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)
    assert isinstance(sender_from_environment(), LogEmailSender)
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    assert isinstance(sender_from_environment(), SmtpEmailSender)
    monkeypatch.setenv("EMAIL_BACKEND", "scaleway")
    for name in (
        "SCW_SECRET_KEY",
        "SCW_DEFAULT_PROJECT_ID",
        "SCW_TEM_DEFAULT_SENDER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="SCW_SECRET_KEY"):
        sender_from_environment()
    monkeypatch.setenv("SCW_SECRET_KEY", "k")
    monkeypatch.setenv("SCW_DEFAULT_PROJECT_ID", "p")
    monkeypatch.setenv("SCW_TEM_DEFAULT_SENDER_EMAIL", "a@example.test")
    assert isinstance(sender_from_environment(), ScalewayTransactionalEmailClient)
    monkeypatch.setenv("EMAIL_BACKEND", "carrier-pigeon")
    with pytest.raises(RuntimeError, match="EMAIL_BACKEND"):
        sender_from_environment()
