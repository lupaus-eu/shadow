from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.users.models import AuthSession, User, UserIdentity
from app.core.config import Settings
from app.core.models import Base
from app.provision_local_admin import (
    LocalAdminProvisioningError,
    provision_local_admin,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as database_session:
        yield database_session
    engine.dispose()


def development_settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "development",
            "PUBLIC_ORIGIN": "https://app.localhost",
            "APP_ALLOWED_ORIGIN": "https://app.localhost",
            "SESSION_COOKIE_SECURE": True,
            "TRUSTED_CADDY_PEER_CIDRS": "172.28.59.2/32",
        }
    )


def test_provisions_admin_without_identity_or_session(session: Session) -> None:
    result = provision_local_admin(
        session,
        development_settings(),
        name=" Local Admin ",
        email="local.admin@example.test",
    )

    user = session.get(User, result.user_id)
    assert result.created is True
    assert user is not None
    assert user.name == "Local Admin"
    assert user.role == "admin"
    assert session.query(UserIdentity).count() == 0
    assert session.query(AuthSession).count() == 0


def test_existing_admin_is_idempotent_without_role_change(session: Session) -> None:
    user = User(name="Existing", email="existing@example.test", role="admin")
    session.add(user)
    session.commit()

    result = provision_local_admin(
        session,
        development_settings(),
        name="Other name",
        email="EXISTING@example.test",
    )

    assert result == type(result)(user_id=user.user_id, created=False)
    assert session.get(User, user.user_id).name == "Existing"  # type: ignore[union-attr]


def test_provisions_on_a_populated_development_database(session: Session) -> None:
    session.add(
        User(
            name="Seeded Consultant",
            email="consultant@example.local",
            role="consultant",
        )
    )
    session.commit()

    result = provision_local_admin(
        session,
        development_settings(),
        name="Local Admin",
        email="local.admin@example.test",
    )

    assert result.created is True
    assert session.query(User).count() == 2
    assert session.get(User, result.user_id).role == "admin"  # type: ignore[union-attr]


@pytest.mark.parametrize("role, deleted", [("consultant", False), ("admin", True)])
def test_conflicting_or_deleted_account_is_not_admitted(
    session: Session, role: str, deleted: bool
) -> None:
    user = User(name="Existing", email="existing@example.test", role=role)
    if deleted:
        user.deleted_time = datetime.now(UTC)
    session.add(user)
    session.commit()

    with pytest.raises(LocalAdminProvisioningError):
        provision_local_admin(
            session,
            development_settings(),
            name="Local Admin",
            email="existing@example.test",
        )

    assert session.query(User).count() == 1


def test_rejects_non_development_and_invalid_email(session: Session) -> None:
    with pytest.raises(LocalAdminProvisioningError):
        provision_local_admin(
            session,
            Settings(),
            name="Local Admin",
            email="local.admin@example.test",
        )
    with pytest.raises(ValueError, match="valid email"):
        provision_local_admin(
            session,
            development_settings(),
            name="Local Admin",
            email="not-an-email",
        )
