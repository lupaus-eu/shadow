"""AI change-set engine (ADR-015).

The engine stages typed operations, resolves `$ref` symbols in order and runs
operations only through the owning domains' `*_in_transaction` cores. It never
writes another domain's tables itself.

- `dry_run` executes operations in a fresh session guarded against commit and
  always rolls back. Without SAVEPOINTs it stops at the first failing
  operation.
- `compute_replacements` flags, read-only and against current data, every
  operation that replaces data that existed before the change set, and hashes
  the flags, summaries and per-target checksums into the review fingerprint.
- `submit_change_set` re-validates and freezes generated values.
- `apply_change_set` is the human apply, from the Metrics tab or an approved
  MCP call: one transaction under the change-set row lock, the fingerprint
  check, re-validation, execution and one commit. The step alone decides
  whether a failure marks the change set `failed`.
- `reject_change_set` is the human reject under the same row lock.

Apply and reject record the reviewer with the `ReviewChannel` they came
through.

Only `apply_change_set` commits; the caller commits every other change.
"""

import hashlib
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as dt_date
from typing import Any, Literal
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.ai_change_sets.models import AiChangeSet, AiChangeSetOperation
from app.api.v1.ai_change_sets.schemas import (
    MAX_CHANGE_SET_OPERATIONS,
    MAX_CHANGE_SET_VALUES,
    OPERATION_ADAPTER,
    REF_KIND_BY_OPERATION_TYPE,
    ApplyOutcome,
    ApplyStep,
    ChangeSetOperation,
    CopyScenarioOperation,
    CreateDerivedMetricOperation,
    CreateEdgeOperation,
    CreateEventOperation,
    CreateNodeOperation,
    CreateOrgStateOperation,
    CreateScenarioOperation,
    CreateTimeserieOperation,
    ExecutionResult,
    FrozenValues,
    GenerateTimeserieValuesOperation,
    NodeReplacement,
    OperationError,
    OperationReplacement,
    OperationResult,
    PatchNodeOperation,
    RefKind,
    ReplacementReport,
    ReviewChannelName,
    SetTimeserieValuesOperation,
    TimeserieReplacement,
    operation_value_count,
)
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import Scenario
from app.api.v1.org_states.schemas import (
    TimeserieValueRequest,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.schemas import STORED_GRAPH_PAYLOAD
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.service import get_active_organisation
from app.api.v1.timeserie_generation.generator import (
    GENERATOR_VERSION,
    TimeserieGenerationError,
    generate,
)
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

LOCK_NOT_AVAILABLE = "55P03"
QUERY_CANCELED = "57014"
_PRE_EXECUTION_STEPS: frozenset[ApplyStep] = frozenset(
    {"lock", "status", "fingerprint"}
)
_KIND_WITH_ARTICLE: dict[RefKind, str] = {
    "scenario": "a scenario",
    "org_state": "an organisation state",
    "event": "an event",
    "derived_metric": "a derived metric",
}

type ApplyErrorCode = Literal[
    "not_submitted",
    "review_stale",
    "apply_in_progress",
    "apply_unavailable",
    "apply_failed",
]


@dataclass(frozen=True)
class ReviewChannel:
    """How a human reviews a change set, recorded with the reviewer.

    `web` is the Metrics tab. `mcp` is an MCP client call the human approved;
    its client is copied like the staging client, as a plain value.
    """

    via: ReviewChannelName
    client_id: str | None = None
    client_name: str | None = None

    @classmethod
    def web(cls) -> "ReviewChannel":
        return cls("web")

    @classmethod
    def mcp(cls, client_id: str, client_name: str) -> "ReviewChannel":
        return cls("mcp", client_id, client_name)

    def audit_values(self) -> dict[str, str | None]:
        return {
            "reviewed_via": self.via,
            "review_client_id": self.client_id,
            "review_client_name": self.client_name,
        }


@dataclass(frozen=True)
class StagedOperation:
    """An operation at its change-set position, with values frozen on submit."""

    position: int
    operation: ChangeSetOperation
    frozen_values: FrozenValues | None = None


class DryRunCommitError(RuntimeError):
    """A dry-run tried to commit; dry-runs always roll back."""


class ReferenceResolutionError(Exception):
    """A `$ref` symbol that is undeclared, redeclared or of the wrong kind."""

    def __init__(self, message: str, *, position: int | None = None) -> None:
        super().__init__(message)
        self.position = position


class ChangeSetApplyError(Exception):
    """A rejected or failed apply, or a reject that could not run.

    `not_submitted`, `review_stale`, `apply_in_progress` and
    `apply_unavailable` come from the lock, status or fingerprint steps and
    never change the status; a reject raises only these, without
    `review_stale`. `apply_failed` comes from re-validation,
    execution or commit; the change set was then marked `failed` unless a
    concurrent apply had already changed it (`change_set_status`).
    """

    def __init__(
        self,
        code: ApplyErrorCode,
        message: str,
        *,
        step: ApplyStep,
        change_set_status: str | None = None,
        outcome: ApplyOutcome | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ApplyErrorCode = code
        self.message = message
        self.step: ApplyStep = step
        self.change_set_status = change_set_status
        self.outcome = outcome

    @property
    def retryable(self) -> bool:
        return self.code in {"apply_in_progress", "apply_unavailable"}

    @property
    def status_code(self) -> int:
        if self.code == "apply_unavailable":
            return status.HTTP_503_SERVICE_UNAVAILABLE
        return status.HTTP_409_CONFLICT


class _OperationsFailed(Exception):
    def __init__(self, result: ExecutionResult) -> None:
        super().__init__("A change-set operation failed.")
        self.result = result


@dataclass(frozen=True)
class _DeclaredRef:
    kind: RefKind
    position: int
    # The scenario the referenced row belongs to; None for a scenario ref.
    scenario_key: str | None


# Staging, for the MCP write tools. Edits lock the change-set row so concurrent
# edits of one draft serialise; the caller commits.


def create_change_set(
    session: Session,
    organisation_key: str,
    *,
    title: str,
    rationale: str | None,
    created_by: int,
    grant_id: int | None,
    client_id: str,
    client_name: str,
) -> AiChangeSet:
    organisation = get_active_organisation(session, organisation_key)
    stripped_title = title.strip()
    if not stripped_title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Change set title must not be blank.",
        )
    change_set = AiChangeSet(
        change_set_key=f"change_set_{uuid4().hex}",
        organisation_id=organisation.organisation_id,
        title=stripped_title,
        rationale=(rationale or "").strip() or None,
        status="draft",
        grant_id=grant_id,
        client_id=client_id,
        client_name=client_name,
        created_by=created_by,
    )
    session.add(change_set)
    session.flush()
    return change_set


def load_operations(session: Session, change_set: AiChangeSet) -> list[StagedOperation]:
    return [_staged(row) for row in _operation_rows(session, change_set)]


def staged_operation(row: AiChangeSetOperation) -> StagedOperation:
    """Parse a stored operation row; a row that no longer parses raises."""
    return _staged(row)


def add_operations(
    session: Session,
    change_set: AiChangeSet,
    operations: Sequence[ChangeSetOperation],
    actor_user_id: int,
) -> list[AiChangeSetOperation]:
    """Append operations to a draft and recompute its scenario reference."""
    change_set = _lock_change_set(session, change_set.change_set_id)
    _ensure_draft(change_set)
    if not operations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide at least one operation.",
        )
    rows = _operation_rows(session, change_set)
    existing = [_staged(row) for row in rows]
    next_position = rows[-1].position + 1 if rows else 0
    added = [
        StagedOperation(next_position + index, operation)
        for index, operation in enumerate(operations)
    ]
    staged = existing + added
    ensure_operation_limits([item.operation for item in staged])
    try:
        validate_references(staged)
    except ReferenceResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    new_rows = [
        AiChangeSetOperation(
            change_set_id=change_set.change_set_id,
            position=item.position,
            ref=_declared_symbol(item.operation),
            op_type=item.operation.type,
            payload=_payload_json(item.operation),
        )
        for item in added
    ]
    session.add_all(new_rows)
    _operations_changed(session, change_set, rows, staged, actor_user_id)
    session.flush()
    return new_rows


def remove_operation(
    session: Session,
    change_set: AiChangeSet,
    position: int,
    actor_user_id: int,
) -> None:
    """Remove one operation of a draft; later positions keep their numbers."""
    change_set = _lock_change_set(session, change_set.change_set_id)
    _ensure_draft(change_set)
    rows = _operation_rows(session, change_set)
    row = next((item for item in rows if item.position == position), None)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found.",
        )
    remaining = [item for item in rows if item is not row]
    staged = [_staged(item) for item in remaining]
    try:
        validate_references(staged)
    except ReferenceResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Operation {position} cannot be removed. {exc}",
        ) from exc
    session.delete(row)
    _operations_changed(session, change_set, remaining, staged, actor_user_id)
    session.flush()


def discard_change_set(
    session: Session, change_set: AiChangeSet, actor_user_id: int
) -> AiChangeSet:
    """Discard a draft; its operations are kept as the record."""
    change_set = _lock_change_set(session, change_set.change_set_id)
    _ensure_draft(change_set)
    change_set.status = "discarded"
    _touch(change_set, actor_user_id)
    session.flush()
    return change_set


def ensure_operation_limits(operations: Sequence[ChangeSetOperation]) -> None:
    if len(operations) > MAX_CHANGE_SET_OPERATIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"A change set has at most {MAX_CHANGE_SET_OPERATIONS} operations; "
                f"this one would have {len(operations)}."
            ),
        )
    value_count = sum(operation_value_count(operation) for operation in operations)
    if value_count > MAX_CHANGE_SET_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"A change set sets or generates at most {MAX_CHANGE_SET_VALUES} "
                f"timeserie values; this one would have {value_count}."
            ),
        )


def validate_references(
    operations: Sequence[StagedOperation],
) -> dict[str, _DeclaredRef]:
    """Check every `$ref` use against the refs declared by earlier operations."""
    declared: dict[str, _DeclaredRef] = {}
    for item in operations:
        try:
            _check_references(item.operation, declared)
        except ReferenceResolutionError as exc:
            raise ReferenceResolutionError(
                f"Operation {item.position}: {exc}", position=item.position
            ) from exc
        _declare(item, declared)
    return declared


def derive_scenario_id(
    session: Session,
    organisation_id: int,
    operations: Sequence[ChangeSetOperation],
) -> int | None:
    """The one existing scenario all operations target, otherwise None.

    A change set that creates or copies a scenario, or touches several
    scenarios, has no scenario reference.
    """
    scenario_keys: set[str] = set()
    for operation in operations:
        if isinstance(operation, CreateScenarioOperation | CopyScenarioOperation):
            return None
        scenario_keys.add(operation.scenario_key)
    if len(scenario_keys) != 1:
        return None
    (scenario_key,) = scenario_keys
    if scenario_key.startswith("$"):
        return None
    return session.scalar(
        select(Scenario.scenario_id).where(
            Scenario.organisation_id == organisation_id,
            Scenario.scenario_key == scenario_key,
            Scenario.deleted_time.is_(None),
        )
    )


def scenario_key_of(session: Session, change_set: AiChangeSet) -> str | None:
    if change_set.scenario_id is None:
        return None
    return session.scalar(
        select(Scenario.scenario_key).where(
            Scenario.scenario_id == change_set.scenario_id
        )
    )


# Execution.


def set_statement_timeout(session: Session, settings: Settings) -> None:
    """Bound every statement of the session's current transaction."""
    _set_local(
        session, "statement_timeout", settings.ai_change_set_statement_timeout_ms
    )


def execute_operations(
    session: Session,
    organisation: Organisation,
    ops: Sequence[StagedOperation],
    actor_user_id: int,
) -> ExecutionResult:
    """Resolve refs in order and run each operation's domain core.

    Execution stops at the first failing operation, because without a
    SAVEPOINT a database error aborts the transaction. Domain errors and the
    known database errors become that operation's error; any other exception
    propagates. The caller commits or rolls back.
    """
    declared: dict[str, _DeclaredRef] = {}
    keys: dict[str, str] = {}
    results: list[OperationResult] = []
    failed = False
    for item in ops:
        operation = item.operation
        if failed:
            results.append(
                OperationResult(
                    position=item.position, op_type=operation.type, status="not_run"
                )
            )
            continue
        try:
            _check_references(operation, declared)
            scenario_key, key = _run_operation(
                session, organisation.organisation_key, item, keys, actor_user_id
            )
        except Exception as exc:
            error = _operation_error(exc)
            if error is None:
                raise
            results.append(
                OperationResult(
                    position=item.position,
                    op_type=operation.type,
                    status="error",
                    error=error,
                )
            )
            failed = True
            continue
        symbol = _declare(item, declared)
        if symbol is not None:
            keys[symbol] = key
        results.append(
            OperationResult(
                position=item.position,
                op_type=operation.type,
                status="ok",
                scenario_key=scenario_key,
                key=key,
            )
        )
    return ExecutionResult(ok=not failed, operations=results, refs=keys)


def dry_run(
    session_factory: Callable[[], Session],
    organisation_key: str,
    ops: Sequence[StagedOperation],
    actor_user_id: int,
    *,
    settings: Settings | None = None,
) -> ExecutionResult:
    """Execute the operations in a fresh session and always roll back.

    A `before_commit` guard makes any commit attempt fail. The session is
    rolled back and cleared before the result is returned, so a failure that
    is not a database error leaves no pending objects behind.
    """
    settings = settings or get_settings()
    session = session_factory()

    def reject_commit(_session: Session) -> None:
        raise DryRunCommitError("A change-set dry-run must not commit.")

    event.listen(session, "before_commit", reject_commit)
    try:
        set_statement_timeout(session, settings)
        organisation = get_active_organisation(session, organisation_key)
        return execute_operations(session, organisation, ops, actor_user_id)
    finally:
        session.rollback()
        session.expunge_all()
        session.close()


def validate_change_set(
    session: Session,
    session_factory: Callable[[], Session],
    change_set: AiChangeSet,
    actor_user_id: int,
    *,
    settings: Settings | None = None,
) -> ExecutionResult:
    """Dry-run a draft and store the result on it and its operations.

    Pass a session whose transaction has not written or locked rows; commit
    change-set edits first.
    """
    _ensure_no_earlier_writes(session)
    change_set = _lock_change_set(session, change_set.change_set_id)
    _ensure_draft(change_set)
    rows = _operation_rows(session, change_set)
    result = dry_run(
        session_factory,
        _organisation_key(session, change_set),
        [_staged(row) for row in rows],
        actor_user_id,
        settings=settings,
    )
    _store_validation(change_set, rows, result, actor_user_id)
    session.flush()
    return result


def submit_change_set(
    session: Session,
    session_factory: Callable[[], Session],
    change_set: AiChangeSet,
    actor_user_id: int,
    *,
    settings: Settings | None = None,
) -> ExecutionResult:
    """Re-validate a draft, freeze its generated values and submit it.

    The values are generated once, dry-run, and frozen with the generator
    version only when every operation validates; otherwise the change set
    stays a draft with the stored validation result. Pass a session whose
    transaction has not written or locked rows; commit change-set edits first.
    """
    _ensure_no_earlier_writes(session)
    locked = _lock_change_set(session, change_set.change_set_id)
    _ensure_draft(locked)
    rows = _operation_rows(session, locked)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A change set needs at least one operation before submit.",
        )
    staged = [_with_generated_values(_staged(row)) for row in rows]
    result = dry_run(
        session_factory,
        _organisation_key(session, locked),
        staged,
        actor_user_id,
        settings=settings,
    )
    _store_validation(locked, rows, result, actor_user_id)
    if result.ok:
        for row, item in zip(rows, staged, strict=True):
            if item.frozen_values is not None:
                row.frozen_values = item.frozen_values.model_dump(
                    mode="json", by_alias=True
                )
        locked.status = "submitted"
    session.flush()
    return result


# Replacement flags.


def compute_replacements(
    session: Session,
    change_set: AiChangeSet,
    *,
    settings: Settings | None = None,
    operations: Sequence[StagedOperation] | None = None,
) -> ReplacementReport:
    """Flag operations that replace data existing before the change set.

    `patch_node`, and `set_timeserie_values` or `generate_timeserie_values` on
    a timeserie that has values, replace existing data. An operation on a row
    the change set creates earlier (a node, a timeserie, or anything in a
    scenario it creates or copies) is never flagged. Everything is read from
    current data on every call; a missing target is reported, not raised.
    The function only reads, under the change-set `statement_timeout`.
    `operations` are the change set's operations when the caller has already
    read them, so the report describes exactly those; otherwise they are read.
    """
    set_statement_timeout(session, settings or get_settings())
    organisation_key = _organisation_key(session, change_set)
    created_nodes: set[tuple[str, str]] = set()
    created_timeseries: set[tuple[str, str]] = set()
    org_state_dates: dict[str, tuple[str, dt_date]] = {}
    timeserie_cache: dict[tuple[str, str], TimeserieReplacement | None] = {}
    entries: list[OperationReplacement] = []

    if operations is None:
        operations = load_operations(session, change_set)
    for item in operations:
        operation = item.operation
        summary: NodeReplacement | TimeserieReplacement | None = None
        match operation:
            case CreateNodeOperation():
                created_nodes.add((operation.scenario_key, operation.payload.id))
            case CreateTimeserieOperation():
                created_timeseries.add((operation.scenario_key, operation.payload.id))
            case CreateOrgStateOperation(ref=str() as ref):
                org_state_dates[ref] = (
                    operation.scenario_key,
                    operation.payload.target_date,
                )
            case PatchNodeOperation():
                target = (operation.scenario_key, operation.node_key)
                if not _is_ref(operation.scenario_key) and target not in created_nodes:
                    summary = _node_replacement(
                        session, organisation_key, operation, org_state_dates
                    )
            case SetTimeserieValuesOperation() | GenerateTimeserieValuesOperation():
                target = (operation.scenario_key, operation.timeserie_key)
                if (
                    not _is_ref(operation.scenario_key)
                    and target not in created_timeseries
                ):
                    if target not in timeserie_cache:
                        timeserie_cache[target] = _timeserie_replacement(
                            session, organisation_key, *target
                        )
                    summary = timeserie_cache[target]
            case _:
                pass
        entries.append(
            OperationReplacement(
                position=item.position,
                op_type=operation.type,
                replaces_existing=summary is not None,
                summary=summary,
            )
        )

    return ReplacementReport(
        operations=entries,
        review_fingerprint=_sha256_hex(
            [entry.model_dump(mode="json") for entry in entries]
        ),
    )


# Human apply and reject, from the Metrics tab or an approved MCP call.


def apply_change_set(
    session: Session,
    organisation_key: str,
    change_set_key: str,
    review_fingerprint: str,
    actor_user_id: int,
    *,
    channel: ReviewChannel,
    settings: Settings | None = None,
) -> ExecutionResult:
    """Apply a submitted change set atomically; the reviewer is the actor.

    Steps, in one transaction: lock the change set (`FOR UPDATE` under
    `lock_timeout`), require `submitted`, compare the recomputed review
    fingerprint, re-validate, execute with the frozen values and commit once.
    The `lock_timeout` and `statement_timeout` stay in force for the whole
    transaction. An error in the lock, status or fingerprint steps rolls back
    and never changes the status; an error in a later step rolls back and
    then marks the change set `failed` in a new transaction, only if it is
    still `submitted`. Pass a session without pending changes.
    """
    settings = settings or get_settings()
    step: ApplyStep = "lock"
    change_set_id: int | None = None
    try:
        _set_apply_timeouts(session, settings)
        organisation = get_active_organisation(session, organisation_key)
        change_set = _lock_change_set_by_key(session, organisation, change_set_key)
        change_set_id = change_set.change_set_id

        step = "status"
        if change_set.status != "submitted":
            raise ChangeSetApplyError(
                "not_submitted",
                f"Only a submitted change set can be applied; this one is "
                f"{change_set.status}.",
                step=step,
                change_set_status=change_set.status,
            )

        step = "fingerprint"
        report = compute_replacements(session, change_set, settings=settings)
        if report.review_fingerprint != review_fingerprint:
            raise ChangeSetApplyError(
                "review_stale",
                "The data this change set replaces changed after the review was "
                "loaded. Reload the change set and confirm again.",
                step=step,
                change_set_status=change_set.status,
            )

        step = "revalidate"
        rows = _operation_rows(session, change_set)
        staged = [_staged(row) for row in rows]
        _require_frozen_values(staged)
        ensure_operation_limits([item.operation for item in staged])
        validate_references(staged)

        step = "execute"
        result = execute_operations(session, organisation, staged, actor_user_id)
        if not result.ok:
            raise _OperationsFailed(result)

        step = "commit"
        now = datetime.now(UTC)
        change_set.status = "applied"
        change_set.applied_result = ApplyOutcome(
            status="applied",
            operations=result.operations,
            refs=result.refs,
        ).model_dump(mode="json")
        change_set.reviewed_by = actor_user_id
        change_set.reviewed_time = now
        _record_channel(change_set, channel)
        change_set.modified_by = actor_user_id
        change_set.modified_time = now
        for row in rows:
            row.error = None
        session.commit()
        return result
    except ChangeSetApplyError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        if step in _PRE_EXECUTION_STEPS:
            if (
                step == "lock"
                and isinstance(exc, HTTPException)
                and exc.status_code == status.HTTP_404_NOT_FOUND
            ):
                # An unknown organisation or change set is not retryable.
                raise
            raise _pre_execution_error(
                step, exc, change_set_key, action="applied"
            ) from exc
        assert change_set_id is not None
        outcome, failing = _failed_outcome(step, exc)
        logger.info(
            "AI change set %s apply failed in step %s with %s",
            change_set_key,
            step,
            type(exc).__name__,
        )
        change_set_status = _mark_failed(
            session, change_set_id, outcome, failing, actor_user_id, channel, settings
        )
        assert outcome.error is not None
        raise ChangeSetApplyError(
            "apply_failed",
            f"The change set failed to apply and nothing was changed: "
            f"{outcome.error.message}",
            step=step,
            change_set_status=change_set_status,
            outcome=outcome,
        ) from exc


def reject_change_set(
    session: Session,
    organisation_key: str,
    change_set_key: str,
    note: str | None,
    actor_user_id: int,
    *,
    channel: ReviewChannel,
    settings: Settings | None = None,
) -> AiChangeSet:
    """Reject a submitted change set; the reviewer is recorded with the note.

    The change-set row is locked under apply's timeouts, so a reject waiting
    behind an apply returns the same codes as a second apply: the retryable
    `apply_in_progress` or `apply_unavailable`, or `not_submitted` once the
    apply has finished. The stored operations are not parsed, so a change set
    whose operations no longer parse can still be rejected. On an error the
    session is rolled back; otherwise the caller commits.
    """
    settings = settings or get_settings()
    step: ApplyStep = "lock"
    try:
        _set_apply_timeouts(session, settings)
        organisation = get_active_organisation(session, organisation_key)
        change_set = _lock_change_set_by_key(session, organisation, change_set_key)

        step = "status"
        if change_set.status != "submitted":
            raise ChangeSetApplyError(
                "not_submitted",
                f"Only a submitted change set can be rejected; this one is "
                f"{change_set.status}.",
                step=step,
                change_set_status=change_set.status,
            )
        now = datetime.now(UTC)
        change_set.status = "rejected"
        change_set.reviewed_by = actor_user_id
        change_set.reviewed_time = now
        change_set.review_note = note
        _record_channel(change_set, channel)
        change_set.modified_by = actor_user_id
        change_set.modified_time = now
        session.flush()
        return change_set
    except ChangeSetApplyError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        if isinstance(exc, HTTPException) and exc.status_code < 500:
            raise
        raise _pre_execution_error(
            step, exc, change_set_key, action="rejected"
        ) from exc


# Internal helpers.


def _run_operation(
    session: Session,
    organisation_key: str,
    item: StagedOperation,
    keys: Mapping[str, str],
    actor_user_id: int,
) -> tuple[str, str]:
    """Run one operation; return its scenario key and the key it created or
    changed."""
    operation = item.operation
    match operation:
        case CreateScenarioOperation():
            scenario = org_states_service.create_scenario_in_transaction(
                session, organisation_key, operation.payload, actor_user_id
            )
            return scenario.scenario_key, scenario.scenario_key
        case CopyScenarioOperation():
            payload = operation.payload.model_copy(
                update={
                    "source_scenario_id": _resolve(
                        operation.payload.source_scenario_id, keys
                    ),
                    "source_org_state_id": _resolve(
                        operation.payload.source_org_state_id, keys
                    ),
                }
            )
            scenario = org_states_service.copy_scenario_in_transaction(
                session, organisation_key, payload, actor_user_id
            )
            return scenario.scenario_key, scenario.scenario_key
        case CreateOrgStateOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            org_state = org_states_service.create_org_state_in_transaction(
                session,
                organisation_key,
                scenario_key,
                operation.payload,
                actor_user_id,
            )
            return scenario_key, org_state.org_state_key
        case CreateEventOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            created_event = org_states_service.create_event_in_transaction(
                session,
                organisation_key,
                scenario_key,
                operation.payload,
                actor_user_id,
            )
            return scenario_key, created_event.event_key
        case CreateTimeserieOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            timeserie = org_states_service.create_timeserie_in_transaction(
                session,
                organisation_key,
                scenario_key,
                operation.payload,
                actor_user_id,
            )
            return scenario_key, timeserie.timeserie_key
        case SetTimeserieValuesOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            timeserie = org_states_service.replace_timeserie_values_in_transaction(
                session,
                organisation_key,
                scenario_key,
                operation.timeserie_key,
                operation.payload,
                actor_user_id,
            )
            return scenario_key, timeserie.timeserie_key
        case GenerateTimeserieValuesOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            points = (
                item.frozen_values.values
                if item.frozen_values is not None
                else generate(operation.spec)
            )
            timeserie = org_states_service.replace_timeserie_values_in_transaction(
                session,
                organisation_key,
                scenario_key,
                operation.timeserie_key,
                TimeserieValuesPatchRequest(
                    values=[
                        TimeserieValueRequest(date=point.date, value=point.value)
                        for point in points
                    ]
                ),
                actor_user_id,
            )
            return scenario_key, timeserie.timeserie_key
        case CreateDerivedMetricOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            timeserie = org_states_service.create_derived_metric_in_transaction(
                session,
                organisation_key,
                scenario_key,
                operation.payload,
                actor_user_id,
            )
            return scenario_key, timeserie.timeserie_key
        case CreateNodeOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            node = org_twin_structure_service.create_graph_node_in_transaction(
                session,
                organisation_key,
                scenario_key,
                _resolve(operation.org_state_key, keys),
                operation.payload,
                actor_user_id,
            )
            return scenario_key, node.node_key
        case PatchNodeOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            node_payload = operation.payload
            linked = {
                name: _resolve(value, keys)
                for name, value in (
                    ("timeserie_id", node_payload.timeserie_id),
                    ("timeserie_secondary_id", node_payload.timeserie_secondary_id),
                )
                if value is not None
            }
            node = org_twin_structure_service.patch_graph_node_in_transaction(
                session,
                organisation_key,
                scenario_key,
                _resolve(operation.org_state_key, keys),
                operation.node_key,
                node_payload.model_copy(update=linked),
                actor_user_id,
            )
            return scenario_key, node.node_key
        case CreateEdgeOperation():
            scenario_key = _resolve(operation.scenario_key, keys)
            edge = org_twin_structure_service.create_graph_edge_in_transaction(
                session,
                organisation_key,
                scenario_key,
                _resolve(operation.org_state_key, keys),
                operation.payload,
                actor_user_id,
            )
            return scenario_key, edge.edge_key


def _reference_fields(
    operation: ChangeSetOperation,
) -> list[tuple[str, str, RefKind, str | None]]:
    """(field, value, expected ref kind, scenario the referenced row must be in)."""
    match operation:
        case CreateScenarioOperation():
            return []
        case CopyScenarioOperation():
            source_scenario = operation.payload.source_scenario_id
            return [
                ("payload.sourceScenarioId", source_scenario, "scenario", None),
                (
                    "payload.sourceOrgStateId",
                    operation.payload.source_org_state_id,
                    "org_state",
                    source_scenario,
                ),
            ]
        case CreateNodeOperation() | CreateEdgeOperation() | PatchNodeOperation():
            scenario_key = operation.scenario_key
            fields: list[tuple[str, str, RefKind, str | None]] = [
                ("scenario_key", scenario_key, "scenario", None),
                ("org_state_key", operation.org_state_key, "org_state", scenario_key),
            ]
            if isinstance(operation, PatchNodeOperation):
                for label, value in (
                    ("payload.timeserieId", operation.payload.timeserie_id),
                    (
                        "payload.timeserieSecondaryId",
                        operation.payload.timeserie_secondary_id,
                    ),
                ):
                    if value is not None:
                        fields.append((label, value, "derived_metric", scenario_key))
            return fields
        case _:
            return [("scenario_key", operation.scenario_key, "scenario", None)]


def _check_references(
    operation: ChangeSetOperation,
    declared: Mapping[str, _DeclaredRef],
) -> None:
    for field, value, kind, scenario_key in _reference_fields(operation):
        if not _is_ref(value):
            continue
        ref = declared.get(value)
        if ref is None:
            raise ReferenceResolutionError(
                f"{field} uses {value}, which no earlier operation declares."
            )
        if ref.kind != kind:
            raise ReferenceResolutionError(
                f"{field} uses {value}, which names {_KIND_WITH_ARTICLE[ref.kind]} "
                f"created by operation {ref.position}; {field} needs "
                f"{_KIND_WITH_ARTICLE[kind]}."
            )
        if scenario_key is not None and ref.scenario_key != scenario_key:
            raise ReferenceResolutionError(
                f"{field} uses {value}, which belongs to scenario "
                f"{ref.scenario_key}, not {scenario_key}."
            )
    symbol = _declared_symbol(operation)
    if symbol is not None and symbol in declared:
        raise ReferenceResolutionError(
            f"ref {symbol} is already declared by operation "
            f"{declared[symbol].position}."
        )


def _declare(item: StagedOperation, declared: dict[str, _DeclaredRef]) -> str | None:
    operation = item.operation
    symbol = _declared_symbol(operation)
    if symbol is None:
        return None
    match operation:
        case (
            CreateOrgStateOperation()
            | CreateEventOperation()
            | CreateDerivedMetricOperation()
        ):
            scenario_key: str | None = operation.scenario_key
        case _:
            scenario_key = None
    declared[symbol] = _DeclaredRef(
        kind=REF_KIND_BY_OPERATION_TYPE[operation.type],
        position=item.position,
        scenario_key=scenario_key,
    )
    return symbol


def _declared_symbol(operation: ChangeSetOperation) -> str | None:
    match operation:
        case (
            CreateScenarioOperation()
            | CopyScenarioOperation()
            | CreateOrgStateOperation()
            | CreateEventOperation()
            | CreateDerivedMetricOperation()
        ):
            return operation.ref
        case _:
            return None


def _resolve(value: str, keys: Mapping[str, str]) -> str:
    if not _is_ref(value):
        return value
    resolved = keys.get(value)
    if resolved is None:
        raise ReferenceResolutionError(
            f"{value} has no key yet; it must be declared by an earlier operation."
        )
    return resolved


def _is_ref(value: str) -> bool:
    return value.startswith("$")


def _operation_error(exc: Exception) -> OperationError | None:
    if isinstance(exc, HTTPException):
        return OperationError(
            code="domain_error", message=str(exc.detail), status_code=exc.status_code
        )
    if isinstance(exc, ReferenceResolutionError):
        return OperationError(
            code="invalid_reference",
            message=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if isinstance(exc, TimeserieGenerationError):
        return OperationError(
            code="generation_error",
            message=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if isinstance(exc, ValidationError):
        # Without the inputs, which may be large or contain tool arguments.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in exc.errors(include_url=False, include_input=False)
        )
        return OperationError(
            code="invalid_operation",
            message=problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    # Database messages can contain SQL parameters, so they are not repeated.
    if isinstance(exc, IntegrityError):
        return OperationError(
            code="conflict",
            message="The operation conflicts with existing data.",
            status_code=status.HTTP_409_CONFLICT,
        )
    sqlstate = _sqlstate(exc)
    if sqlstate == LOCK_NOT_AVAILABLE:
        return OperationError(
            code="lock_timeout",
            message=(
                "The operation waited longer than the lock timeout for data "
                "another transaction holds."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    if sqlstate == QUERY_CANCELED:
        return OperationError(
            code="statement_timeout",
            message="The operation exceeded the statement timeout.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return None


def _sqlstate(exc: BaseException) -> str | None:
    if not isinstance(exc, DBAPIError):
        return None
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return sqlstate if isinstance(sqlstate, str) else None


def _pre_execution_error(
    step: ApplyStep,
    exc: Exception,
    change_set_key: str,
    *,
    action: Literal["applied", "rejected"],
) -> ChangeSetApplyError:
    if step == "lock" and _sqlstate(exc) == LOCK_NOT_AVAILABLE:
        return ChangeSetApplyError(
            "apply_in_progress",
            "Another transaction, normally a concurrent apply, holds this change "
            "set. Try again shortly.",
            step=step,
        )
    logger.warning(
        "AI change set %s was left unchanged after %s in step %s",
        change_set_key,
        type(exc).__name__,
        step,
    )
    return ChangeSetApplyError(
        "apply_unavailable",
        f"The change set could not be {action} right now. Try again shortly.",
        step=step,
    )


def _failed_outcome(
    step: ApplyStep, exc: Exception
) -> tuple[ApplyOutcome, OperationResult | None]:
    """The stored outcome and, for an operation failure, the failing operation."""
    if isinstance(exc, _OperationsFailed):
        failing = next(item for item in exc.result.operations if item.status == "error")
        assert failing.error is not None
        error = failing.error.model_copy(
            update={"message": f"Operation {failing.position}: {failing.error.message}"}
        )
        operations = [
            item.model_copy(update={"scenario_key": None, "key": None})
            for item in exc.result.operations
        ]
        return (
            ApplyOutcome(
                status="failed", step=step, error=error, operations=operations, refs={}
            ),
            failing,
        )
    error = _operation_error(exc) or OperationError(
        code="unexpected_error",
        message=f"The {step} step failed unexpectedly.",
    )
    return (
        ApplyOutcome(status="failed", step=step, error=error, operations=[], refs={}),
        None,
    )


def _mark_failed(
    session: Session,
    change_set_id: int,
    outcome: ApplyOutcome,
    failing: OperationResult | None,
    actor_user_id: int,
    channel: ReviewChannel,
    settings: Settings,
) -> str | None:
    """Mark a still-submitted change set failed in a new transaction.

    The conditional update never overwrites a concurrent successful apply.
    Returns the change set's status afterwards.
    """
    now = datetime.now(UTC)
    try:
        _set_apply_timeouts(session, settings)
        marked = session.scalar(
            update(AiChangeSet)
            .where(
                AiChangeSet.change_set_id == change_set_id,
                AiChangeSet.status == "submitted",
            )
            .values(
                status="failed",
                applied_result=outcome.model_dump(mode="json"),
                reviewed_by=actor_user_id,
                reviewed_time=now,
                **channel.audit_values(),
                modified_by=actor_user_id,
                modified_time=now,
            )
            .returning(AiChangeSet.change_set_id)
            .execution_options(synchronize_session=False)
        )
        if marked is not None and failing is not None and failing.error is not None:
            session.execute(
                update(AiChangeSetOperation)
                .where(
                    AiChangeSetOperation.change_set_id == change_set_id,
                    AiChangeSetOperation.position == failing.position,
                )
                .values(error=failing.error.model_dump(mode="json"))
                .execution_options(synchronize_session=False)
            )
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning(
            "AI change set %s could not be marked failed after %s",
            change_set_id,
            type(exc).__name__,
        )
    try:
        return session.scalar(
            select(AiChangeSet.status).where(AiChangeSet.change_set_id == change_set_id)
        )
    finally:
        session.rollback()


def _record_channel(change_set: AiChangeSet, channel: ReviewChannel) -> None:
    change_set.reviewed_via = channel.via
    change_set.review_client_id = channel.client_id
    change_set.review_client_name = channel.client_name


def _set_apply_timeouts(session: Session, settings: Settings) -> None:
    set_statement_timeout(session, settings)
    _set_local(session, "lock_timeout", settings.ai_change_set_lock_timeout_ms)


def _set_local(session: Session, name: str, milliseconds: int) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": name, "value": f"{milliseconds}ms"},
    )


def _node_replacement(
    session: Session,
    organisation_key: str,
    operation: PatchNodeOperation,
    org_state_dates: Mapping[str, tuple[str, dt_date]],
) -> NodeReplacement:
    summary = NodeReplacement(
        scenario_key=operation.scenario_key,
        org_state_key=operation.org_state_key,
        node_key=operation.node_key,
    )
    try:
        if _is_ref(operation.org_state_key):
            # An org state this change set creates in an existing scenario.
            declared = org_state_dates.get(operation.org_state_key)
            if declared is None or declared[0] != operation.scenario_key:
                return summary.model_copy(
                    update={
                        "missing": True,
                        "message": "Organisation state not found.",
                    }
                )
            target_date = declared[1]
        else:
            target_date = org_states_service.get_org_state(
                session,
                organisation_key,
                operation.scenario_key,
                operation.org_state_key,
            ).target_date
        node = org_twin_structure_service.get_graph_node_visible_at(
            session,
            organisation_key,
            operation.scenario_key,
            operation.node_key,
            target_date,
        )
    except HTTPException as exc:
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise
        return summary.model_copy(update={"missing": True, "message": str(exc.detail)})
    current = node.model_dump(mode="json")
    patched = sorted(operation.payload.model_fields_set)
    fields = {name: current[name] for name in patched}
    return summary.model_copy(
        update={"fields": fields, "checksum": _sha256_hex(fields)}
    )


def _timeserie_replacement(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
) -> TimeserieReplacement | None:
    try:
        timeserie = org_states_service.get_timeserie(
            session, organisation_key, scenario_key, timeserie_key
        )
    except HTTPException as exc:
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise
        return TimeserieReplacement(
            scenario_key=scenario_key,
            timeserie_key=timeserie_key,
            missing=True,
            message=str(exc.detail),
        )
    if not timeserie.values:
        return None
    pairs = [[value.date.isoformat(), value.value] for value in timeserie.values]
    return TimeserieReplacement(
        scenario_key=scenario_key,
        timeserie_key=timeserie_key,
        value_count=len(pairs),
        first_date=timeserie.values[0].date,
        last_date=timeserie.values[-1].date,
        checksum=_sha256_hex(pairs),
    )


def _sha256_hex(data: object) -> str:
    canonical = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _with_generated_values(item: StagedOperation) -> StagedOperation:
    operation = item.operation
    if not isinstance(operation, GenerateTimeserieValuesOperation):
        return item
    try:
        points = generate(operation.spec)
    except TimeserieGenerationError:
        # The dry-run generates again and reports the error on this operation.
        return item
    return StagedOperation(
        item.position,
        operation,
        FrozenValues(generatorVersion=GENERATOR_VERSION, values=points),
    )


def _require_frozen_values(staged: Sequence[StagedOperation]) -> None:
    for item in staged:
        if (
            isinstance(item.operation, GenerateTimeserieValuesOperation)
            and item.frozen_values is None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Operation {item.position} has no frozen generated values.",
            )


def _staged(row: AiChangeSetOperation) -> StagedOperation:
    data: dict[str, Any] = {**row.payload, "type": row.op_type}
    if row.ref is not None:
        data["ref"] = row.ref
    return StagedOperation(
        position=row.position,
        # Rows staged before the graph name and key limits must stay readable.
        operation=OPERATION_ADAPTER.validate_python(
            data, context={STORED_GRAPH_PAYLOAD: True}
        ),
        frozen_values=(
            FrozenValues.model_validate(row.frozen_values)
            if row.frozen_values is not None
            else None
        ),
    )


def _payload_json(operation: ChangeSetOperation) -> dict[str, Any]:
    # exclude_unset keeps a patch's explicit nulls apart from omitted fields.
    return operation.model_dump(
        mode="json", by_alias=True, exclude_unset=True, exclude={"type", "ref"}
    )


def _operation_rows(
    session: Session, change_set: AiChangeSet
) -> list[AiChangeSetOperation]:
    return list(
        session.scalars(
            select(AiChangeSetOperation)
            .where(AiChangeSetOperation.change_set_id == change_set.change_set_id)
            .order_by(AiChangeSetOperation.position)
        ).all()
    )


def _operations_changed(
    session: Session,
    change_set: AiChangeSet,
    rows: Sequence[AiChangeSetOperation],
    staged: Sequence[StagedOperation],
    actor_user_id: int,
) -> None:
    change_set.scenario_id = derive_scenario_id(
        session, change_set.organisation_id, [item.operation for item in staged]
    )
    # A stored dry-run result no longer describes the edited operations.
    change_set.validation_result = None
    for row in rows:
        row.error = None
    _touch(change_set, actor_user_id)


def _store_validation(
    change_set: AiChangeSet,
    rows: Sequence[AiChangeSetOperation],
    result: ExecutionResult,
    actor_user_id: int,
) -> None:
    change_set.validation_result = result.model_dump(mode="json")
    errors = {item.position: item.error for item in result.operations}
    for row in rows:
        error = errors.get(row.position)
        row.error = error.model_dump(mode="json") if error is not None else None
    _touch(change_set, actor_user_id)


def _touch(change_set: AiChangeSet, actor_user_id: int) -> None:
    change_set.modified_by = actor_user_id
    change_set.modified_time = datetime.now(UTC)


def _ensure_draft(change_set: AiChangeSet) -> None:
    if change_set.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only a draft change set can be changed or validated; this one is "
                f"{change_set.status}."
            ),
        )


def _ensure_no_earlier_writes(session: Session) -> None:
    """Refuse a dry-run after writes or row locks in the caller's transaction.

    The dry-run runs on its own connection, so it would wait until the
    statement timeout for row locks the caller holds. A change-set edit, for
    example, holds a key-share lock on its scenario row through the
    `scenario_id` foreign key, and the org-state cores lock that row for
    update. On PostgreSQL a transaction that has written or locked rows has a
    transaction id; unflushed changes would be written by the next flush.
    """
    pending = bool(
        session.new
        or session.deleted
        or any(session.is_modified(instance) for instance in session.dirty)
    )
    if not pending and session.get_bind().dialect.name == "postgresql":
        pending = (
            session.scalar(text("SELECT pg_current_xact_id_if_assigned()")) is not None
        )
    if pending:
        raise RuntimeError(
            "Validate or submit a change set in a transaction that has not "
            "written or locked rows; commit the change-set edits first."
        )


def _lock_change_set(session: Session, change_set_id: int) -> AiChangeSet:
    change_set = session.scalar(
        select(AiChangeSet)
        .where(AiChangeSet.change_set_id == change_set_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if change_set is None:
        raise _change_set_not_found()
    return change_set


def _lock_change_set_by_key(
    session: Session, organisation: Organisation, change_set_key: str
) -> AiChangeSet:
    change_set = session.scalar(
        select(AiChangeSet)
        .where(
            AiChangeSet.organisation_id == organisation.organisation_id,
            AiChangeSet.change_set_key == change_set_key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if change_set is None:
        raise _change_set_not_found()
    return change_set


def _organisation_key(session: Session, change_set: AiChangeSet) -> str:
    return session.get_one(Organisation, change_set.organisation_id).organisation_key


def _change_set_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Change set not found.",
    )
