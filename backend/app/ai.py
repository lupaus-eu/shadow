"""The language model behind AI-assisted analysis.

Only the Anthropic Messages API is spoken, over httpx (no SDK). The client exists only when the
operator sets ``ANTHROPIC_API_KEY``; without it the AI analysis is switched off. What is sent is
the findings of one simulation: metric keys, names, units and forecast figures.
"""

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

DEFAULT_MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"


class AIError(RuntimeError):
    """The model could not be reached or answered with something unusable."""


class AIClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


@dataclass(frozen=True)
class AISettings:
    api_key: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 2000
    timeout_seconds: float = 60.0

    @classmethod
    def from_environment(cls) -> "AISettings":
        return cls(api_key=os.getenv("ANTHROPIC_API_KEY", ""), model=os.getenv("SHADOW_AI_MODEL", "") or DEFAULT_MODEL)


class AnthropicClient:
    def __init__(self, settings: AISettings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.timeout_seconds)

    def complete(self, system: str, prompt: str) -> str:
        try:
            response = self._client.post(
                API_URL,
                headers={"x-api-key": self._settings.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self._settings.model, "max_tokens": self._settings.max_tokens, "system": system, "messages": [{"role": "user", "content": prompt}]},
            )
            response.raise_for_status()
            blocks = response.json()["content"]
            return "".join(block["text"] for block in blocks if block.get("type") == "text")
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise AIError("the language model request failed") from error


def ai_client_from_environment() -> AIClient | None:
    settings = AISettings.from_environment()
    return AnthropicClient(settings) if settings.api_key else None
