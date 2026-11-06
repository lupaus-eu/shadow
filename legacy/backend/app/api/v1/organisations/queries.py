from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.organisations.models import Organisation


def get_active_organisation(session: Session, organisation_key: str) -> Organisation:
    organisation = session.scalar(
        select(Organisation).where(
            Organisation.organisation_key == organisation_key,
            Organisation.deleted_time.is_(None),
        )
    )
    if organisation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found.",
        )
    return organisation
