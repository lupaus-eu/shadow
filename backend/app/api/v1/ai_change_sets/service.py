"""Read AI change sets for the MCP tools and the review API (ADR-015).

Change sets are read by key within active organisations. Scenario and
organisation rows are joined only to map ids to keys, as the engine does, and
User rows are read only for the names of creators and reviewers.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.ai_change_sets import engine
from app.api.v1.ai_change_sets.models import AiChangeSet, AiChangeSetOperation
from app.api.v1.ai_change_sets.review_schemas import (
    INLINE_FROZEN_VALUES_LIMIT,
    ChangeSetListItem,
    ChangeSetReviewDetail,
    ChangeSetReviewOperation,
    ReviewApplyOutcome,
    ReviewExecutionResult,
    ReviewFrozenValues,
    ReviewNodeReplacement,
    ReviewOperationError,
    ReviewTimeserieReplacement,
)
from app.api.v1.ai_change_sets.schemas import (
    ApplyOutcome,
    ChangeSetDetail,
    ChangeSetOperationDetail,
    ChangeSetStatus,
    ChangeSetSummary,
    ExecutionResult,
    FrozenValues,
    FrozenValuesSummary,
    NodeReplacement,
    OperationError,
    OperationReplacement,
    ReplacementReport,
    ReviewChannelName,
    TimeserieReplacement,
)
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import Scenario
from app.api.v1.org_twin_structure.schemas import GraphNodePatchRequest
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.service import get_active_organisation
from app.api.v1.users.models import User
from app.core.config import Settings

_PATCH_FIELD_ALIASES = {
    name: field.alias
    for name, field in GraphNodePatchRequest.model_fields.items()
    if field.alias is not None
}


def get_change_set(
    session: Session, change_set_key: str, *, organisation_key: str | None = None
) -> AiChangeSet:
    """The change set with this key in an active organisation, else 404.

    With `organisation_key` the change set must belong to that organisation.
    """
    query = (
        select(AiChangeSet)
        .join(Organisation, Organisation.organisation_id == AiChangeSet.organisation_id)
        .where(
            AiChangeSet.change_set_key == change_set_key,
            Organisation.deleted_time.is_(None),
        )
    )
    if organisation_key is not None:
        query = query.where(Organisation.organisation_key == organisation_key)
    change_set = session.scalar(query)
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
    include_unscoped: bool = False,
) -> list[ChangeSetSummary]:
    """An organisation's change sets, newest first, at most `limit`.

    `scenario_key` filters on the derived scenario reference and must name an
    active scenario of the organisation. `include_unscoped` adds the change
    sets without a scenario reference to that filter.
    """
    organisation = get_active_organisation(session, organisation_key)
    query = _summary_query().where(
        AiChangeSet.organisation_id == organisation.organisation_id
    )
    if status_filter is not None:
        query = query.where(AiChangeSet.status == status_filter)
    if scenario_key is not None:
        org_states_service.get_scenario(session, organisation_key, scenario_key)
        scoped = and_(
            Scenario.scenario_key == scenario_key, Scenario.deleted_time.is_(None)
        )
        query = query.where(
            or_(scoped, AiChangeSet.scenario_id.is_(None))
            if include_unscoped
            else scoped
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


def organisation_key_of(session: Session, change_set_key: str) -> str:
    """The organisation key of a change set in an active organisation, else 404."""
    organisation_key = session.scalar(
        select(Organisation.organisation_key)
        .join(AiChangeSet, AiChangeSet.organisation_id == Organisation.organisation_id)
        .where(
            AiChangeSet.change_set_key == change_set_key,
            Organisation.deleted_time.is_(None),
        )
    )
    if organisation_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Change set not found.",
        )
    return organisation_key


def change_set_detail(session: Session, change_set: AiChangeSet) -> ChangeSetDetail:
    return _detail(
        change_set,
        change_set_summary(session, change_set),
        _operation_rows(session, change_set),
    )


def change_set_review(
    session: Session, change_set_key: str, *, settings: Settings
) -> tuple[ChangeSetDetail, ReplacementReport]:
    """The detail with the replacement report, as the MCP review returns them.

    Loaded and recomputed as `review_detail` does, so the report's
    `review_fingerprint` is the one apply compares.
    """
    change_set, summary, rows, report = _load_review(
        session, change_set_key, organisation_key=None, settings=settings
    )
    return _detail(change_set, summary, rows), report


def user_names(session: Session, user_ids: Iterable[int | None]) -> dict[int, str]:
    """Names of the creators and reviewers, deleted Users included."""
    ids = {user_id for user_id in user_ids if user_id is not None}
    if not ids:
        return {}
    return dict(
        session.execute(select(User.user_id, User.name).where(User.user_id.in_(ids)))
        .tuples()
        .all()
    )


def review_list_item(
    summary: ChangeSetSummary, names: Mapping[int, str]
) -> ChangeSetListItem:
    """A summary for the review API; `names` maps the User ids to names."""
    return ChangeSetListItem(
        **summary.model_dump(exclude={"organisation_key"}),
        created_by_name=names[summary.created_by],
        reviewed_by_name=(
            names[summary.reviewed_by] if summary.reviewed_by is not None else None
        ),
    )


def review_detail(
    session: Session,
    organisation_key: str,
    change_set_key: str,
    *,
    settings: Settings,
) -> ChangeSetReviewDetail:
    """The review detail with replacement flags recomputed against current data.

    It is loaded as `_load_review` describes. A stored operation that no
    longer parses raises.
    """
    change_set, summary, rows, report = _load_review(
        session, change_set_key, organisation_key=organisation_key, settings=settings
    )
    names = user_names(session, (summary.created_by, summary.reviewed_by))
    return ChangeSetReviewDetail(
        **review_list_item(summary, names).model_dump(),
        operations=[
            _review_operation(row, replacement)
            for row, replacement in zip(rows, report.operations, strict=True)
        ],
        review_fingerprint=report.review_fingerprint,
        validation_result=(
            ReviewExecutionResult.model_validate(change_set.validation_result)
            if change_set.validation_result is not None
            else None
        ),
        applied_result=(
            ReviewApplyOutcome.model_validate(change_set.applied_result)
            if change_set.applied_result is not None
            else None
        ),
    )


def _load_review(
    session: Session,
    change_set_key: str,
    *,
    organisation_key: str | None,
    settings: Settings,
) -> tuple[
    AiChangeSet, ChangeSetSummary, list[AiChangeSetOperation], ReplacementReport
]:
    """The change set, its summary, operation rows and replacement report.

    Every read, the lookup included, runs under the change-set statement
    timeout. The change set, its summary and its operation rows come from one
    statement, and the flags are computed from exactly those rows, so a draft
    edited meanwhile cannot make any part of the result disagree. A stored
    operation that no longer parses raises.
    """
    engine.set_statement_timeout(session, settings)
    change_set = get_change_set(
        session, change_set_key, organisation_key=organisation_key
    )
    results = session.execute(
        _summary_query()
        .add_columns(AiChangeSetOperation)
        .outerjoin(
            AiChangeSetOperation,
            AiChangeSetOperation.change_set_id == AiChangeSet.change_set_id,
        )
        .where(AiChangeSet.change_set_id == change_set.change_set_id)
        .order_by(AiChangeSetOperation.position)
        .execution_options(populate_existing=True)
    ).all()
    summary = _summary(*results[0][:4])
    rows = [result[4] for result in results if result[4] is not None]
    report = engine.compute_replacements(
        session,
        change_set,
        settings=settings,
        operations=[engine.staged_operation(row) for row in rows],
    )
    return change_set, summary, rows, report


def _detail(
    change_set: AiChangeSet,
    summary: ChangeSetSummary,
    rows: Sequence[AiChangeSetOperation],
) -> ChangeSetDetail:
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


def _review_operation(
    row: AiChangeSetOperation, replacement: OperationReplacement
) -> ChangeSetReviewOperation:
    frozen = (
        FrozenValues.model_validate(row.frozen_values)
        if row.frozen_values is not None
        else None
    )
    return ChangeSetReviewOperation(
        position=row.position,
        type=row.op_type,
        ref=row.ref,
        operation=_operation_json(row),
        error=(
            ReviewOperationError.model_validate(row.error)
            if row.error is not None
            else None
        ),
        frozen_values=(
            ReviewFrozenValues(
                **_frozen_summary(frozen).model_dump(),
                values=(
                    frozen.values
                    if len(frozen.values) <= INLINE_FROZEN_VALUES_LIMIT
                    else None
                ),
            )
            if frozen is not None
            else None
        ),
        replaces_existing=replacement.replaces_existing,
        replaces=_review_replacement(replacement.summary),
    )


def _review_replacement(
    summary: NodeReplacement | TimeserieReplacement | None,
) -> ReviewNodeReplacement | ReviewTimeserieReplacement | None:
    match summary:
        case None:
            return None
        case NodeReplacement(fields=dict() as fields):
            # The engine names the patched fields by attribute; the review
            # names them as the operation's payload does.
            return ReviewNodeReplacement.model_validate(
                {
                    **summary.model_dump(),
                    "fields": {
                        _PATCH_FIELD_ALIASES.get(name, name): value
                        for name, value in fields.items()
                    },
                }
            )
        case NodeReplacement():
            return ReviewNodeReplacement.model_validate(summary.model_dump())
        case TimeserieReplacement():
            return ReviewTimeserieReplacement.model_validate(summary.model_dump())


def _operation_rows(
    session: Session, change_set: AiChangeSet
) -> Sequence[AiChangeSetOperation]:
    return session.scalars(
        select(AiChangeSetOperation)
        .where(AiChangeSetOperation.change_set_id == change_set.change_set_id)
        .order_by(AiChangeSetOperation.position)
    ).all()


def _operation_json(row: AiChangeSetOperation) -> dict[str, Any]:
    operation: dict[str, Any] = {"type": row.op_type}
    if row.ref is not None:
        operation["ref"] = row.ref
    operation.update(row.payload)
    return operation


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
        reviewed_via=cast(ReviewChannelName | None, change_set.reviewed_via),
        review_client_id=change_set.review_client_id,
        review_client_name=change_set.review_client_name,
    )


def _operation_details(
    rows: Sequence[AiChangeSetOperation],
) -> list[ChangeSetOperationDetail]:
    details: list[ChangeSetOperationDetail] = []
    for row in rows:
        details.append(
            ChangeSetOperationDetail(
                position=row.position,
                type=row.op_type,
                ref=row.ref,
                operation=_operation_json(row),
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
