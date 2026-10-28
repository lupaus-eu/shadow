"""Read AI change sets for the MCP tools (ADR-015).

Change sets are read by key within active organisations. Scenario and
organisation rows are joined only to map ids to keys, as the engine does.
"""

from collections.abc import Sequence
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.v1.ai_change_sets.models import AiChangeSet, AiChangeSetOperation
from app.api.v1.ai_change_sets.schemas import (
    ApplyOutcome,
    ChangeSetDetail,
    ChangeSetOperationDetail,
    ChangeSetStatus,
    ChangeSetSummary,
    ExecutionResult,
    FrozenValues,
    FrozenValuesSummary,
    OperationError,
)
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import Scenario
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.service import get_active_organisation


def get_change_set(session: Session, change_set_key: str) -> AiChangeSet:
    """The change set with this key in an active organisation, else 404."""
    change_set = session.scalar(
        select(AiChangeSet)
        .join(Organisation, Organisation.organisation_id == AiChangeSet.organisation_id)
        .where(
            AiChangeSet.change_set_key == change_set_key,
            Organisation.deleted_time.is_(None),
        )
    )
    if change_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Change set not found.",
        )
    return change_set


def list_change_sets(
    session: Session,
    organisation_key: str,
    *,
    status_filter: ChangeSetStatus | None,
    scenario_key: str | None,
    limit: int,
) -> list[ChangeSetSummary]:
    """An organisation's change sets, newest first, at most `limit`.

    `scenario_key` filters on the derived scenario reference and must name an
    active scenario of the organisation.
    """
    organisation = get_active_organisation(session, organisation_key)
    query = _summary_query().where(
        AiChangeSet.organisation_id == organisation.organisation_id
    )
    if status_filter is not None:
        query = query.where(AiChangeSet.status == status_filter)
    if scenario_key is not None:
        org_states_service.get_scenario(session, organisation_key, scenario_key)
        query = query.where(
            Scenario.scenario_key == scenario_key, Scenario.deleted_time.is_(None)
        )
    rows = session.execute(
        query.order_by(
            AiChangeSet.created_time.desc(), AiChangeSet.change_set_id.desc()
        ).limit(limit)
    ).all()
    return [_summary(*row) for row in rows]


def change_set_summary(session: Session, change_set: AiChangeSet) -> ChangeSetSummary:
    row = session.execute(
        _summary_query().where(AiChangeSet.change_set_id == change_set.change_set_id)
    ).one()
    return _summary(*row)


def change_set_detail(session: Session, change_set: AiChangeSet) -> ChangeSetDetail:
    summary = change_set_summary(session, change_set)
    rows = session.scalars(
        select(AiChangeSetOperation)
        .where(AiChangeSetOperation.change_set_id == change_set.change_set_id)
        .order_by(AiChangeSetOperation.position)
    ).all()
    return ChangeSetDetail(
        **summary.model_dump(),
        operations=_operation_details(rows),
        validation_result=(
            ExecutionResult.model_validate(change_set.validation_result)
            if change_set.validation_result is not None
            else None
        ),
        applied_result=(
            ApplyOutcome.model_validate(change_set.applied_result)
            if change_set.applied_result is not None
            else None
        ),
    )


def _summary_query() -> Select[tuple[AiChangeSet, str, str, int]]:
    operation_count = (
        select(func.count())
        .where(AiChangeSetOperation.change_set_id == AiChangeSet.change_set_id)
        .correlate(AiChangeSet)
        .scalar_subquery()
    )
    return (
        select(
            AiChangeSet,
            Organisation.organisation_key,
            Scenario.scenario_key,
            operation_count,
        )
        .join(Organisation, Organisation.organisation_id == AiChangeSet.organisation_id)
        .outerjoin(Scenario, Scenario.scenario_id == AiChangeSet.scenario_id)
    )


def _summary(
    change_set: AiChangeSet,
    organisation_key: str,
    scenario_key: str | None,
    operation_count: int,
) -> ChangeSetSummary:
    return ChangeSetSummary(
        id=change_set.change_set_key,
        organisation_key=organisation_key,
        scenario_key=scenario_key,
        title=change_set.title,
        rationale=change_set.rationale,
        status=cast(ChangeSetStatus, change_set.status),
        operation_count=operation_count,
        client_id=change_set.client_id,
        client_name=change_set.client_name,
        created_by=change_set.created_by,
        created_time=change_set.created_time,
        modified_time=change_set.modified_time,
        reviewed_by=change_set.reviewed_by,
        reviewed_time=change_set.reviewed_time,
        review_note=change_set.review_note,
    )


def _operation_details(
    rows: Sequence[AiChangeSetOperation],
) -> list[ChangeSetOperationDetail]:
    details: list[ChangeSetOperationDetail] = []
    for row in rows:
        operation: dict[str, Any] = {"type": row.op_type}
        if row.ref is not None:
            operation["ref"] = row.ref
        operation.update(row.payload)
        details.append(
            ChangeSetOperationDetail(
                position=row.position,
                type=row.op_type,
                ref=row.ref,
                operation=operation,
                error=(
                    OperationError.model_validate(row.error)
                    if row.error is not None
                    else None
                ),
                frozen_values=(
                    _frozen_summary(FrozenValues.model_validate(row.frozen_values))
                    if row.frozen_values is not None
                    else None
                ),
            )
        )
    return details


def _frozen_summary(frozen: FrozenValues) -> FrozenValuesSummary:
    return FrozenValuesSummary(
        generator_version=frozen.generator_version,
        value_count=len(frozen.values),
        first_date=frozen.values[0].date if frozen.values else None,
        last_date=frozen.values[-1].date if frozen.values else None,
    )
