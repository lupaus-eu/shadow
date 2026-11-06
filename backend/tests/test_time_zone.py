from datetime import datetime, timezone

from app.time_zone import organization_today


def test_organization_today_uses_the_organization_time_zone() -> None:
    now = datetime(2024, 1, 1, 23, 30, tzinfo=timezone.utc)

    assert organization_today("Europe/Helsinki", now=now).isoformat() == "2024-01-02"
