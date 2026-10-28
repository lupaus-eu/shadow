import hashlib
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.users.models import AuthSession, User

TEST_ACTOR_USER_ID = 0
TEST_CSRF_TOKEN = "test-csrf-token"
TEST_RAW_SESSION_ID = "s" * 43
TEST_ORIGIN = "http://testserver"


def authenticate_test_client(
    client: TestClient,
    session_factory: sessionmaker[Session],
    *,
    user_id: int = TEST_ACTOR_USER_ID,
    role: str = "admin",
    raw_session_id: str = TEST_RAW_SESSION_ID,
    csrf_token: str = TEST_CSRF_TOKEN,
    create_user: bool = True,
) -> int:
    """Sign the client in; `create_user=False` signs in an existing User."""
    now = datetime.now(UTC)
    with session_factory() as session:
        if create_user:
            session.add(
                User(
                    user_id=user_id,
                    name=f"Test {role.title()}",
                    email=f"test-{abs(user_id)}@example.test",
                    role=role,
                )
            )
            # Insert the User first for test databases that enforce foreign keys.
            session.flush()
        session.add(
            AuthSession(
                session_id_hash=hashlib.sha256(raw_session_id.encode()).digest(),
                user_id=user_id,
                csrf_token=csrf_token,
                created_time=now,
                last_activity_time=now,
                absolute_expires_time=now + timedelta(hours=8),
            )
        )
        session.commit()

    client.cookies.set("schatten-session", raw_session_id)
    client.headers.update(
        {
            "Origin": TEST_ORIGIN,
            "X-CSRF-Token": csrf_token,
        }
    )
    return user_id
