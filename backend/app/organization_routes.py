from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.billing import (
    CheckoutRequest,
    StripeBilling,
    StripeWebhookVerifier,
)
from app.database import RequestContext, apply_request_context, transaction_session
from app.legal_acceptance import record_acceptance, require_acceptances
from app.legal_documents import LegalLibrary
from app.models import Organization, SupportedLocale
from app.organization_activation import (
    InitialContent,
    create_pending_organization,
    find_signup_for_creator,
    initial_content,
    process_checkout_event,
)


class AcceptedDocument(BaseModel):
    document_key: str = Field(min_length=1, max_length=40)
    version: int = Field(ge=1)
    locale: SupportedLocale | None = None


class OrganizationSignupRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    time_zone: str = Field(min_length=1, max_length=100)
    default_locale: SupportedLocale
    billing_name: str = Field(min_length=1, max_length=200)
    billing_email: str = Field(min_length=3, max_length=320)
    initial_seats: int = Field(ge=1, le=10_000)
    accepted_documents: list[AcceptedDocument] = Field(default_factory=list, max_length=20)

    @field_validator("organization_name", "billing_name")
    @classmethod
    def names_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("billing_email")
    @classmethod
    def email_must_have_an_address_shape(cls, value: str) -> str:
        stripped = value.strip()
        if "@" not in stripped or stripped.startswith("@") or stripped.endswith("@"):
            raise ValueError("invalid billing email")
        return stripped

    @field_validator("time_zone")
    @classmethod
    def time_zone_must_be_iana(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("unknown IANA time zone") from error
        return value


class InitialContentResponse(BaseModel):
    owner_user_account_id: UUID


class OrganizationSignupResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    status: str
    initial_seats: int
    expires_at: datetime
    checkout_url: str | None
    initial_content: InitialContentResponse | None


class StripeWebhookResponse(BaseModel):
    received: bool = True
    processed: bool
    duplicate: bool
    outcome: str


def create_organization_router(
    *,
    session_factory: sessionmaker[Session],
    authenticated_user_dependency: AuthenticatedUserDependency,
    stripe_billing: StripeBilling,
    stripe_webhook_verifier: StripeWebhookVerifier,
    clock: Callable[[], datetime],
    legal_library: LegalLibrary | None = None,
) -> APIRouter:
    library = legal_library or LegalLibrary.from_environment()
    router = APIRouter(tags=["organization activation"])

    @router.post(
        "/api/v1/organization-signups",
        response_model=OrganizationSignupResponse,
        status_code=201,
    )
    def create_signup(
        signup: OrganizationSignupRequest,
        request: Request,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> OrganizationSignupResponse:
        now = clock()
        # Before anything is created: every published required document must be accepted at its current version.
        to_record = require_acceptances(library, signup.accepted_documents)
        with transaction_session(
            session_factory,
            RequestContext(user_account_id=authenticated_user.account.id),
        ) as session:
            organization = create_pending_organization(
                session,
                user_account_id=authenticated_user.account.id,
                name=signup.organization_name,
                time_zone=signup.time_zone,
                default_locale=signup.default_locale.value,
                billing_name=signup.billing_name,
                billing_email=signup.billing_email,
                initial_seats=signup.initial_seats,
                now=now,
                request_id=_request_id(request),
            )
            for document in to_record:
                record_acceptance(
                    session,
                    organization_id=organization.id,
                    user=authenticated_user.account,
                    document=document,
                    locale=(next((item.locale for item in signup.accepted_documents if item.document_key == document.key), None) or signup.default_locale).value,
                    request_id=_request_id(request),
                    audit=False,
                )
            checkout = stripe_billing.create_subscription_checkout(
                CheckoutRequest(
                    organization_id=str(organization.id),
                    organization_name=organization.name,
                    billing_email=organization.billing_email,
                    seats=organization.purchased_seats,
                    locale=organization.default_locale,
                    expires_at=organization.pending_activation_expires_at,
                )
            )
            organization.stripe_checkout_session_id = checkout.id
            return _response(
                organization,
                checkout_url=checkout.url,
                content=None,
            )

    @router.get(
        "/api/v1/organization-signups/{organization_id}",
        response_model=OrganizationSignupResponse,
    )
    def signup_status(
        organization_id: UUID,
        authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> OrganizationSignupResponse:
        with transaction_session(
            session_factory,
            RequestContext(user_account_id=authenticated_user.account.id),
        ) as session:
            organization = find_signup_for_creator(
                session,
                organization_id=organization_id,
                user_account_id=authenticated_user.account.id,
                now=clock(),
            )
            if organization.status == "active":
                apply_request_context(
                    session,
                    RequestContext(
                        user_account_id=authenticated_user.account.id,
                        organization_id=organization.id,
                    ),
                )
            return _response(
                organization,
                checkout_url=None,
                content=initial_content(session, organization),
            )

    @router.post(
        "/api/v1/billing/stripe/webhook",
        response_model=StripeWebhookResponse,
    )
    async def stripe_webhook(request: Request) -> StripeWebhookResponse:
        event = stripe_webhook_verifier.verify(
            await request.body(),
            request.headers.get("Stripe-Signature"),
        )
        organization_id = _optional_uuid(event.organization_id)
        with transaction_session(
            session_factory,
            RequestContext(organization_id=organization_id),
        ) as session:
            outcome = process_checkout_event(
                session,
                event=event,
                now=clock(),
                request_id=_request_id(request),
            )
            return StripeWebhookResponse(
                processed=outcome.processed,
                duplicate=outcome.duplicate,
                outcome=outcome.outcome,
            )

    return router


def _response(
    organization: Organization,
    *,
    checkout_url: str | None,
    content: InitialContent | None,
) -> OrganizationSignupResponse:
    return OrganizationSignupResponse(
        organization_id=organization.id,
        organization_name=organization.name,
        status=organization.status,
        initial_seats=organization.purchased_seats,
        expires_at=organization.pending_activation_expires_at,
        checkout_url=checkout_url,
        initial_content=(
            InitialContentResponse(
                owner_user_account_id=content.owner_user_account_id,
            )
            if content
            else None
        ),
    )


def _request_id(request: Request) -> str:
    return (request.headers.get("X-Request-ID") or str(uuid4()))[:120]


def _optional_uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except ValueError:
        return None
