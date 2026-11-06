"""The single rule for a member's access to Yearclocks (Yearclock V2, P10a; ADR-0007).

A member's role on a Yearclock is the strongest of their Organization role
(Owners and Admins edit everything) and their grants. There is no deny.
Every authorization check reads access through this module, so each new
Access Source applies everywhere at once.
"""
from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Group, GroupMember, OrganizationMembership, OrganizationRole, Yearclock, YearclockAccessGrant, YearclockGroupGrant

MANAGER_ROLES = {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}
_STRENGTH = {None: 0, "viewer": 1, "editor": 2}


@dataclass
class Access:
    """A member's strongest role on one Yearclock and every source that gives access."""
    role: str | None = None
    sources: list[dict] = field(default_factory=list)

    def add(self, role: str, source: dict) -> None:
        self.sources.append({**source, "role": role})
        if _STRENGTH[role] > _STRENGTH[self.role]:
            self.role = role


def membership_of(session: Session, organization_id: UUID, user_account_id: UUID) -> OrganizationMembership | None:
    return session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user_account_id))


def is_manager(membership: OrganizationMembership) -> bool:
    return membership.role in MANAGER_ROLES


def yearclock_access(session: Session, membership: OrganizationMembership, yearclock_ids: Iterable[UUID] | None = None, *, include_deleted: bool = False, without_group: UUID | None = None) -> dict[UUID, Access]:
    """Access per Yearclock of the membership's Organization (only those with some access).

    ``without_group`` leaves one Group out, to show what its deletion takes away.
    """
    clocks = select(Yearclock.id).where(Yearclock.organization_id == membership.organization_id)
    if not include_deleted:
        clocks = clocks.where(Yearclock.deleted_at.is_(None))
    if yearclock_ids is not None:
        clocks = clocks.where(Yearclock.id.in_(list(yearclock_ids)))
    result: dict[UUID, Access] = {}
    if is_manager(membership):
        for yearclock_id in session.scalars(clocks).all():
            result.setdefault(yearclock_id, Access()).add("editor", {"kind": "role", "organization_role": membership.role})
    shared = select(Yearclock.id, Yearclock.organization_access).where(Yearclock.id.in_(clocks), Yearclock.organization_access != "none")
    for yearclock_id, role in session.execute(shared).all():
        result.setdefault(yearclock_id, Access()).add(role, {"kind": "organization"})
    for yearclock_id, role in session.execute(select(YearclockAccessGrant.yearclock_id, YearclockAccessGrant.role).where(YearclockAccessGrant.organization_id == membership.organization_id, YearclockAccessGrant.user_account_id == membership.user_account_id, YearclockAccessGrant.yearclock_id.in_(clocks))).all():
        result.setdefault(yearclock_id, Access()).add(role, {"kind": "direct"})
    groups = (
        select(YearclockGroupGrant.yearclock_id, YearclockGroupGrant.role, Group.id, Group.name)
        .join(Group, Group.id == YearclockGroupGrant.group_id)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.membership_id == membership.id, YearclockGroupGrant.yearclock_id.in_(clocks))
    )
    if without_group is not None:
        groups = groups.where(Group.id != without_group)
    for yearclock_id, role, group_id, group_name in session.execute(groups).all():
        result.setdefault(yearclock_id, Access()).add(role, {"kind": "group", "group_id": str(group_id), "group_name": group_name})
    return result


def role_on(session: Session, membership: OrganizationMembership, yearclock_id: UUID, *, include_deleted: bool = False) -> str | None:
    """The member's strongest role on one Yearclock, or None without access."""
    access = yearclock_access(session, membership, [yearclock_id], include_deleted=include_deleted).get(yearclock_id)
    return access.role if access else None


def accessible_yearclock_ids(session: Session, membership: OrganizationMembership, *, include_deleted: bool = False) -> set[UUID]:
    return set(yearclock_access(session, membership, include_deleted=include_deleted))


def edits_any_yearclock(session: Session, membership: OrganizationMembership) -> bool:
    return any(access.role == "editor" for access in yearclock_access(session, membership).values())


def group_access(session: Session, group: Group) -> list[dict]:
    """The live Yearclocks a Group gives access to, with the role."""
    rows = session.execute(
        select(Yearclock.id, Yearclock.name, YearclockGroupGrant.role)
        .join(YearclockGroupGrant, YearclockGroupGrant.yearclock_id == Yearclock.id)
        .where(YearclockGroupGrant.group_id == group.id, Yearclock.deleted_at.is_(None))
        .order_by(Yearclock.display_order, Yearclock.id)
    ).all()
    return [{"yearclock_id": yearclock_id, "yearclock_name": name, "role": role} for yearclock_id, name, role in rows]


def group_deletion_impact(session: Session, group: Group) -> dict:
    """What deleting a Group changes: its members, the Yearclocks it opens, and who can then no longer open one at all."""
    from app.models import UserAccount

    granted = group_access(session, group)
    members = session.execute(
        select(OrganizationMembership, UserAccount.display_name, UserAccount.email)
        .join(GroupMember, GroupMember.membership_id == OrganizationMembership.id)
        .join(UserAccount, UserAccount.id == OrganizationMembership.user_account_id)
        .where(GroupMember.group_id == group.id)
    ).all()
    losing = []
    for membership, display_name, email in members:
        remaining = yearclock_access(session, membership, [item["yearclock_id"] for item in granted], without_group=group.id)
        losing += [{"name": display_name or email, "yearclock_name": item["yearclock_name"]} for item in granted if item["yearclock_id"] not in remaining]
    return {"members": len(members), "yearclocks": len(granted), "losing_access": losing}



def yearclock_roles(session: Session, organization_id: UUID, yearclock_ids: Iterable[UUID], user_ids: Iterable[UUID] | None = None) -> dict[tuple[UUID, UUID], str]:
    """Role per (user account, Yearclock) for many members at once, by the same rule as ``yearclock_access``.

    Only live Yearclocks and current members appear, and only those with some access. A handful of queries
    however many members there are, so notices about a bulk change can compare before and after.
    """
    wanted = list(yearclock_ids)
    people = None if user_ids is None else set(user_ids)
    clocks = session.execute(select(Yearclock.id, Yearclock.organization_access).where(Yearclock.organization_id == organization_id, Yearclock.id.in_(wanted), Yearclock.deleted_at.is_(None))).all()
    live = {yearclock_id for yearclock_id, _ in clocks}
    members = session.execute(select(OrganizationMembership.id, OrganizationMembership.user_account_id, OrganizationMembership.role).where(OrganizationMembership.organization_id == organization_id)).all()
    members = [member for member in members if people is None or member[1] in people]
    result: dict[tuple[UUID, UUID], str] = {}

    def give(user_id: UUID, yearclock_id: UUID, role: str) -> None:
        key = (user_id, yearclock_id)
        if _STRENGTH[role] > _STRENGTH[result.get(key)]:
            result[key] = role

    for _, user_id, organization_role in members:
        if organization_role in MANAGER_ROLES:
            for yearclock_id in live:
                give(user_id, yearclock_id, "editor")
    for yearclock_id, shared in clocks:
        if shared != "none":
            for _, user_id, _ in members:
                give(user_id, yearclock_id, shared)
    member_users = {user_id for _, user_id, _ in members}
    for yearclock_id, user_id, role in session.execute(select(YearclockAccessGrant.yearclock_id, YearclockAccessGrant.user_account_id, YearclockAccessGrant.role).where(YearclockAccessGrant.organization_id == organization_id, YearclockAccessGrant.yearclock_id.in_(live))).all():
        if user_id in member_users:
            give(user_id, yearclock_id, role)
    by_membership = {membership_id: user_id for membership_id, user_id, _ in members}
    for yearclock_id, role, membership_id in session.execute(
        select(YearclockGroupGrant.yearclock_id, YearclockGroupGrant.role, GroupMember.membership_id)
        .join(GroupMember, GroupMember.group_id == YearclockGroupGrant.group_id)
        .where(YearclockGroupGrant.organization_id == organization_id, YearclockGroupGrant.yearclock_id.in_(live))
    ).all():
        if membership_id in by_membership:
            give(by_membership[membership_id], yearclock_id, role)
    return result


def group_scope(session: Session, group_id: UUID) -> tuple[list[UUID], list[UUID]]:
    """The Yearclocks a Group gives access to and the user accounts in it, for ``AccessWatch``."""
    yearclocks = session.scalars(select(YearclockGroupGrant.yearclock_id).where(YearclockGroupGrant.group_id == group_id)).all()
    users = session.scalars(select(OrganizationMembership.user_account_id).join(GroupMember, GroupMember.membership_id == OrganizationMembership.id).where(GroupMember.group_id == group_id)).all()
    return list(yearclocks), list(users)
