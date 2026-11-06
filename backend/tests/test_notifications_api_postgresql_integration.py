from collections.abc import Generator, Iterator
from uuid import uuid4

import pytest
from auth_helpers import authenticate_test_client
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import (
    RequestContext,
    get_db_session,
    get_session_factory,
    transaction_session,
)
from app.main import create_app
from app.platform.notifications import NotificationDraft, notify_many

Factory = sessionmaker[Session]
BASE = "/api/v1/notifications"


@pytest.fixture
def client(schema_session_factory: Factory) -> Generator[TestClient, None, None]:
    app = create_app(settings=Settings())

    def db_session() -> Iterator[Session]:
        with schema_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = db_session
    app.dependency_overrides[get_session_factory] = lambda: schema_session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _signed_in(client: TestClient, factory: Factory, user_id: int = 7) -> int:
    return authenticate_test_client(client, factory, user_id=user_id, role="consultant")


def _other_user(factory: Factory) -> int:
    with factory.begin() as session:
        return int(
            session.scalar(
                text(
                    "INSERT INTO users (name, role, email) "
                    "VALUES ('Other', 'admin', 'o@example.test') RETURNING user_id"
                )
            )
            or 0
        )


def _notify(factory: Factory, recipient: int, count: int = 1, **params: object) -> None:
    # One transaction each, so the notifications get distinct creation times.
    for index in range(count):
        with transaction_session(factory, RequestContext()) as session:
            notify_many(
                session,
                [NotificationDraft(recipient, "demo.changed", {"n": index, **params})],
            )


def test_every_route_requires_a_session(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401
    assert client.get(f"{BASE}/unread-count").status_code == 401
    assert client.post(f"{BASE}/read-all").status_code == 401
    assert client.post(f"{BASE}/{uuid4()}/read").status_code == 401


def test_a_user_lists_only_their_own_notifications_newest_first(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    other = _other_user(schema_session_factory)
    _notify(schema_session_factory, me, 2)
    _notify(schema_session_factory, other, 3)

    body = client.get(BASE).json()

    assert [item["params"]["n"] for item in body["items"]] == [1, 0]
    assert body["next_cursor"] is None
    assert {"id", "type", "params", "created_time", "read_time"} == set(
        body["items"][0]
    )
    assert client.get(f"{BASE}/unread-count").json() == {"unread": 2}


def test_listing_is_paged_with_a_cursor_and_filters_unread(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    _notify(schema_session_factory, me, 25)
    first = client.get(BASE).json()
    assert len(first["items"]) == 20 and first["next_cursor"]
    second = client.get(BASE, params={"cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 5 and second["next_cursor"] is None
    ids = {item["id"] for item in first["items"]} | {
        item["id"] for item in second["items"]
    }
    assert len(ids) == 25

    client.post(f"{BASE}/{first['items'][0]['id']}/read")
    unread = client.get(BASE, params={"unread": "true"}).json()
    assert first["items"][0]["id"] not in {item["id"] for item in unread["items"]}
    assert client.get(BASE, params={"cursor": "nonsense"}).status_code == 422


def test_marking_read_sets_the_time_once_and_unknown_or_foreign_ids_are_404(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    other = _other_user(schema_session_factory)
    _notify(schema_session_factory, me)
    _notify(schema_session_factory, other)
    (mine,) = client.get(BASE).json()["items"]
    with transaction_session(schema_session_factory, RequestContext()) as session:
        foreign = session.scalar(
            text("SELECT id FROM notifications WHERE recipient_user_id = :id"),
            {"id": other},
        )

    assert client.post(f"{BASE}/{mine['id']}/read").status_code == 204
    read_time = client.get(BASE).json()["items"][0]["read_time"]
    assert read_time is not None
    assert client.post(f"{BASE}/{mine['id']}/read").status_code == 204
    assert client.get(BASE).json()["items"][0]["read_time"] == read_time
    assert client.post(f"{BASE}/{foreign}/read").status_code == 404
    assert client.post(f"{BASE}/{uuid4()}/read").status_code == 404
    assert client.post(f"{BASE}/not-a-uuid/read").status_code == 422


def test_read_all_marks_only_the_callers_notifications(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    other = _other_user(schema_session_factory)
    _notify(schema_session_factory, me, 3)
    _notify(schema_session_factory, other, 2)

    assert client.post(f"{BASE}/read-all").json() == {"updated": 3}
    assert client.get(f"{BASE}/unread-count").json() == {"unread": 0}
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM notifications WHERE read_time IS NULL")
            )
            == 2
        )


def test_marking_requires_origin_and_csrf(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    _notify(schema_session_factory, me)
    client.headers.pop("X-CSRF-Token")
    assert client.post(f"{BASE}/read-all").status_code == 403
    assert client.get(f"{BASE}/unread-count").json() == {"unread": 1}


def test_cursor_is_opaque_and_pages_stay_complete_when_creation_times_are_equal(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    with transaction_session(schema_session_factory, RequestContext()) as session:
        notify_many(
            session,
            [
                NotificationDraft(me, "demo.changed", {"n": index})
                for index in range(25)
            ],
        )  # one transaction: every row has the same creation time
    first = client.get(BASE).json()
    assert "|" not in first["next_cursor"] and "+" not in first["next_cursor"]
    second = client.get(f"{BASE}?cursor={first['next_cursor']}").json()
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(ids) == 25 and len(set(ids)) == 25


def test_marking_read_never_violates_the_read_after_created_check(
    client: TestClient, schema_session_factory: Factory
) -> None:
    me = _signed_in(client, schema_session_factory)
    _notify(schema_session_factory, me)
    with transaction_session(schema_session_factory, RequestContext()) as session:
        session.execute(
            text("UPDATE notifications SET created_time = now() + interval '1 hour'")
        )
    (item,) = client.get(BASE).json()["items"]
    assert client.post(f"{BASE}/{item['id']}/read").status_code == 204
    assert client.post(f"{BASE}/read-all").status_code == 200
