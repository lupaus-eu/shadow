from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.users.models import (
    AuthSession,
    OidcLoginTransaction,
    User,
    UserIdentity,
)
from app.core.models import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _user(session: Session, email: str) -> User:
    user = User(name=email, email=email, role="consultant")
    session.add(user)
    session.commit()
    return user


def test_identity_uniqueness_is_provider_scoped(session: Session) -> None:
    first_user = _user(session, "first@example.local")
    second_user = _user(session, "second@example.local")
    session.add(
        UserIdentity(
            user_id=first_user.user_id,
            issuer="https://issuer.example",
            subject="subject-1",
        )
    )
    session.commit()

    session.add(
        UserIdentity(
            user_id=second_user.user_id,
            issuer="https://issuer.example",
            subject="subject-1",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        UserIdentity(
            user_id=first_user.user_id,
            issuer="https://issuer.example",
            subject="subject-2",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_login_transaction_stores_separate_hashes_and_timeout_fields(
    session: Session,
) -> None:
    now = datetime.now(UTC)
    transaction = OidcLoginTransaction(
        state_hash=b"s" * 32,
        browser_binding_hash=b"b" * 32,
        nonce="nonce",
        pkce_verifier="verifier",
        return_to="/schatten",
        created_time=now,
        expires_time=now + timedelta(minutes=10),
    )
    session.add(transaction)
    session.commit()

    assert transaction.state_hash != transaction.browser_binding_hash
    assert transaction.expires_time > transaction.created_time


def test_session_model_exposes_only_hashed_identifier_and_timeout_state(
    session: Session,
) -> None:
    user = _user(session, "session@example.local")
    now = datetime.now(UTC)
    auth_session = AuthSession(
        session_id_hash=b"h" * 32,
        user_id=user.user_id,
        csrf_token="csrf-token",
        created_time=now,
        last_activity_time=now,
        absolute_expires_time=now + timedelta(hours=8),
    )
    session.add(auth_session)
    session.commit()

    columns = set(AuthSession.__table__.columns.keys())
    assert "session_id_hash" in columns
    assert "session_id" not in columns
    assert not {"access_token", "refresh_token", "id_token", "client_secret"} & columns


def test_hash_columns_reject_non_sha256_lengths(session: Session) -> None:
    now = datetime.now(UTC)
    session.add(
        OidcLoginTransaction(
            state_hash=b"short",
            browser_binding_hash=b"b" * 32,
            nonce="nonce",
            pkce_verifier="verifier",
            return_to="/",
            created_time=now,
            expires_time=now + timedelta(minutes=10),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
