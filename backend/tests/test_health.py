from app.health.router import read_health
from app.main import create_app


def test_health_endpoint_returns_ok() -> None:
    response = read_health()

    assert response.model_dump() == {"status": "ok"}


def test_health_route_is_registered() -> None:
    schema = create_app().openapi()
    paths = schema.get("paths")

    assert isinstance(paths, dict)
    assert "/health" in paths
