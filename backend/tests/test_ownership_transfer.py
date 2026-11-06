"""Ownership Transfer and leaving as the last Owner (Shadow V2, P14 ticket 03)."""
from datetime import UTC, datetime

from sqlalchemy import text

from test_notifications import World, stack  # noqa: F401 - the fixture
from test_subscription_lifecycle import _event, _post


def roles(world, client=None):
    people = {}
    for item in (client or world.owner).get(f"{world.org}/memberships").json():
        local = item["email"].split("@")[0]
        people["owner" if local == world.subject else local.removeprefix(f"{world.subject}-")] = item
    return people


def audit(world, client=None):
    return (client or world.owner).get(f"{world.org}/audit-events", params={"prefix": "organization"}).json()["items"]


def transfer(client, world, membership, **body):
    return client.post(f"{world.org}/memberships/{membership['id']}/transfer-ownership", json={"expected_version": membership["version"], **body})


def test_a_transfer_makes_the_member_an_owner_and_lowers_the_caller_in_one_action(database_url, stack) -> None:
    world = World(stack, database_url, "own-transfer")
    admin, _, admin_membership = world.person("admin", role="admin")
    other, _, other_membership = world.person("other", role="admin")
    world.owner.patch(f"{world.org}/memberships/{other_membership['id']}", json={"role": "owner", "expected_version": other_membership["version"]})
    response = transfer(world.owner, world, admin_membership)
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "owner"
    people = roles(world)
    assert people["admin"]["role"] == "owner" and people["owner"]["role"] == "admin" and people["other"]["role"] == "owner"
    entry = next(item for item in audit(world) if item["action"] == "organization.ownership_transferred")
    assert entry["change_summary"]["kept_owner"] is False
    assert [item["params"]["to_role"] for item in world.notices(admin, "role_changed")] == ["owner"]
    assert any(item["params"]["owner"] is True for item in world.notices(other, "ownership_changed"))
    assert any(item["params"]["owner"] is False for item in world.notices(other, "ownership_changed"))
    assert world.notices(world.owner, "role_changed") == []
    assert world.owner.get(world.org).json()["membership"]["role"] == "admin"


def test_keeping_the_owner_role_makes_two_owners(database_url, stack) -> None:
    world = World(stack, database_url, "own-keep")
    member, _, membership = world.person("member")
    assert transfer(world.owner, world, membership, keep_owner=True).status_code == 200
    people = roles(world)
    assert people["member"]["role"] == "owner" and people["owner"]["role"] == "owner"


def test_the_target_and_the_caller_must_qualify_and_nothing_changes_when_refused(database_url, stack) -> None:
    world = World(stack, database_url, "own-rules")
    admin, _, admin_membership = world.person("admin", role="admin")
    member, _, member_membership = world.person("member")
    me = roles(world)["owner"]
    assert transfer(world.owner, world, me).status_code == 422  # not to yourself
    assert world.owner.post(f"{world.org}/memberships/00000000-0000-4000-8000-000000000000/transfer-ownership", json={"expected_version": 1}).status_code == 404
    stale = world.owner.post(f"{world.org}/memberships/{member_membership['id']}/transfer-ownership", json={"expected_version": member_membership["version"] + 5})
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": member_membership["version"]}
    assert transfer(admin, world, member_membership).status_code == 403  # an Admin cannot
    assert transfer(member, world, admin_membership).status_code == 403
    assert {key: value["role"] for key, value in roles(world).items()} == {"owner": "owner", "admin": "admin", "member": "member"}
    assert not any(item["action"] == "organization.ownership_transferred" for item in audit(world))
    assert transfer(world.owner, world, member_membership).status_code == 200
    again = world.owner.post(f"{world.org}/memberships/{member_membership['id']}/transfer-ownership", json={"expected_version": member_membership["version"] + 1})
    assert again.status_code == 403  # the caller is no longer an Owner


def test_a_read_only_organization_refuses_a_transfer(database_url, stack) -> None:
    world = World(stack, database_url, "own-readonly")
    member, _, membership = world.person("member")
    _post(world.owner, world.verifier, _event(world.organization_id, "customer.subscription.deleted", "evt_own_ended", datetime.now(UTC)))
    assert transfer(world.owner, world, membership).status_code == 403
    assert roles(world)["member"]["role"] == "member"


def test_people_leave_for_themselves_only_and_free_their_seat(database_url, stack) -> None:
    world = World(stack, database_url, "own-leave")
    member, _, membership = world.person("member")
    admin, _, admin_membership = world.person("admin", role="admin")
    before = world.owner.get(f"{world.org}/billing/seats").json()["occupied"]
    assert admin.post(f"{world.org}/memberships/{membership['id']}/leave").status_code == 403
    assert member.post(f"{world.org}/memberships/{membership['id']}/leave").status_code == 204
    assert world.owner.get(f"{world.org}/billing/seats").json()["occupied"] == before - 1
    assert "member" not in roles(world)
    assert any(item["action"] == "organization.membership_left" for item in audit(world))


def test_the_only_owner_must_name_a_successor_and_leaves_with_the_transfer(database_url, stack) -> None:
    world = World(stack, database_url, "own-last")
    admin, _, admin_membership = world.person("admin", role="admin")
    member, _, member_membership = world.person("member")
    me = roles(world)["owner"]
    assert world.owner.post(f"{world.org}/memberships/{me['id']}/leave").json()["detail"] == {"reason": "successor_required"}
    assert world.owner.post(f"{world.org}/memberships/{me['id']}/leave", json={"successor_membership_id": me["id"]}).status_code == 422
    assert roles(world)["owner"]["role"] == "owner"  # a refused attempt changes nothing
    assert world.owner.post(f"{world.org}/memberships/{me['id']}/leave", json={"successor_membership_id": member_membership["id"]}).status_code == 204
    people = roles(world, member)
    assert "owner" not in people and people["member"]["role"] == "owner"
    assert member.get(world.org).json()["membership"]["role"] == "owner"
    entry = next(item for item in audit(world, member) if item["action"] == "organization.ownership_transferred")
    assert entry["change_summary"]["leaving"] is True
    assert world.owner.get(world.org).status_code == 404  # the leaver no longer reaches the Organization


def test_the_only_member_cannot_leave_and_is_pointed_to_deletion_or_an_invitation(database_url, stack) -> None:
    world = World(stack, database_url, "own-alone")
    me = roles(world)["owner"]
    response = world.owner.post(f"{world.org}/memberships/{me['id']}/leave")
    assert response.status_code == 409 and response.json()["detail"] == {"reason": "last_member"}


def test_an_owner_who_is_not_the_last_leaves_without_a_successor(database_url, stack) -> None:
    world = World(stack, database_url, "own-second")
    member, _, membership = world.person("member")
    assert transfer(world.owner, world, membership, keep_owner=True).status_code == 200
    me = roles(world)["owner"]
    assert world.owner.post(f"{world.org}/memberships/{me['id']}/leave").status_code == 204
    assert roles(world, member)["member"]["role"] == "owner"
