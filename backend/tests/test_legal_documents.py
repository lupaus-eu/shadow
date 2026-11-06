"""Legal documents: loader validation and the public endpoints (ADR-0041)."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.legal_documents import KEYS, LEGAL_DIRECTORY, LegalDocumentError, LegalLibrary
from app.main import create_app
from test_invitations import NOW, OIDC, login
from test_notifications import stack  # noqa: F401 - the fixture


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "legal"
    shutil.copytree(LEGAL_DIRECTORY, target)
    return target


def _publish(directory: Path, key: str, *, version: int = 1) -> None:
    for locale in ("fi", "en"):
        path = directory / f"{key}.{locale}.md"
        text = path.read_text(encoding="utf-8").replace("status: draft", "status: published")
        text = text.replace("version: 1", f"version: {version}")
        path.write_text(text, encoding="utf-8")


def test_the_shipped_set_is_valid_and_complete() -> None:
    library = LegalLibrary.load(show_drafts=True)
    assert [document.key for document in library.visible("en", signed_in=True)] == list(KEYS)
    assert [document.key for document in library.visible("fi", signed_in=True)] == list(KEYS)
    assert library.visible("en") == []  # drafts are not public


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: (d / "terms.fi.md").unlink(), "terms.fi.md: the file is missing"),
        (lambda d: (d / "extra.en.md").write_text("x"), "extra.en.md: not a legal document"),
        (lambda d: (d / "terms.en.md").write_text("no front matter"), "terms.en.md: front matter"),
        (lambda d: _replace(d / "terms.en.md", "version: 1", "version: 0"), "terms.en.md: version must be a positive integer"),
        (lambda d: _replace(d / "terms.en.md", "effective_from: 2026-12-01", "effective_from: tomorrow"), "terms.en.md: effective_from"),
        (lambda d: _replace(d / "terms.en.md", "status: draft", "status: final"), "terms.en.md: status must be one of"),
        (lambda d: _replace(d / "terms.en.md", "acceptance: required", "acceptance: maybe"), "terms.en.md: acceptance must be one of"),
        (lambda d: _replace(d / "terms.en.md", "version: 1", "version: 2"), "terms.fi.md: version differs from terms.en.md"),
        (lambda d: _replace(d / "terms.fi.md", "status: draft", "status: published"), "status differs"),
        (lambda d: _replace(d / "terms.en.md", "title: Terms of service\n", ""), "terms.en.md: front matter lacks title"),
        (lambda d: _replace(d / "terms.en.md", "version: 1\n", "version: 1\nversion: 2\n"), "terms.en.md: unexpected or repeated"),
    ],
)
def test_a_malformed_set_is_refused_with_the_file_name(tmp_path: Path, mutate, message: str) -> None:
    directory = _copy(tmp_path)
    mutate(directory)
    with pytest.raises(LegalDocumentError, match=message):
        LegalLibrary.load(directory)


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_the_backend_refuses_to_start_on_a_bad_set(database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _copy(tmp_path)
    (directory / "dpa.en.md").unlink()
    monkeypatch.setattr("app.legal_documents.LEGAL_DIRECTORY", directory)
    with pytest.raises(LegalDocumentError, match="dpa.en.md"):
        create_app(database_url=database_url)


def _client(database_url: str, library: LegalLibrary) -> TestClient:
    return TestClient(create_app(database_url=database_url, legal_library=library))


def test_drafts_are_hidden_unless_enabled_and_then_only_for_signed_in_people(database_url: str, tmp_path: Path, stack) -> None:
    directory = _copy(tmp_path)
    _publish(directory, "terms")
    # Drafts disabled: nobody sees them, signed in or not.
    off = create_app(database_url=database_url, legal_library=LegalLibrary.load(directory, show_drafts=False), oidc_client=OIDC("legal-off", "legal-off@example.com"), clock=lambda: NOW)
    with TestClient(off) as client:
        login(client)
        assert [item["key"] for item in client.get("/api/v1/legal/documents?locale=en").json()] == ["terms"]
        assert client.get("/api/v1/legal/documents/dpa?locale=en").status_code == 404
    # Drafts enabled: published texts stay public, drafts need a signed-in customer.
    on = create_app(database_url=database_url, legal_library=LegalLibrary.load(directory, show_drafts=True), oidc_client=OIDC("legal-on", "legal-on@example.com"), clock=lambda: NOW)
    with TestClient(on) as client:
        anonymous = client.get("/api/v1/legal/documents?locale=en")
        assert [item["key"] for item in anonymous.json()] == ["terms"]
        assert anonymous.headers["cache-control"] == "public, max-age=300" and anonymous.headers["vary"] == "Cookie"
        assert client.get("/api/v1/legal/documents/dpa?locale=en").status_code == 404
        assert client.get("/api/v1/legal/documents/terms?locale=fi").status_code == 200
        login(client)
        listing = client.get("/api/v1/legal/documents")
        assert len(listing.json()) == len(KEYS)
        assert listing.headers["cache-control"] == "private, no-store"
        draft = client.get("/api/v1/legal/documents/dpa?locale=en")
        assert draft.status_code == 200 and draft.headers["cache-control"] == "private, no-store"
        assert draft.json()["status"] == "draft" and "Draft for legal review" in draft.json()["body"]
        client.cookies.clear()
        assert client.get("/api/v1/legal/documents/dpa?locale=en").status_code == 404


def test_documents_are_public_in_both_locales_and_cacheable(database_url: str, tmp_path: Path) -> None:
    directory = _copy(tmp_path)
    for key in KEYS:
        _publish(directory, key)
    with _client(database_url, LegalLibrary.load(directory)) as client:
        english = client.get("/api/v1/legal/documents/terms?locale=en")
        finnish = client.get("/api/v1/legal/documents/terms?locale=fi")
        assert english.status_code == finnish.status_code == 200
        assert english.headers["cache-control"] == "public, max-age=300"
        assert english.json()["title"] == "Terms of service" and finnish.json()["title"] == "Palveluehdot"
        assert english.json()["version"] == 1 and english.json()["effective_from"] == "2026-12-01"
        assert english.json()["acceptance"] == "required"
        assert client.get("/api/v1/legal/documents").headers["cache-control"] == "public, max-age=300"
        assert client.get("/api/v1/legal/documents/unknown").status_code == 404
        assert client.get("/api/v1/legal/documents/terms?locale=sv").status_code == 422


def test_the_shipped_drafts_are_marked_draft_and_name_what_the_lawyer_must_fill() -> None:
    library = LegalLibrary.load(show_drafts=True)
    for locale in ("fi", "en"):
        for document in library.visible(locale, signed_in=True):
            if document.status == "draft":
                assert "TODO(lawyer)" in document.body, f"{document.key}.{locale}: a draft must mark what counsel has to decide"
                assert "not legal advice" in document.body.lower() or "ei ole oikeudellista neuvontaa" in document.body.lower()
