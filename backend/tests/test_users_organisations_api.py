from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    app = create_app()

    def override_get_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_users_crud_excludes_soft_deleted_rows(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/users",
        json={"name": "  Ada Lovelace  ", "role": "admin"},
    )
    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user == {"id": 1, "name": "Ada Lovelace", "role": "admin"}

    user_id = created_user["id"]
    assert client.get(f"/api/v1/users/{user_id}").json() == created_user
    assert client.get("/api/v1/users").json() == [created_user]

    patch_response = client.patch(
        f"/api/v1/users/{user_id}",
        json={"name": "Grace Hopper", "role": "consultant"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": user_id,
        "name": "Grace Hopper",
        "role": "consultant",
    }

    delete_response = client.delete(f"/api/v1/users/{user_id}")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/users").json() == []
    assert client.get(f"/api/v1/users/{user_id}").status_code == 404


def test_user_create_rejects_invalid_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users",
        json={"name": "Ada Lovelace", "role": "owner"},
    )

    assert response.status_code == 422


def test_organisation_crud_returns_frontend_dto_and_excludes_deleted_rows(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/v1/organisations",
        json={"name": "  Acme Corp  "},
    )
    assert create_response.status_code == 201
    created_org = create_response.json()
    assert created_org["id"].startswith("org_")
    assert created_org["name"] == "Acme Corp"

    organisation_key = created_org["id"]
    assert client.get(f"/api/v1/organisations/{organisation_key}").json() == created_org
    assert client.get("/api/v1/organisations").json() == [created_org]

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}",
        json={"name": "Acme Updated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": organisation_key,
        "name": "Acme Updated",
    }

    delete_response = client.delete(f"/api/v1/organisations/{organisation_key}")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/organisations").json() == []
    assert client.get(f"/api/v1/organisations/{organisation_key}").status_code == 404


def test_duplicate_active_organisation_name_returns_409(client: TestClient) -> None:
    first_response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    assert first_response.status_code == 201

    duplicate_response = client.post(
        "/api/v1/organisations",
        json={"name": "acme corp"},
    )
    assert duplicate_response.status_code == 409


def test_soft_deleted_organisation_name_can_be_reused(client: TestClient) -> None:
    first_response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    assert first_response.status_code == 201

    organisation_key = first_response.json()["id"]
    assert client.delete(f"/api/v1/organisations/{organisation_key}").status_code == 204

    second_response = client.post("/api/v1/organisations", json={"name": "acme corp"})
    assert second_response.status_code == 201
    assert second_response.json()["name"] == "acme corp"


def test_patch_organisation_rejects_duplicate_active_name(
    client: TestClient,
) -> None:
    first_response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    second_response = client.post("/api/v1/organisations", json={"name": "Globex"})
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.patch(
        f"/api/v1/organisations/{second_response.json()['id']}",
        json={"name": "ACME CORP"},
    )

    assert response.status_code == 409
