"""Versioned legal documents (ADR-0041): files in ``backend/legal/``, validated at start-up."""
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

KEYS = ("terms", "dpa", "privacy", "storage", "subprocessors", "switching", "security", "provider")
LOCALES = ("fi", "en")
STATUSES = ("draft", "published")
ACCEPTANCE_MODES = ("required", "notice", "none")
_FIELDS = ("title", "version", "effective_from", "status", "acceptance")
LEGAL_DIRECTORY = Path(__file__).resolve().parent.parent / "legal"
# Files in the directory that are not documents.
_OTHER_FILES = {"browser-storage.json", "README.md"}


class LegalDocumentError(Exception):
    """The set of legal documents is malformed; the backend must not start."""


@dataclass(frozen=True)
class LegalDocument:
    key: str
    locale: str
    title: str
    version: int
    effective_from: date
    status: str
    acceptance: str
    body: str

    @property
    def published(self) -> bool:
        return self.status == "published"


def _parse(path: Path, key: str, locale: str) -> LegalDocument:
    name = path.name
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    if match is None:
        raise LegalDocumentError(f"{name}: front matter between '---' lines is missing")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        field, separator, value = line.partition(":")
        field = field.strip()
        if not separator or field not in _FIELDS or field in fields:
            raise LegalDocumentError(f"{name}: unexpected or repeated front matter line {line!r}")
        fields[field] = value.strip()
    missing = [field for field in _FIELDS if not fields.get(field)]
    if missing:
        raise LegalDocumentError(f"{name}: front matter lacks {', '.join(missing)}")
    if not fields["version"].isdigit() or int(fields["version"]) < 1:
        raise LegalDocumentError(f"{name}: version must be a positive integer")
    try:
        effective_from = date.fromisoformat(fields["effective_from"])
    except ValueError as error:
        raise LegalDocumentError(f"{name}: effective_from must be a date (YYYY-MM-DD)") from error
    if fields["status"] not in STATUSES:
        raise LegalDocumentError(f"{name}: status must be one of {', '.join(STATUSES)}")
    if fields["acceptance"] not in ACCEPTANCE_MODES:
        raise LegalDocumentError(f"{name}: acceptance must be one of {', '.join(ACCEPTANCE_MODES)}")
    body = match.group(2).strip()
    if not body:
        raise LegalDocumentError(f"{name}: the text is empty")
    return LegalDocument(
        key=key,
        locale=locale,
        title=fields["title"],
        version=int(fields["version"]),
        effective_from=effective_from,
        status=fields["status"],
        acceptance=fields["acceptance"],
        body=body,
    )


class LegalLibrary:
    def __init__(self, documents: list[LegalDocument], *, show_drafts: bool) -> None:
        self._documents = {(document.key, document.locale): document for document in documents}
        self.show_drafts = show_drafts

    @classmethod
    def load(cls, directory: Path = LEGAL_DIRECTORY, *, show_drafts: bool = False) -> "LegalLibrary":
        if not directory.is_dir():
            raise LegalDocumentError(f"{directory}: the legal documents directory is missing")
        expected = {f"{key}.{locale}.md": (key, locale) for key in KEYS for locale in LOCALES}
        present = {path.name for path in directory.iterdir() if path.is_file()}
        for name in sorted(present - set(expected) - _OTHER_FILES):
            raise LegalDocumentError(f"{name}: not a legal document (keys: {', '.join(KEYS)}; locales: {', '.join(LOCALES)})")
        for name in sorted(set(expected) - present):
            raise LegalDocumentError(f"{name}: the file is missing")
        documents = [_parse(directory / name, *expected[name]) for name in sorted(expected)]
        by_key: dict[str, list[LegalDocument]] = {}
        for document in documents:
            by_key.setdefault(document.key, []).append(document)
        for key, pair in by_key.items():
            first = pair[0]
            for other in pair[1:]:
                for field in ("version", "effective_from", "status", "acceptance"):
                    if getattr(first, field) != getattr(other, field):
                        raise LegalDocumentError(f"{key}.{other.locale}.md: {field} differs from {key}.{first.locale}.md")
        return cls(documents, show_drafts=show_drafts)

    @classmethod
    def from_environment(cls) -> "LegalLibrary":
        return cls.load(LEGAL_DIRECTORY, show_drafts=os.getenv("LEGAL_SHOW_DRAFTS", "false").strip().lower() in {"1", "true", "yes"})

    def _readable(self, document: LegalDocument, signed_in: bool) -> bool:
        """Published texts are public; drafts only when enabled and the reader is signed in (the alpha's people)."""
        return document.published or (self.show_drafts and signed_in)

    def visible(self, locale: str, *, signed_in: bool = False) -> list[LegalDocument]:
        """Documents this reader may read, in the fixed key order."""
        return [
            document
            for key in KEYS
            if self._readable(document := self._documents[(key, locale)], signed_in)
        ]

    def published(self, locale: str) -> list[LegalDocument]:
        """Published documents only (what an Organization can accept or be told about), in key order."""
        return [document for key in KEYS if (document := self._documents[(key, locale)]).published]

    def get(self, key: str, locale: str, *, signed_in: bool = False) -> LegalDocument | None:
        document = self._documents.get((key, locale))
        if document is None or not self._readable(document, signed_in):
            return None
        return document

    def required(self) -> list[LegalDocument]:
        """Published documents an Owner must accept (English entry; metadata is the same in both locales)."""
        return [
            document
            for key in KEYS
            if (document := self._documents[(key, "en")]).published and document.acceptance == "required"
        ]
