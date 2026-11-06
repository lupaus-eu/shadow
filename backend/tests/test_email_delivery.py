import json

import httpx

from app.email_delivery import (
    EmailMessage,
    ScalewayEmailSettings,
    ScalewayTransactionalEmailClient,
)


def test_scaleway_tem_settings_use_the_shared_scaleway_contract(monkeypatch) -> None:
    monkeypatch.setenv("SCW_SECRET_KEY", "secret-key")
    monkeypatch.setenv("SCW_DEFAULT_PROJECT_ID", "project-id")
    monkeypatch.setenv("SCW_TEM_DEFAULT_SENDER_EMAIL", "notifications@example.com")
    monkeypatch.setenv("SCW_TEM_DEFAULT_SENDER_NAME", "Yearclock")
    monkeypatch.setenv("SCW_TEM_REGION", "fr-par")
    monkeypatch.setenv(
        "SCW_TEM_API_BASE_URL",
        "https://tem.example.test/custom-tem-regions",
    )

    assert ScalewayEmailSettings.from_environment() == ScalewayEmailSettings(
        secret_key="secret-key",
        project_id="project-id",
        sender_email="notifications@example.com",
        sender_name="Yearclock",
        region="fr-par",
        api_base_url="https://tem.example.test/custom-tem-regions",
    )


def test_scaleway_tem_client_uses_the_configured_endpoint_and_response_shape() -> None:
    request_log: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        request_log.append(request)
        return httpx.Response(200, json={"emails": [{"id": "tem-email-id"}]})

    client = httpx.Client(
        base_url="https://tem.example.test/custom-tem-regions",
        transport=httpx.MockTransport(responder),
    )
    sender = ScalewayTransactionalEmailClient(
        ScalewayEmailSettings(
            secret_key="secret-key",
            project_id="project-id",
            sender_email="notifications@example.com",
            sender_name="Yearclock",
            region="fr-par",
            api_base_url="https://tem.example.test/custom-tem-regions",
        ),
        client=client,
    )

    provider_id = sender.send(
        EmailMessage("person@example.com", "Invitation", "Accept it", "invite-1")
    )

    assert provider_id == "tem-email-id"
    assert request_log[0].url == "https://tem.example.test/custom-tem-regions/fr-par/emails"
    assert request_log[0].headers["X-Auth-Token"] == "secret-key"
    assert json.loads(request_log[0].content) == {
        "project_id": "project-id",
        "from": {"email": "notifications@example.com", "name": "Yearclock"},
        "to": [{"email": "person@example.com"}],
        "subject": "Invitation",
        "text": "Accept it",
        "additional_headers": [{"key": "Message-ID", "value": "<invite-1@yearclock>"}],
    }
