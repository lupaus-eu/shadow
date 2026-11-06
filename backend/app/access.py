"""Membership access rules of the platform (ADR-0005; the Shadow-specific grants are gone).

An Organization role (Owner, Admin, Member) decides what a person may do in an
Organization. Product features add their own access rules on top of it.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OrganizationMembership, OrganizationRole

MANAGER_ROLES = {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}


def membership_of(session: Session, organization_id: UUID, user_account_id: UUID) -> OrganizationMembership | None:
    return session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user_account_id))


def is_manager(membership: OrganizationMembership) -> bool:
    return membership.role in MANAGER_ROLES
