import os
from urllib.parse import urlparse
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from mcp.server.auth.provider import TokenVerifier
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, AuthSettings, Clock, OIDCClient, authenticate_session, utc_now
from app.auth_routes import (
    create_auth_router,
    create_authenticated_user_dependency,
)
from app.billing import (
    StripeBilling,
    StripeBillingClient,
    StripeSettings,
    StripeSignatureVerifier,
    StripeWebhookVerifier,
)
from app.database import (
    RequestContext,
    create_database_engine,
    create_session_factory,
    transaction_session,
)
from app.models import AccountClass
from app.legal_documents import LegalLibrary
from app.legal_routes import create_legal_router
from app.organization_legal_routes import create_organization_legal_router
from app.mcp_routes import create_mcp_router
from app.mcp_server.server import create_mcp_app
from app.mcp_server.settings import McpSettings
from app.oidc import AuthentikOIDCClient
from app.organization_context_routes import create_organization_context_router
from app.organization_routes import create_organization_router
from app.metamodel_routes import create_metamodel_router
from app.metric_io_routes import create_metric_io_router
from app.model_routes import create_model_router
from app.timeline_edit_routes import create_timeline_edit_router
from app.timeline_change_routes import create_timeline_change_router
from app.timeline_line_routes import create_timeline_line_router
from app.timeline_routes import create_timeline_router
from app.metric_routes import create_metric_router
from app.simulation_routes import create_simulation_router
from app.analysis_routes import create_analysis_router
from app.invitation_routes import create_invitation_router
from app.membership_routes import create_membership_router
from app.notification_routes import create_notification_router
from app.subscription_routes import create_subscription_router
from app.audit_routes import create_audit_router
from app.platform_routes import create_platform_router
from app.monitoring_routes import AuthentikProbe, create_monitoring_router
from app.support_access_routes import create_platform_support_access_router, create_support_access_router
from app.organization_deletion_routes import create_organization_deletion_router
from app.seat_capacity_routes import create_seat_capacity_router
from app.billing_routes import create_billing_router

PROJECT_NAME = os.getenv("PROJECT_NAME", "Shadow")
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:8173,http://127.0.0.1:8173",
    ).split(",")
    if origin.strip()
]
DEFAULT_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://shadow:shadow@localhost:8132/shadow",
)


def create_app(
    database_url: str = DEFAULT_DATABASE_URL,
    *,
    oidc_client: OIDCClient | None = None,
    clock: Clock = utc_now,
    auth_settings: AuthSettings | None = None,
    stripe_billing: StripeBilling | None = None,
    stripe_webhook_verifier: StripeWebhookVerifier | None = None,
    authentik_probe: AuthentikProbe | None = None,
    monitoring_token: str | None = None,
    mcp_settings: McpSettings | None = None,
    mcp_token_verifier: TokenVerifier | None = None,
    legal_library: LegalLibrary | None = None,
) -> FastAPI:
    engine = create_database_engine(database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        mcp_app = application.state.mcp_app
        if mcp_app is None:
            yield
        else:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        engine.dispose()

    application = FastAPI(title=PROJECT_NAME, lifespan=lifespan)
    application.state.database_engine = engine
    application.state.session_factory = create_session_factory(engine)
    resolved_mcp_settings = mcp_settings or McpSettings.from_environment()
    application.state.mcp_settings = resolved_mcp_settings
    application.state.mcp_app = (
        create_mcp_app(application.state.session_factory, resolved_mcp_settings, token_verifier=mcp_token_verifier)
        if resolved_mcp_settings.enabled
        else None
    )
    # A malformed legal text stops the start-up here (ADR-0041).
    application.state.legal_library = legal_library or LegalLibrary.from_environment()
    resolved_auth_settings = auth_settings or AuthSettings.from_environment()
    stripe_settings = StripeSettings.from_environment()
    resolved_stripe_billing = stripe_billing or StripeBillingClient(
        stripe_settings
    )
    authenticated_user_dependency = create_authenticated_user_dependency(
        session_factory=application.state.session_factory,
        clock=clock,
        settings=resolved_auth_settings,
    )
    platform_user_dependency = create_authenticated_user_dependency(
        session_factory=application.state.session_factory,
        clock=clock,
        settings=resolved_auth_settings,
        account_class=AccountClass.PLATFORM.value,
    )
    resolved_oidc_client = oidc_client or AuthentikOIDCClient.from_environment()

    trusted_origins = set(FRONTEND_ORIGINS)
    if public_api := os.getenv("PUBLIC_API_BASE_URL"):
        parsed = urlparse(public_api)
        trusted_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    @application.middleware("http")
    async def reject_cross_origin_writes(request: Request, call_next):
        """CSRF defense in depth beside SameSite=Lax cookies: a browser write must come from a trusted origin."""
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin is not None
            and origin not in trusted_origins
            and request.url.path != "/api/v1/billing/stripe/webhook"
        ):
            return JSONResponse(status_code=403, content={"detail": "cross-origin request refused"})
        return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # The browser reads the file name of an export and when to retry a refused one.
        expose_headers=["Content-Disposition", "Retry-After"],
    )
    application.include_router(
        create_auth_router(
            session_factory=application.state.session_factory,
            oidc_client=resolved_oidc_client,
            clock=clock,
            settings=resolved_auth_settings,
            authenticated_user_dependency=authenticated_user_dependency,
        )
    )
    application.include_router(
        create_organization_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
            stripe_billing=resolved_stripe_billing,
            stripe_webhook_verifier=(
                stripe_webhook_verifier
                or StripeSignatureVerifier(stripe_settings.webhook_secret)
            ),
            clock=clock,
            legal_library=application.state.legal_library,
        )
    )
    application.include_router(
        create_organization_context_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
        )
    )
    application.include_router(
        create_seat_capacity_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
            stripe_billing=resolved_stripe_billing,
            clock=clock,
        )
    )
    application.include_router(
        create_billing_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
            stripe_billing=resolved_stripe_billing,
        )
    )
    application.include_router(
        create_subscription_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
            stripe_billing=resolved_stripe_billing,
        )
    )
    application.include_router(
        create_invitation_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
            clock=clock,
        )
    )
    application.include_router(
        create_membership_router(
            session_factory=application.state.session_factory,
            authenticated_user_dependency=authenticated_user_dependency,
        )
    )
    application.include_router(create_model_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_metamodel_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_timeline_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency, clock=clock))
    application.include_router(create_timeline_change_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency, clock=clock))
    application.include_router(create_timeline_edit_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency, clock=clock))
    application.include_router(create_timeline_line_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency, clock=clock))
    application.include_router(create_metric_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_simulation_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_metric_io_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_analysis_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_notification_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_audit_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_platform_router(session_factory=application.state.session_factory, platform_user_dependency=platform_user_dependency, oidc_client=resolved_oidc_client, settings=resolved_auth_settings, clock=clock))
    application.include_router(create_support_access_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))
    application.include_router(create_platform_support_access_router(session_factory=application.state.session_factory, platform_user_dependency=platform_user_dependency))
    application.include_router(create_monitoring_router(session_factory=application.state.session_factory, authentik_probe=authentik_probe, token=monitoring_token))
    application.include_router(create_mcp_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency, settings=resolved_mcp_settings))
    def reader_is_signed_in(request: Request) -> bool:
        """Whether the request carries a live customer session (drafts are shown to those people only)."""
        with transaction_session(application.state.session_factory, RequestContext()) as session:
            try:
                authenticate_session(session, session_token=request.cookies.get(resolved_auth_settings.session_cookie_name), now=clock())
            except HTTPException:
                return False
        return True

    application.include_router(create_legal_router(library=application.state.legal_library, is_signed_in=reader_is_signed_in))
    application.include_router(create_organization_legal_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency, library=application.state.legal_library))
    application.include_router(create_organization_deletion_router(session_factory=application.state.session_factory, authenticated_user_dependency=authenticated_user_dependency))

    def get_session(request: Request) -> Iterator[Session]:
        with transaction_session(
            request.app.state.session_factory,
            RequestContext(),
        ) as session:
            yield session

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": PROJECT_NAME}

    @application.get("/api/v1/system/status")
    def system_status(
        session: Session = Depends(get_session),
        _authenticated_user: AuthenticatedUser = Depends(
            authenticated_user_dependency
        ),
    ) -> dict[str, str]:
        revision = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        return {
            "status": "ok",
            "database": "ready",
            "schema_revision": revision,
        }

    if application.state.mcp_app is not None:
        # Last, so that every application route keeps precedence; serves the MCP endpoint and its metadata.
        application.mount("/", application.state.mcp_app)

    return application


app = create_app()
