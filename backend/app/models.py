from datetime import date, datetime, time
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class QueueStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AccountClass(StrEnum):
    CUSTOMER = "customer"
    PLATFORM = "platform"


class SupportedLocale(StrEnum):
    ENGLISH = "en"
    FINNISH = "fi"


class OrganizationStatus(StrEnum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING_DELETION = "pending_deletion"
    PURGED = "purged"


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class SeatChangeKind(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"


class SeatChangeStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    SCHEDULED = "scheduled"
    APPLIED = "applied"
    FAILED = "failed"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class UserAccount(Base):
    __tablename__ = "user_accounts"
    __table_args__ = (
        UniqueConstraint(
            "oidc_issuer",
            "oidc_subject",
            name="uq_user_accounts_oidc_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    oidc_issuer: Mapped[str] = mapped_column(String(500))
    oidc_subject: Mapped[str] = mapped_column(String(255))
    account_class: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    locale: Mapped[str] = mapped_column(
        String(2),
        server_default=SupportedLocale.ENGLISH.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlatformRole(Base):
    __tablename__ = "platform_roles"
    __table_args__ = (UniqueConstraint("user_account_id", "role", name="uq_platform_roles_account_role"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_account_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30))


class SupportAccessRequest(Base):
    __tablename__ = "support_access_requests"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    requested_by_user_account_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("user_accounts.id"))
    case_reference: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    requested_hours: Mapped[int] = mapped_column(Integer, server_default="1")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_account_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OIDCLoginAttempt(Base):
    __tablename__ = "oidc_login_attempts"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    flow_token_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(128))
    code_verifier: Mapped[str] = mapped_column(String(128))
    return_to: Mapped[str] = mapped_column(String(500))
    audience: Mapped[str] = mapped_column(String(20), server_default="customer")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class PlatformEnrollment(Base):
    __tablename__ = "platform_enrollments"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(30)))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_account_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("user_accounts.id", ondelete="SET NULL"))


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_token_hint: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    time_zone: Mapped[str] = mapped_column(String(100))
    default_locale: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(30))
    created_by_user_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_accounts.id"),
        index=True,
    )
    billing_name: Mapped[str] = mapped_column(String(200))
    billing_email: Mapped[str] = mapped_column(String(320))
    purchased_seats: Mapped[int] = mapped_column(Integer)
    reserved_seats: Mapped[int] = mapped_column(Integer, server_default="0")
    seat_version: Mapped[int] = mapped_column(Integer, server_default="1")
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
    )
    subscription_access_state: Mapped[str] = mapped_column(String(30), server_default="active")
    grace_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(server_default="false")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_subscription_ids: Mapped[list[str]] = mapped_column(ARRAY(String(255)), server_default="{}")
    resubscribe_checkout_session_id: Mapped[str | None] = mapped_column(String(255))
    # MCP traffic for this Organization: its Owners and Admins can turn it off; the operator can block it.
    mcp_enabled: Mapped[bool] = mapped_column(server_default="true")
    mcp_platform_blocked: Mapped[bool] = mapped_column(server_default="false")
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_activation_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class OrganizationSeatChange(Base):
    __tablename__ = "organization_seat_changes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    requested_by_user_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_accounts.id"),
    )
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    from_quantity: Mapped[int] = mapped_column(Integer)
    target_quantity: Mapped[int] = mapped_column(Integer)
    stripe_reference: Mapped[str | None] = mapped_column(String(255))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationSeatPreview(Base):
    __tablename__ = "organization_seat_previews"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    seat_version: Mapped[int] = mapped_column(Integer)
    from_quantity: Mapped[int] = mapped_column(Integer)
    target_quantity: Mapped[int] = mapped_column(Integer)
    amount_due: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    proration_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    invited_by_user_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user_accounts.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by_user_account_id: Mapped[UUID | None] = mapped_column(Uuid)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_account_id",
            name="uq_organization_memberships_account",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    user_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
















class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(120))
    outcome: Mapped[str] = mapped_column(String(40))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = {"implicit_returning": False}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    actor_user_account_id: Mapped[UUID | None] = mapped_column(Uuid)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    support_access_id: Mapped[UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(120))
    target_id: Mapped[UUID] = mapped_column(Uuid)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    request_id: Mapped[str] = mapped_column(String(120))
    change_summary: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    topic: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=QueueStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    job_type: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=QueueStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)





















class LegalAcceptance(Base):
    """An Owner's acceptance of one version of a required legal document for an Organization (ADR-0041).

    Contract evidence: the e-mail address is a snapshot, and the Organization purge keeps the rows.
    """

    __tablename__ = "legal_acceptances"
    __table_args__ = (UniqueConstraint("organization_id", "document_key", "version", name="uq_legal_acceptances_version"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_account_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("user_accounts.id", ondelete="SET NULL"))
    accepted_by_email: Mapped[str] = mapped_column(String(320))
    document_key: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    locale: Mapped[str] = mapped_column(String(5))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    request_id: Mapped[str] = mapped_column(String(120))


class LegalAnnouncement(Base):
    """A published legal document version that Owners have been told about (once)."""

    __tablename__ = "legal_announcements"

    document_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """A short message to one Organization User; its text is built when it is read (ADR-0031)."""

    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"))
    recipient_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("user_accounts.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(60))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(Base):
    """One person's notification switches and Summary choice in one Organization."""

    __tablename__ = "notification_preferences"

    organization_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    summary_frequency: Mapped[str] = mapped_column(String(10), server_default="off")
    summary_yearclock_ids: Mapped[list[UUID] | None] = mapped_column(ARRAY(Uuid))
    summary_sent_on: Mapped[date | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TwinModel(Base):
    """A digital twin of one organisation, owned by an Organization (the paying account)."""

    __tablename__ = "models"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NodeType(Base):
    __tablename__ = "node_types"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(7))
    shape: Mapped[str] = mapped_column(String(20), server_default="rectangle")
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class ConnectionType(Base):
    __tablename__ = "connection_types"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(80))
    style: Mapped[str] = mapped_column(String(20), server_default="solid")
    source_end: Mapped[str] = mapped_column(String(20), server_default="none")
    target_end: Mapped[str] = mapped_column(String(20), server_default="arrow")
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class AllowedConnection(Base):
    __tablename__ = "allowed_connections"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    connection_type_id: Mapped[UUID] = mapped_column(Uuid)
    source_node_type_id: Mapped[UUID] = mapped_column(Uuid)
    target_node_type_id: Mapped[UUID] = mapped_column(Uuid)


class ModelVersion(Base):
    """The baseline of a Model or a version forked from another version; each holds a full graph."""

    __tablename__ = "model_versions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_baseline: Mapped[bool] = mapped_column(Boolean, server_default="false")
    base_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    origin_node_id: Mapped[UUID | None] = mapped_column(Uuid)
    node_type_id: Mapped[UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    x: Mapped[float] = mapped_column(Float, server_default="0")
    y: Mapped[float] = mapped_column(Float, server_default="0")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    connection_type_id: Mapped[UUID] = mapped_column(Uuid)
    source_node_id: Mapped[UUID] = mapped_column(Uuid)
    target_node_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Metric(Base):
    """A KPI of a Model version: monthly values, or a formula over other metrics by key."""

    __tablename__ = "metrics"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    node_id: Mapped[UUID | None] = mapped_column(Uuid)
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(20))
    formula: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetricValue(Base):
    __tablename__ = "metric_values"
    metric_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    period: Mapped[date] = mapped_column(Date, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    value: Mapped[float] = mapped_column(Float)


class Simulation(Base):
    """A forecast run of a Model version: method, horizon, what-if adjustments, and results."""

    __tablename__ = "simulations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    model_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    version_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(120))
    method: Mapped[str] = mapped_column(String(20))
    horizon_months: Mapped[int] = mapped_column(Integer)
    adjustments: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    skipped: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    history_end: Mapped[date | None] = mapped_column(Date)
    created_by_user_account_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimulationPoint(Base):
    __tablename__ = "simulation_points"
    simulation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    period: Mapped[date] = mapped_column(Date, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    value: Mapped[float] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)


class Recommendation(Base):
    """An action proposal derived from a simulation; people accept or dismiss it."""

    __tablename__ = "recommendations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    simulation_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))
    metric_key: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), server_default="proposed")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
