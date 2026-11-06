from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.database import (
    APPLICATION_DATABASE_ROLE,
    RequestContext,
    apply_request_context,
)


def _executed(session: MagicMock) -> list[tuple[str, dict[str, str]]]:
    calls: list[tuple[str, dict[str, str]]] = []
    for call in session.execute.call_args_list:
        params = cast(dict[str, str], call.args[1])
        calls.append((str(call.args[0]), params))
    return calls


def test_apply_request_context_sets_every_setting_transaction_locally() -> None:
    session = MagicMock(spec=Session)
    tenant_id = uuid4()

    apply_request_context(session, RequestContext(user_id=101, tenant_id=tenant_id))

    values = {params["name"]: params["value"] for _, params in _executed(session)}
    assert values == {
        "app.request_context": "applied",
        "app.current_user_id": "101",
        "app.current_tenant_id": str(tenant_id),
        "app.current_support_access_id": "",
        "app.current_invitation_token_hash": "",
        "app.worker_scope": "",
    }
    assert all("true" in statement for statement, _ in _executed(session))


def test_empty_context_clears_all_settings() -> None:
    session = MagicMock(spec=Session)

    apply_request_context(session, RequestContext())

    values = {params["name"]: params["value"] for _, params in _executed(session)}
    assert values.pop("app.request_context") == "applied"
    assert set(values.values()) == {""}


def test_application_role_name_is_shadow_app() -> None:
    assert APPLICATION_DATABASE_ROLE == "shadow_app"
