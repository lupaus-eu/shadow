from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.legal_documents import KEYS, LegalDocument, LegalLibrary

PUBLIC_CACHE = "public, max-age=300"
# What a signed-in reader gets may include drafts, so no shared cache may keep it.
SIGNED_IN_CACHE = "private, no-store"


class LegalDocumentSummary(BaseModel):
    key: str
    title: str
    version: int
    effective_from: str
    status: Literal["draft", "published"]
    acceptance: Literal["required", "notice", "none"]


class LegalDocumentResponse(LegalDocumentSummary):
    body: str


def _summary(document: LegalDocument) -> dict:
    return {
        "key": document.key,
        "title": document.title,
        "version": document.version,
        "effective_from": document.effective_from.isoformat(),
        "status": document.status,
        "acceptance": document.acceptance,
    }


def create_legal_router(*, library: LegalLibrary, is_signed_in: Callable[[Request], bool] = lambda request: False) -> APIRouter:
    router = APIRouter(prefix="/api/v1/legal", tags=["legal documents"])

    @router.get("/documents", response_model=list[LegalDocumentSummary])
    def list_documents(request: Request, response: Response, locale: Literal["fi", "en"] = "en") -> list[dict]:
        signed_in = library.show_drafts and is_signed_in(request)
        response.headers["Cache-Control"] = SIGNED_IN_CACHE if signed_in else PUBLIC_CACHE
        response.headers["Vary"] = "Cookie"
        return [_summary(document) for document in library.visible(locale, signed_in=signed_in)]

    @router.get("/documents/{key}", response_model=LegalDocumentResponse)
    def get_document(key: str, request: Request, response: Response, locale: Literal["fi", "en"] = "en") -> dict:
        signed_in = library.show_drafts and is_signed_in(request)
        document = library.get(key, locale, signed_in=signed_in) if key in KEYS else None
        if document is None:
            raise HTTPException(status_code=404, detail="document not found")
        response.headers["Cache-Control"] = SIGNED_IN_CACHE if signed_in else PUBLIC_CACHE
        response.headers["Vary"] = "Cookie"
        return {**_summary(document), "body": document.body}

    return router
