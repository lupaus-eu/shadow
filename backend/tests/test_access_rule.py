"""The single Yearclock access rule (Yearclock V2, P10a ticket 01)."""
import re
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uuid import UUID

from app.access import accessible_yearclock_ids, edits_any_yearclock, membership_of, role_on, yearclock_access
from app.database import RequestContext, transaction_session
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login

# Modules that may touch Yearclock grants: the rule itself, grant management, cleanup on removal or purge,
# the DBML generator, which only lists table names for the documentation, and the Organization Export, which
# writes the grants out as data for its Owner and never uses them to decide access.
GRANT_MODULES = {"access.py", "models.py", "yearclock_access_routes.py", "membership_routes.py", "lifecycle.py", "dbml.py", "organization_export.py"}


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_no_module_reads_grants_for_authorization_outside_the_rule() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [path.name for path in app_dir.glob("*.py") if path.name not in GRANT_MODULES and re.search(r"YearclockAccessGrant|yearclock_access_grants|YearclockGroupGrant|yearclock_group_grants", path.read_text())]
    assert offenders == []


def test_roles_and_sources_follow_the_organization_role_and_grants(database_url, stack) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("access-owner", "access-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=5)
    base = f"/api/v1/organizations/{organization_id}"
    first = owner.get(base).json()["yearclocks"][0]
    second = owner.post(f"{base}/yearclocks", json={"name": "Second"}).json()
    ids = {}
    for name, role in (("admin", "admin"), ("editor", "member"), ("viewer", "member"), ("member", "member")):
        _, ids[name] = join(application, owner, organization_id, subject=f"access-{name}", email=f"access-{name}@example.com", role=role)
    owner.put(f"{base}/yearclocks/{first['id']}/access", json={"user_account_id": ids["editor"], "role": "editor"})
    owner.put(f"{base}/yearclocks/{second['id']}/access", json={"user_account_id": ids["editor"], "role": "viewer"})
    owner.put(f"{base}/yearclocks/{first['id']}/access", json={"user_account_id": ids["viewer"], "role": "viewer"})
    first["id"], second["id"] = UUID(first["id"]), UUID(second["id"])
    organization_id, ids = UUID(organization_id), {name: UUID(str(value)) for name, value in ids.items()}
    factory = application.state.session_factory
    with transaction_session(factory, RequestContext(organization_id=organization_id)) as session:
        member = lambda name: membership_of(session, organization_id, ids[name])
        admin = member("admin")
        assert {key: value.role for key, value in yearclock_access(session, admin).items()} == {first["id"]: "editor", second["id"]: "editor"}
        assert yearclock_access(session, admin)[first["id"]].sources == [{"kind": "role", "organization_role": "admin", "role": "editor"}]
        editor = member("editor")
        assert role_on(session, editor, first["id"]) == "editor" and role_on(session, editor, second["id"]) == "viewer"
        assert yearclock_access(session, editor)[second["id"]].sources == [{"kind": "direct", "role": "viewer"}]
        assert edits_any_yearclock(session, editor) is True and edits_any_yearclock(session, member("viewer")) is False
        assert accessible_yearclock_ids(session, member("viewer")) == {first["id"]} and accessible_yearclock_ids(session, member("member")) == set()
    version = next(item for item in owner.get(base).json()["yearclocks"] if item["id"] == str(second["id"]))["version"]
    owner.delete(f"{base}/yearclocks/{second['id']}?expected_version={version}")
    with transaction_session(factory, RequestContext(organization_id=organization_id)) as session:
        editor = membership_of(session, organization_id, ids["editor"])
        assert role_on(session, editor, second["id"]) is None and role_on(session, editor, second["id"], include_deleted=True) == "viewer"
