from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.api.v1.users.models import hash_length_constraints, non_blank_constraints
from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")

# Migration 020 (TASK-074): one MCP resource with read, or read and write.
_SCOPE_CHECK = "scopes IN ('schatten.read', 'schatten.read schatten.write')"
_RESOURCE_CHECK = "resource LIKE '%/api/mcp'"


class McpOauthClient(Base):
    __tablename__ = "mcp_oauth_clients"
    __table_args__ = (
        UniqueConstraint("client_id", name="uq_mcp_oauth_clients_client_id"),
        *non_blank_constraints(
            "client_id",
            "ck_mcp_oauth_clients_client_id_non_blank",
        ),
        CheckConstraint(
            "length(client_name) BETWEEN 1 AND 100",
            name="ck_mcp_oauth_clients_client_name_length",
        ),
        CheckConstraint(
            "jsonb_typeof(redirect_uris) = 'array' "
            "AND jsonb_array_length(redirect_uris) BETWEEN 1 AND 10",
            name="ck_mcp_oauth_clients_redirect_uris",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "json_type(redirect_uris) = 'array' "
            "AND json_array_length(redirect_uris) BETWEEN 1 AND 10",
            name="ck_mcp_oauth_clients_redirect_uris_sqlite",
        ).ddl_if(dialect="sqlite"),
        *non_blank_constraints(
            "created_ip",
            "ck_mcp_oauth_clients_created_ip_non_blank",
        ),
    )

    mcp_oauth_client_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    client_id: Mapped[str] = mapped_column(Text)
    client_name: Mapped[str] = mapped_column(Text)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    created_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class McpOauthGrant(Base):
    __tablename__ = "mcp_oauth_grants"
    __table_args__ = (
        UniqueConstraint("grant_key", name="uq_mcp_oauth_grants_key"),
        *non_blank_constraints("grant_key", "ck_mcp_oauth_grants_key_non_blank"),
        CheckConstraint(_SCOPE_CHECK, name="ck_mcp_oauth_grants_scope"),
        CheckConstraint(
            _RESOURCE_CHECK,
            name="ck_mcp_oauth_grants_resource",
        ),
        CheckConstraint(
            "expires_time > created_time",
            name="ck_mcp_oauth_grants_expiry",
        ),
        CheckConstraint(
            "revoked_by IS NULL OR revoked_time IS NOT NULL",
            name="ck_mcp_oauth_grants_revocation_audit",
        ),
    )

    grant_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    grant_key: Mapped[str] = mapped_column(Text)
    mcp_oauth_client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mcp_oauth_clients.mcp_oauth_client_id", ondelete="RESTRICT"),
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    scopes: Mapped[str] = mapped_column(Text)
    resource: Mapped[str] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )


class McpOauthAuthorizationRequest(Base):
    __tablename__ = "mcp_oauth_authorization_requests"
    __table_args__ = (
        UniqueConstraint(
            "code_hash",
            name="uq_mcp_oauth_authorization_requests_code_hash",
        ),
        *hash_length_constraints(
            "request_id_hash",
            "ck_mcp_oauth_authorization_requests_id_hash_length",
        ),
        *hash_length_constraints(
            "code_hash",
            "ck_mcp_oauth_authorization_requests_code_hash_length",
        ),
        CheckConstraint(
            "length(redirect_uri) BETWEEN 1 AND 2048",
            name="ck_mcp_oauth_authorization_requests_redirect_uri",
        ),
        CheckConstraint(
            "code_challenge ~ '^[A-Za-z0-9_-]{43}$'",
            name="ck_mcp_oauth_authorization_requests_code_challenge",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "length(code_challenge) = 43",
            name="ck_mcp_oauth_authorization_requests_code_challenge_sqlite",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            _SCOPE_CHECK,
            name="ck_mcp_oauth_authorization_requests_scope",
        ),
        CheckConstraint(
            _RESOURCE_CHECK,
            name="ck_mcp_oauth_authorization_requests_resource",
        ),
        CheckConstraint(
            "expires_time > created_time",
            name="ck_mcp_oauth_authorization_requests_expiry",
        ),
        CheckConstraint(
            "(code_hash IS NULL) = (code_expires_time IS NULL) "
            "AND (code_hash IS NULL OR user_id IS NOT NULL)",
            name="ck_mcp_oauth_authorization_requests_code",
        ),
        CheckConstraint(
            "consumed_time IS NULL OR code_hash IS NOT NULL",
            name="ck_mcp_oauth_authorization_requests_consumed",
        ),
        CheckConstraint(
            "grant_id IS NULL OR consumed_time IS NOT NULL",
            name="ck_mcp_oauth_authorization_requests_grant",
        ),
    )

    request_id_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    mcp_oauth_client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mcp_oauth_clients.mcp_oauth_client_id", ondelete="RESTRICT"),
    )
    redirect_uri: Mapped[str] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text)
    resource: Mapped[str] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    code_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    code_expires_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    consumed_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    grant_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("mcp_oauth_grants.grant_id", ondelete="SET NULL"),
        nullable=True,
    )


class McpOauthToken(Base):
    __tablename__ = "mcp_oauth_tokens"
    __table_args__ = (
        *hash_length_constraints("token_hash", "ck_mcp_oauth_tokens_hash_length"),
        *hash_length_constraints(
            "replaced_by_hash",
            "ck_mcp_oauth_tokens_replaced_by_hash_length",
        ),
        CheckConstraint(
            "kind IN ('access', 'refresh')",
            name="ck_mcp_oauth_tokens_kind",
        ),
        CheckConstraint(
            "replaced_by_hash IS NULL OR kind = 'refresh'",
            name="ck_mcp_oauth_tokens_replacement_kind",
        ),
        CheckConstraint(
            "expires_time > created_time",
            name="ck_mcp_oauth_tokens_expiry",
        ),
    )

    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    grant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mcp_oauth_grants.grant_id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    replaced_by_hash: Mapped[bytes | None] = mapped_column(
        LargeBinary(32),
        nullable=True,
    )
    revoked_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


Index(
    "idx_mcp_oauth_clients_stale",
    func.coalesce(McpOauthClient.last_used_time, McpOauthClient.created_time),
    postgresql_where=McpOauthClient.deleted_time.is_(None),
    sqlite_where=McpOauthClient.deleted_time.is_(None),
)
Index(
    "idx_mcp_oauth_clients_deleted_time",
    McpOauthClient.deleted_time,
    postgresql_where=McpOauthClient.deleted_time.is_not(None),
    sqlite_where=McpOauthClient.deleted_time.is_not(None),
)
Index("idx_mcp_oauth_grants_user_id", McpOauthGrant.user_id)
Index(
    "idx_mcp_oauth_grants_client_user_resource",
    McpOauthGrant.mcp_oauth_client_id,
    McpOauthGrant.user_id,
    McpOauthGrant.resource,
)
Index("idx_mcp_oauth_grants_expires_time", McpOauthGrant.expires_time)
Index(
    "idx_mcp_oauth_grants_revoked_time",
    McpOauthGrant.revoked_time,
    postgresql_where=McpOauthGrant.revoked_time.is_not(None),
    sqlite_where=McpOauthGrant.revoked_time.is_not(None),
)
Index(
    "idx_mcp_oauth_authorization_requests_client",
    McpOauthAuthorizationRequest.mcp_oauth_client_id,
)
Index(
    "idx_mcp_oauth_authorization_requests_expires_time",
    McpOauthAuthorizationRequest.expires_time,
)
Index(
    "idx_mcp_oauth_authorization_requests_grant_id",
    McpOauthAuthorizationRequest.grant_id,
    postgresql_where=McpOauthAuthorizationRequest.grant_id.is_not(None),
    sqlite_where=McpOauthAuthorizationRequest.grant_id.is_not(None),
)
Index("idx_mcp_oauth_tokens_grant_id", McpOauthToken.grant_id)
Index(
    "idx_mcp_oauth_tokens_access_expires_time",
    McpOauthToken.expires_time,
    postgresql_where=McpOauthToken.kind == "access",
    sqlite_where=McpOauthToken.kind == "access",
)
