"""Shadow never calls a large language model itself (ADR-0047).

All agent and LLM use happens in the user's own harness through MCP. This test fails when
the backend gains an LLM SDK, a provider host, or an LLM key setting.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FORBIDDEN_PACKAGES = ("anthropic", "openai", "google-generativeai", "google-genai", "cohere", "mistralai", "litellm", "langchain")
FORBIDDEN_TEXT = (
    "api.anthropic.com",
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
    "api.cohere",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)


def _sources() -> list[Path]:
    return [path for path in (BACKEND / "app").rglob("*.py")]


def test_no_llm_sdk_in_requirements() -> None:
    for name in ("requirements.txt", "requirements-dev.txt"):
        text = (BACKEND / name).read_text().lower()
        for package in FORBIDDEN_PACKAGES:
            assert not re.search(rf"^{re.escape(package)}\b", text, re.MULTILINE), f"{name} lists {package}"


def test_backend_code_names_no_llm_provider() -> None:
    for path in _sources():
        text = path.read_text()
        for package in FORBIDDEN_PACKAGES:
            assert not re.search(rf"^\s*(import|from)\s+{re.escape(package.replace('-', '_'))}\b", text, re.MULTILINE), f"{path} imports {package}"
        for needle in FORBIDDEN_TEXT:
            assert needle not in text, f"{path} names {needle}"
