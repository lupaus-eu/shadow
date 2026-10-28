"""Cookie-session review API for AI change sets (ADR-015, TASK-069K).

The Metrics tab lists, inspects, applies and rejects change sets staged
through MCP. Both roles may review, including the creator, and the reviewer is
the actor. The routes stay registered with `MCP_ENABLED=false`, so staged
change sets can still be reviewed while MCP is disabled.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.v1.ai_change_sets import engine, service
from app.api.v1.ai_change_sets.review_schemas import (
    LIST_CHANGE_SETS_DEFAULT_LIMIT,
    LIST_CHANGE_SETS_MAX_LIMIT,
    ChangeSetApplyRequest,
    ChangeSetApplyResponse,
    ChangeSetListItem,
    ChangeSetRejectRequest,
    ChangeSetReviewDetail,
    ReviewOperationResult,
)
from app.api.v1.ai_change_sets.schemas import ChangeSetStatus
from app.api.v1.auth.dependencies import (
    AuthHttpError,
    SessionDependency,
    SettingsDependency,
    UnsafeRequestDependency,
    require_business_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/organisations/{organisation_key}/ai/change-sets",
    tags=["ai"],
    dependencies=[Depends(require_business_request)],
)


@router.get("", response_model=list[ChangeSetListItem])
def list_change_sets(
    organisation_key: str,
    session: SessionDependency,
    status_filter: Annotated[ChangeSetStatus | None, Query(alias="status")] = None,
    scenario_key: Annotated[str | None, Query(alias="scenarioKey")] = None,
    include_unscoped: Annotated[bool, Query(alias="includeUnscoped")] = False,
    limit: Annotated[
        int, Query(ge=1, le=LIST_CHANGE_SETS_MAX_LIMIT)
    ] = LIST_CHANGE_SETS_DEFAULT_LIMIT,
) -> list[ChangeSetListItem]:
    summaries = service.list_change_sets(
        session,
        organisation_key,
        status_filter=status_filter,
        scenario_key=scenario_key,
        include_unscoped=include_unscoped,
        limit=limit,
    )
    names = service.user_names(
        session,
        (
            user_id
            for summary in summaries
            for user_id in (summary.created_by, summary.reviewed_by)
        ),
    )
    return [service.review_list_item(summary, names) for summary in summaries]


@router.get("/{change_set_key}", response_model=ChangeSetReviewDetail)
def get_change_set(
    organisation_key: str,
    change_set_key: str,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ChangeSetReviewDetail:
    try:
        return service.review_detail(
            session, organisation_key, change_set_key, settings=settings
        )
    except DBAPIError as exc:
        # For example the statement timeout during the flag recomputation.
        session.rollback()
        logger.warning(
            "AI change set %s review could not be read after %s",
            change_set_key,
            type(exc).__name__,
        )
        raise AuthHttpError(
            503,
            "review_unavailable",
            "The change set review could not be loaded right now. Try again shortly.",
        ) from exc


@router.post("/{change_set_key}/apply", response_model=ChangeSetApplyResponse)
def apply_change_set(
    organisation_key: str,
    change_set_key: str,
    payload: ChangeSetApplyRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    active: UnsafeRequestDependency,
) -> ChangeSetApplyResponse:
    try:
        result = engine.apply_change_set(
            session,
            organisation_key,
            change_set_key,
            payload.review_fingerprint,
            active.user.user_id,
            settings=settings,
        )
    except engine.ChangeSetApplyError as exc:
        raise AuthHttpError(exc.status_code, exc.code, exc.message) from exc
    return ChangeSetApplyResponse(
        change_set=_list_item(session, organisation_key, change_set_key),
        operations=[
            ReviewOperationResult.model_validate(item.model_dump())
            for item in result.operations
        ],
        refs=result.refs,
    )


@router.post("/{change_set_key}/reject", response_model=ChangeSetListItem)
def reject_change_set(
    organisation_key: str,
    change_set_key: str,
    session: SessionDependency,
    settings: SettingsDependency,
    active: UnsafeRequestDependency,
    payload: ChangeSetRejectRequest | None = None,
) -> ChangeSetListItem:
    try:
        engine.reject_change_set(
            session,
            organisation_key,
            change_set_key,
            payload.note if payload is not None else None,
            active.user.user_id,
            settings=settings,
        )
    except engine.ChangeSetApplyError as exc:
        raise AuthHttpError(exc.status_code, exc.code, exc.message) from exc
    session.commit()
    return _list_item(session, organisation_key, change_set_key)


def _list_item(
    session: Session, organisation_key: str, change_set_key: str
) -> ChangeSetListItem:
    change_set = service.get_change_set(
        session, change_set_key, organisation_key=organisation_key
    )
    summary = service.change_set_summary(session, change_set)
    names = service.user_names(session, (summary.created_by, summary.reviewed_by))
    return service.review_list_item(summary, names)
