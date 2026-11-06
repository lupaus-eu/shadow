from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.subscription_access import mark_payment_recovered, mark_renewal_failed, require_mutation_access

def test_failed_renewal_has_seven_day_grace_then_read_only() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC); organization = SimpleNamespace(subscription_access_state="active", grace_expires_at=None)
    mark_renewal_failed(organization, now=now)
    require_mutation_access(organization, now=now + timedelta(days=6))
    with pytest.raises(HTTPException): require_mutation_access(organization, now=now + timedelta(days=7))
    mark_payment_recovered(organization); require_mutation_access(organization, now=now + timedelta(days=8))
