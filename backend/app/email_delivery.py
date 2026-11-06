import os
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    text: str
    idempotency_key: str


class TransactionalEmailSender(Protocol):
    def send(self, message: EmailMessage) -> str: ...


@dataclass(frozen=True)
class ScalewayEmailSettings:
    secret_key: str
    project_id: str
    sender_email: str
    sender_name: str
    region: str = "fr-par"
    api_base_url: str = "https://api.scaleway.com/transactional-email/v1alpha1/regions"

    @classmethod
    def from_environment(cls) -> "ScalewayEmailSettings":
        return cls(
            secret_key=os.getenv("SCW_SECRET_KEY", ""),
            project_id=os.getenv("SCW_DEFAULT_PROJECT_ID", ""),
            sender_email=os.getenv("SCW_TEM_DEFAULT_SENDER_EMAIL", ""),
            sender_name=os.getenv("SCW_TEM_DEFAULT_SENDER_NAME", "Shadow"),
            region=os.getenv("SCW_TEM_REGION", "fr-par"),
            api_base_url=os.getenv(
                "SCW_TEM_API_BASE_URL",
                "https://api.scaleway.com/transactional-email/v1alpha1/regions",
            ),
        )


class ScalewayTransactionalEmailClient:
    def __init__(self, settings: ScalewayEmailSettings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(base_url=settings.api_base_url, timeout=15)

    def send(self, message: EmailMessage) -> str:
        if not all((self._settings.secret_key, self._settings.project_id, self._settings.sender_email)):
            raise RuntimeError("Scaleway transactional email is not configured")
        response = self._client.post(
            f"{self._settings.region}/emails",
            headers={"X-Auth-Token": self._settings.secret_key},
            json={
                "project_id": self._settings.project_id,
                "from": {
                    "email": self._settings.sender_email,
                    "name": self._settings.sender_name,
                },
                "to": [{"email": message.recipient}],
                "subject": message.subject,
                "text": message.text,
                "additional_headers": [
                    {"key": "Message-ID", "value": f"<{message.idempotency_key}@shadow>"}
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return str(data["emails"][0]["id"])
