from datetime import datetime

from sqlalchemy import (
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

from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


def non_blank_constraints(
    column_name: str,
    constraint_name: str,
) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"{column_name} ~ '[^[:space:]]'",
            name=constraint_name,
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            f"length(trim({column_name}, "
            "char(9) || char(10) || char(11) || char(12) || char(13) || ' ')) > 0",
            name=f"{constraint_name}_sqlite",
        ).ddl_if(dialect="sqlite"),
    )


def hash_length_constraints(
    column_name: str,
    constraint_name: str,
) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            f"octet_length({column_name}) = 32",
            name=constraint_name,
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            f"length({column_name}) = 32",
            name=f"{constraint_name}_sqlite",
        ).ddl_if(dialect="sqlite"),
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('consultant', 'admin')", name="ck_users_role"),
        *non_blank_constraints("email", "ck_users_email_non_blank"),
    )

    user_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    modified_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    modified_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deleted_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        *non_blank_constraints("issuer", "ck_user_identities_issuer_non_blank"),
        *non_blank_constraints("subject", "ck_user_identities_subject_non_blank"),
        CheckConstraint(
            "last_login_time >= created_time",
            name="ck_user_identities_login_time",
        ),
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_user_identities_issuer_subject",
        ),
        UniqueConstraint(
            "user_id",
            "issuer",
            name="uq_user_identities_user_issuer",
        ),
    )

    user_identity_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
    )
    issuer: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_login_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class OidcLoginTransaction(Base):
    __tablename__ = "oidc_login_transactions"
    __table_args__ = (
        *hash_length_constraints(
            "state_hash",
            "ck_oidc_login_transactions_state_hash_length",
        ),
        *hash_length_constraints(
            "browser_binding_hash",
            "ck_oidc_login_transactions_browser_hash_length",
        ),
        *non_blank_constraints(
            "nonce",
            "ck_oidc_login_transactions_nonce_non_blank",
        ),
        *non_blank_constraints(
            "pkce_verifier",
            "ck_oidc_login_transactions_pkce_non_blank",
        ),
        CheckConstraint(
            "return_to LIKE '/%' AND return_to NOT LIKE '//%'",
            name="ck_oidc_login_transactions_return_to",
        ),
        CheckConstraint(
            "expires_time > created_time",
            name="ck_oidc_login_transactions_expiry",
        ),
    )

    state_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    browser_binding_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    nonce: Mapped[str] = mapped_column(Text)
    pkce_verifier: Mapped[str] = mapped_column(Text)
    return_to: Mapped[str] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        *hash_length_constraints(
            "session_id_hash",
            "ck_auth_sessions_id_hash_length",
        ),
        *non_blank_constraints(
            "csrf_token",
            "ck_auth_sessions_csrf_token_non_blank",
        ),
        CheckConstraint(
            "last_activity_time >= created_time",
            name="ck_auth_sessions_activity_time",
        ),
        CheckConstraint(
            "absolute_expires_time > created_time",
            name="ck_auth_sessions_absolute_expiry",
        ),
    )

    session_id_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
    )
    csrf_token: Mapped[str] = mapped_column(Text)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_activity_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    absolute_expires_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index(
    "ux_users_email_active",
    func.lower(User.email),
    unique=True,
    postgresql_where=User.deleted_time.is_(None),
    sqlite_where=User.deleted_time.is_(None),
)
Index(
    "idx_oidc_login_transactions_expires_time",
    OidcLoginTransaction.expires_time,
)
Index(
    "idx_oidc_login_transactions_browser_binding_hash",
    OidcLoginTransaction.browser_binding_hash,
)
Index("idx_auth_sessions_user_id", AuthSession.user_id)
Index("idx_auth_sessions_absolute_expires_time", AuthSession.absolute_expires_time)
