"""Transactional email senders (ADR-019; from Yearclock ``email_delivery.py``, 6848e72).

``EMAIL_BACKEND`` picks the sender: ``scaleway`` (Scaleway Transactional Email,
production), ``smtp`` (a local SMTP catcher such as Mailpit, development only,
no TLS or login) or ``log`` (records only that a message was sent, never its
recipient or content). The Scaleway client uses the standard library, so the
platform adds no HTTP dependency.
"""

import json
import logging
import os
import re
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from typing import Any, Protocol
from urllib.parse import urlsplit

LOGGER = logging.getLogger("shadow.email")
SCALEWAY_API_BASE_URL = "https://api.scaleway.com/transactional-email/v1alpha1/regions"
REQUEST_TIMEOUT_SECONDS = 15


class EmailDeliveryError(Exception):
    """A message could not be handed to the provider; safe to log (no content).

    ``permanent`` means that retrying cannot help (a rejected address or sender).
    """

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """The API token must never follow a redirect to another host."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirects)


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    text: str
    idempotency_key: str


class TransactionalEmailSender(Protocol):
    def send(self, message: EmailMessage) -> str: ...


@dataclass(frozen=True)
class SenderIdentity:
    email: str
    name: str

    @classmethod
    def from_environment(cls) -> "SenderIdentity":
        return cls(
            email=os.getenv("SCW_TEM_DEFAULT_SENDER_EMAIL", ""),
            name=os.getenv("SCW_TEM_DEFAULT_SENDER_NAME", "Shadow"),
        )


class LogEmailSender:
    """Development fallback that sends nothing and logs no recipient or content."""

    def send(self, message: EmailMessage) -> str:
        LOGGER.info("email not sent (log backend): %s", message.idempotency_key)
        return f"log:{message.idempotency_key}"


class SmtpEmailSender:
    """Plain SMTP without TLS or login: for a local catcher such as Mailpit only."""

    def __init__(self, host: str, port: int, sender: SenderIdentity) -> None:
        self._host = host
        self._port = port
        self._sender = sender

    def send(self, message: EmailMessage) -> str:
        if re.search(r"[\s,;<>]", message.recipient):
            raise EmailDeliveryError(
                "recipient is not a single address", permanent=True
            )
        mime = MimeMessage()
        try:
            mime["From"] = (
                f"{self._sender.name} <{self._sender.email or 'shadow@localhost'}>"
            )
            mime["To"] = message.recipient
            mime["Subject"] = message.subject
            mime["Message-ID"] = f"<{message.idempotency_key}@shadow>"
            mime.set_content(message.text)
        except ValueError:
            raise EmailDeliveryError(
                "invalid message headers", permanent=True
            ) from None
        try:
            with smtplib.SMTP(
                self._host, self._port, timeout=REQUEST_TIMEOUT_SECONDS
            ) as smtp:
                smtp.send_message(mime)
        except (OSError, smtplib.SMTPException) as error:
            raise EmailDeliveryError(
                f"SMTP delivery failed: {type(error).__name__}"
            ) from None
        return mime["Message-ID"]


@dataclass(frozen=True)
class ScalewayEmailSettings:
    secret_key: str = field(repr=False)
    project_id: str
    sender_email: str
    sender_name: str
    region: str = "fr-par"
    api_base_url: str = SCALEWAY_API_BASE_URL

    @classmethod
    def from_environment(cls) -> "ScalewayEmailSettings":
        sender = SenderIdentity.from_environment()
        return cls(
            secret_key=os.getenv("SCW_SECRET_KEY", ""),
            project_id=os.getenv("SCW_DEFAULT_PROJECT_ID", ""),
            sender_email=sender.email,
            sender_name=sender.name,
            region=os.getenv("SCW_TEM_REGION", "fr-par"),
            api_base_url=os.getenv("SCW_TEM_API_BASE_URL", SCALEWAY_API_BASE_URL),
        )

    def validate(self) -> None:
        if not all((self.secret_key, self.project_id, self.sender_email)):
            raise RuntimeError(
                "Scaleway transactional email needs SCW_SECRET_KEY, "
                "SCW_DEFAULT_PROJECT_ID and SCW_TEM_DEFAULT_SENDER_EMAIL"
            )
        parts = urlsplit(self.api_base_url)
        loopback = parts.hostname in {"127.0.0.1", "localhost", "::1"}
        if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
            raise RuntimeError("SCW_TEM_API_BASE_URL must be https")


class ScalewayTransactionalEmailClient:
    def __init__(self, settings: ScalewayEmailSettings) -> None:
        settings.validate()
        self._settings = settings

    def send(self, message: EmailMessage) -> str:
        settings = self._settings
        body = json.dumps(
            {
                "project_id": settings.project_id,
                "from": {"email": settings.sender_email, "name": settings.sender_name},
                "to": [{"email": message.recipient}],
                "subject": message.subject,
                "text": message.text,
                "additional_headers": [
                    {
                        "key": "Message-ID",
                        "value": f"<{message.idempotency_key}@shadow>",
                    }
                ],
            }
        ).encode()
        request = urllib.request.Request(
            f"{settings.api_base_url.rstrip('/')}/{settings.region}/emails",
            data=body,
            method="POST",
            headers={
                "X-Auth-Token": settings.secret_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read())
            return str(data["emails"][0]["id"])
        except urllib.error.HTTPError as error:
            # A client error other than "timeout" or "too many requests" will not
            # succeed on a retry (rejected address or sender).
            permanent = 400 <= error.code < 500 and error.code not in {408, 429}
            raise EmailDeliveryError(
                f"Scaleway answered HTTP {error.code}", permanent=permanent
            ) from None
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            raise EmailDeliveryError(
                f"Scaleway delivery failed: {type(error).__name__}"
            ) from None


def sender_from_environment() -> TransactionalEmailSender:
    backend = os.getenv("EMAIL_BACKEND", "log")
    if backend == "scaleway":
        return ScalewayTransactionalEmailClient(
            ScalewayEmailSettings.from_environment()
        )
    if backend == "smtp":
        return SmtpEmailSender(
            os.getenv("SMTP_HOST", "localhost"),
            int(os.getenv("SMTP_PORT", "1025")),
            SenderIdentity.from_environment(),
        )
    if backend == "log":
        return LogEmailSender()
    raise RuntimeError(f"EMAIL_BACKEND must be scaleway, smtp or log, got {backend!r}")
