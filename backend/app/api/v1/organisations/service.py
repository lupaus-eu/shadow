from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.org_states import org_states_service
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.schemas import (
    OrganisationCreateRequest,
    OrganisationPatchRequest,
    OrganisationResponse,
)


def to_organisation_response(organisation: Organisation) -> OrganisationResponse:
    return OrganisationResponse(
        id=organisation.organisation_key,
        name=organisation.name,
    )


def list_organisations(session: Session) -> list[OrganisationResponse]:
    organisations = session.scalars(
        select(Organisation)
        .where(Organisation.deleted_time.is_(None))
        .order_by(Organisation.name, Organisation.organisation_id),
    ).all()

    return [to_organisation_response(organisation) for organisation in organisations]


def get_organisation(session: Session, organisation_key: str) -> OrganisationResponse:
    return to_organisation_response(get_active_organisation(session, organisation_key))


def create_organisation(
    session: Session,
    payload: OrganisationCreateRequest,
    actor_user_id: int,
) -> OrganisationResponse:
    try:
        _ensure_name_is_available(session, payload.name)

        organisation = Organisation(
            organisation_key=_generate_organisation_key(),
            name=payload.name,
            created_by=actor_user_id,
        )
        session.add(organisation)
        session.flush()

        scenario = org_states_service.create_default_scenario(
            session, organisation, actor_user_id
        )
        org_state = org_states_service.create_default_org_state(
            session, scenario, actor_user_id
        )
        org_states_service.link_initial_state(scenario, org_state, actor_user_id)
        org_twin_structure_service.copy_active_default_metamodel(
            session,
            organisation,
            actor_user_id,
        )

        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_name_exception() from exc
    except Exception:
        session.rollback()
        raise

    session.refresh(organisation)
    return to_organisation_response(organisation)


def patch_organisation(
    session: Session,
    organisation_key: str,
    payload: OrganisationPatchRequest,
    actor_user_id: int,
) -> OrganisationResponse:
    organisation = get_active_organisation(session, organisation_key)

    if payload.name is not None and payload.name != organisation.name:
        _ensure_name_is_available(
            session,
            payload.name,
            excluding_organisation_id=organisation.organisation_id,
        )
        organisation.name = payload.name

    organisation.modified_time = datetime.now(UTC)
    organisation.modified_by = actor_user_id

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _duplicate_name_exception() from exc

    session.refresh(organisation)
    return to_organisation_response(organisation)


def soft_delete_organisation(
    session: Session, organisation_key: str, actor_user_id: int
) -> None:
    organisation = get_active_organisation(session, organisation_key)
    now = datetime.now(UTC)

    organisation.deleted_time = now
    organisation.deleted_by = actor_user_id
    organisation.modified_time = now
    organisation.modified_by = actor_user_id
    session.commit()


def get_active_organisation(session: Session, organisation_key: str) -> Organisation:
    organisation = session.scalar(
        select(Organisation).where(
            Organisation.organisation_key == organisation_key,
            Organisation.deleted_time.is_(None),
        ),
    )

    if organisation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found.",
        )

    return organisation


def _ensure_name_is_available(
    session: Session,
    name: str,
    excluding_organisation_id: int | None = None,
) -> None:
    query = select(Organisation.organisation_id).where(
        func.lower(Organisation.name) == name.lower(),
        Organisation.deleted_time.is_(None),
    )

    if excluding_organisation_id is not None:
        query = query.where(Organisation.organisation_id != excluding_organisation_id)

    if session.scalar(query) is not None:
        raise _duplicate_name_exception()


def _generate_organisation_key() -> str:
    return f"org_{uuid4().hex}"


def _duplicate_name_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An active organisation with this name already exists.",
    )
