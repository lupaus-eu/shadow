"""MCP read tools and skill prompts, scope `shadow.read` (ADR-015).

`register_read_tools` adds them to the Shadow MCP server (`app.mcp.server`),
each behind `requires_scope(READ_SCOPE)`. Read tools never change data. They
call the existing domain service functions and return the existing response
schemas, so data and errors match REST. The tool docstrings are the contract
the AI client reads. Tools that can return many timeserie values bound them and
report truncation. The prompts serve the Shadow skills' `SKILL.md` bodies to
clients without skills support.
"""

import math
from collections.abc import Callable
from datetime import date as dt_date
from typing import Annotated

from fastapi import HTTPException, status
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.v1.ai_change_sets import service as change_sets_service
from app.api.v1.ai_change_sets.schemas import (
    ChangeSetDetail,
    ChangeSetStatus,
    ChangeSetSummary,
)
from app.api.v1.mcp_oauth.service import READ_SCOPE
from app.api.v1.mcp_oauth.token_service import McpPrincipal
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.schemas import (
    EventResponse,
    OrgStateResponse,
    ScenarioResponse,
    TimeserieResponse,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.schemas import (
    GraphResponse,
    TypeCatalogWithAttributesResponse,
)
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationResponse
from app.api.v1.timeserie_generation.generator import (
    GENERATOR_VERSION,
    TimeserieGenerationError,
    generate,
)
from app.api.v1.timeserie_generation.schemas import TimeserieGenerationSpec
from app.api.v1.users import service as users_service
from app.api.v1.users.schemas import UserResponse
from app.core.config import Settings
from app.mcp.auth import requires_scope
from app.mcp.runtime import McpToolRuntime, busy_on_timeout
from app.mcp.schemas import (
    ChangeSetListResult,
    ChangeSetReview,
    GeneratedTimeseriePreview,
    TimeserieListResult,
    TimeserieValuesResult,
)
from app.mcp.skills import load_skills

READ_TOOL_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, open_world_hint=False
)
LIST_TIMESERIES_MAX_VALUES = 2_000
GET_TIMESERIE_MAX_POINTS = 1_000
PREVIEW_SAMPLE_POINTS = 5
LIST_CHANGE_SETS_MAX_ITEMS = 100

OrganisationKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        description="Organisation key: the `id` of an item of list_organisations.",
    ),
]
ScenarioKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        description="Scenario key: the `id` of an item of list_scenarios.",
    ),
]
OrgStateKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        description="Organisation state key: the `id` of an item of list_org_states.",
    ),
]
TimeserieKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        description="Timeserie key: the `id` of an item of list_timeseries.",
    ),
]


def register_read_tools(
    server: FastMCP, runtime: McpToolRuntime, settings: Settings
) -> None:
    async def whoami() -> UserResponse:
        """Return the Shadow User this connection acts for.

        The result has the User's `id`, `name`, `email` and `role` (`admin` or
        `consultant`). Every tool acts as this User; both roles may read every
        organisation.
        """
        return await runtime.run(
            lambda session, principal: users_service.get_user(
                session, principal.user_id
            )
        )

    async def list_organisations() -> list[OrganisationResponse]:
        """List all active organisations, sorted by name.

        Each item has `id`, the organisation key the other tools take, and
        `name`.
        """
        return await runtime.run(
            lambda session, _: organisations_service.list_organisations(session)
        )

    async def list_scenarios(
        organisation_key: OrganisationKey,
    ) -> list[ScenarioResponse]:
        """List the active scenarios of one organisation, sorted by name.

        Each item has `id`, the scenario key the other tools take, `name`,
        `description` and `protected`. Every organisation has the protected
        default scenario `Reality`; protected scenarios cannot be deleted or
        cleaned. An unknown or deleted organisation is an error.
        """
        return await runtime.run(
            lambda session, _: org_states_service.list_organisation_scenarios(
                session, organisation_key
            )
        )

    async def list_org_states(
        organisation_key: OrganisationKey,
        scenario_key: ScenarioKey,
    ) -> list[OrgStateResponse]:
        """List the active organisation states of one scenario by target date.

        An organisation state is a snapshot of the organisation's structure at
        its `target_date` (an ISO date). Each item has `id`, the organisation
        state key, `name`, `description` and `target_date`. An unknown or
        deleted organisation or scenario is an error.
        """
        return await runtime.run(
            lambda session, _: org_states_service.list_organisation_scenario_org_states(
                session, organisation_key, scenario_key
            )
        )

    async def get_type_catalog(
        organisation_key: OrganisationKey,
        scenario_key: ScenarioKey,
    ) -> TypeCatalogWithAttributesResponse:
        """Return the organisation's active metamodel: what a graph may contain.

        - `node_types`: `id` (the node type key graph nodes use as
          `node_type_id`), `name`, `display_name`, UI `color` and `shape`, and
          the timeserie defaults `timeserie_id` and `timeserie_secondary_id`
          (suggested primary and secondary timeserie keys for nodes of this
          type) and `timeserie_id_rule` (free-text rule describing which graph
          path a node's timeserie belongs to). The defaults are suggestions
          only: any node may link timeseries, and a type without defaults
          does not prevent it.
        - `edge_types`: `id` (the edge type key graph edges use as
          `edge_type_id`), `name`, `display_name` and UI line style and ends.
        - `allowed_connections`: the only permitted
          (`edge_type_id`, `source_node_type_id`, `target_node_type_id`)
          triples; an edge of another combination is rejected.
        - `type_attributes`: attribute definitions per owner type
          (`owner_kind` `node_type` or `edge_type`, `owner_type_id`), with
          `id`, `name`, `display_name`, `data_type` (`string`, `int`,
          `float`, `bool`, `date`, `datetime`, `enum` or `list`),
          `mandatory`, `max_length` and `multiline`. Graph element
          `attributes` are a free JSON object and are not validated against
          them.

        Every scenario of an organisation shares its metamodel; the scenario
        key only selects and checks the context. An unknown or deleted
        organisation or scenario is an error.
        """
        return await runtime.run(
            lambda session, _: (
                org_twin_structure_service.get_scenario_type_catalog_with_attributes(
                    session, organisation_key, scenario_key
                )
            )
        )

    async def get_graph(
        organisation_key: OrganisationKey,
        scenario_key: ScenarioKey,
        org_state_key: OrgStateKey,
    ) -> GraphResponse:
        """Return the scenario's graph as visible at an org state's target date.

        A node is visible when its `create_date` is on or before the target
        date and its `delete_date` is empty or on or after it. An edge is
        visible by the same rule and only when both its end nodes are visible.
        The result has the scenario's `id`, `name` and `description` and the
        visible `nodes` and `edges`, sorted by creation order.

        - A node has `id` (node key), `name`, `description`, `node_type_id`,
          `create_date`, `delete_date`, `position`, `attributes` and the linked
          timeserie keys `timeserie_id` and `timeserie_secondary_id` (null when
          not linked).
        - An edge has `id` (edge key), `name`, `description`, `edge_type_id`,
          `source_node_id`, `target_node_id`, `create_date`, `delete_date` and
          `attributes`.

        An unknown or deleted organisation, scenario or org state is an error.
        """
        return await runtime.run(
            lambda session, _: org_twin_structure_service.get_graph(
                session, organisation_key, scenario_key, org_state_key
            )
        )

    async def list_timeseries(
        organisation_key: OrganisationKey,
        scenario_key: ScenarioKey,
        include_values: Annotated[
            bool,
            Field(
                description="Also return values, at most "
                f"{LIST_TIMESERIES_MAX_VALUES} in total. Default false."
            ),
        ] = False,
    ) -> TimeserieListResult:
        """List the scenario's active timeseries, sorted by key.

        Each timeserie has `id` (timeserie key), `name`, `short_name` (the
        identifier derived formulas use), `description`, `unit`, `time_unit`
        (`day`, `week`, `month` or `year`), `value_unit` (`number`, `string` or
        `boolean`), `values`, `is_derived`, `derived_formula` (the formula of a
        derived metric, else null) and `short_name_editable` (false while a
        formula references it).

        Without `include_values` every `values` list is empty. With it, values
        are returned in timeserie key order and then date order until
        `max_values` (2,000) values in total; `truncated` is true and
        `truncated_timeserie_ids` names every timeserie whose values were cut
        or left out. Read those with get_timeserie, which pages by date. An
        unknown or deleted organisation or scenario is an error.
        """

        return await runtime.run(
            lambda session, _: _bounded_timeserie_list(
                org_states_service.list_scenario_timeseries(
                    session,
                    organisation_key,
                    scenario_key,
                    include_values=include_values,
                ),
                include_values,
            )
        )

    async def get_timeserie(
        organisation_key: OrganisationKey,
        scenario_key: ScenarioKey,
        timeserie_key: TimeserieKey,
        from_date: Annotated[
            dt_date | None,
            Field(description="Inclusive ISO start date; null for no bound."),
        ] = None,
        to_date: Annotated[
            dt_date | None,
            Field(description="Inclusive ISO end date; null for no bound."),
        ] = None,
    ) -> TimeserieValuesResult:
        """Return one timeserie with its values between two dates.

        Values are dated at the start of their period: any day for `day`, a
        Monday for `week`, the 1st for `month` and 1 January for `year`. The
        bounds are inclusive, compare those dates and need not be aligned.
        `from_date` must not be after `to_date`.

        At most `max_points` (1,000) values are returned, in date order.
        `value_count` counts all values within the bounds. When more remain,
        `truncated` is true and `next_from_date` is the date to pass as
        `from_date` for the next page. An unknown or deleted organisation,
        scenario or timeserie is an error.
        """
        if from_date is not None and to_date is not None and from_date > to_date:
            raise ToolError("from_date must not be after to_date.")

        return await runtime.run(
            lambda session, _: _bounded_timeserie_values(
                *org_states_service.get_timeserie_values_page(
                    session,
                    organisation_key,
                    scenario_key,
                    timeserie_key,
                    from_date=from_date,
                    to_date=to_date,
                    # One more than returned shows whether values remain.
                    limit=GET_TIMESERIE_MAX_POINTS + 1,
                ),
                from_date,
                to_date,
            )
        )

    async def list_events(
        organisation_key: OrganisationKey,
        scenario_key: ScenarioKey,
    ) -> list[EventResponse]:
        """List the scenario's active events by target date.

        An event is a dated business occurrence that explains changes in the
        organisation or its timeseries. Each item has `id` (event key), `name`,
        `target_date` (ISO date) and `event_details`. An unknown or deleted
        organisation or scenario is an error.
        """
        return await runtime.run(
            lambda session, _: org_states_service.list_scenario_events(
                session, organisation_key, scenario_key
            )
        )

    async def preview_generated_timeserie(
        spec: TimeserieGenerationSpec,
    ) -> GeneratedTimeseriePreview:
        """Preview the numbers a generation spec produces, without storing them.

        Generation is deterministic: the same spec, including `seed`, always
        gives the same values. `startDate` must be aligned to `timeUnit` (any
        day, a Monday, the 1st of a month or 1 January). Give exactly one of
        `periods` or `endDate`; at most 20,000 points. Change the parameters,
        never the values: the same spec is what a change set stores.

        Returns `generator_version`, `point_count`, `first_date`, `last_date`,
        `min`, `max` and `mean`, and `first_points` and `last_points`, the
        first and last 5 points. An invalid spec is a validation error naming
        the field.
        """
        return await runtime.run(lambda _session, _: _preview(spec))

    async def list_change_sets(
        organisation_key: OrganisationKey,
        status: Annotated[
            ChangeSetStatus | None,
            Field(description="Only change sets in this status; null for all."),
        ] = None,
        scenario_key: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=128,
                description="Only change sets whose derived scenario reference is "
                "this scenario key; null for all.",
            ),
        ] = None,
    ) -> ChangeSetListResult:
        """List an organisation's AI change sets, newest first, without operations.

        A change set is a proposal staged with create_change_set; nothing in
        it is applied until a human approves it. `status` is `draft` (being
        staged), `submitted` (waiting for human review), `applied`,
        `rejected`, `failed` (apply was rolled back) or `discarded`. Each item
        has `id` (the change set key), `title`, `rationale`, `status`,
        `scenario_key` (the one existing scenario every operation targets;
        null when the change set creates or copies a scenario or touches
        several), `operation_count`, the creator `created_by`, the staging
        client and the review fields: the reviewer, time and note, and
        `reviewed_via`, `web` for a review in Shadow or `mcp` with the
        reviewing client for one approved in an MCP client.

        At most `max_items` (100) are returned; `truncated` says whether older
        matching ones were left out. Filtering by `scenario_key` needs an
        active scenario of the organisation. An unknown or deleted
        organisation is an error.
        """
        return await runtime.run(
            lambda session, _: _bounded_change_sets(
                change_sets_service.list_change_sets(
                    session,
                    organisation_key,
                    status_filter=status,
                    scenario_key=scenario_key,
                    # One more than returned shows whether more remain.
                    limit=LIST_CHANGE_SETS_MAX_ITEMS + 1,
                )
            )
        )

    async def get_change_set(
        change_set_key: Annotated[
            str,
            Field(
                min_length=1,
                max_length=128,
                description="Change set key: the `id` of an item of list_change_sets.",
            ),
        ],
    ) -> ChangeSetDetail:
        """Return one change set with its operations and latest results.

        Any User may read any change set; only its creator can change a draft.
        `operations` lists each operation by `position` with its `type`,
        `ref`, the stored `operation` JSON (as add_operations accepts it), its
        latest `error` and, after submit, `frozen_values`: the generator
        version, count and first and last date of the frozen generated values
        (the values themselves are not returned). `validation_result` is the
        latest dry-run result (cleared when operations change; its
        server-generated keys are provisional) and `applied_result` the
        apply's result. An unknown change set, or one of a deleted
        organisation, is an error.
        """
        return await runtime.run(
            lambda session, _: change_sets_service.change_set_detail(
                session,
                change_sets_service.get_change_set(session, change_set_key),
            )
        )

    async def get_change_set_review(
        change_set_key: Annotated[
            str,
            Field(
                min_length=1,
                max_length=128,
                description="Change set key: the `id` of an item of list_change_sets.",
            ),
        ],
    ) -> ChangeSetReview:
        """Return what applying a change set would do now, as a person reviews it.

        It holds everything get_change_set returns, plus `replacements` and
        `review_fingerprint`, recomputed against current data on every call.
        `replacements` flags, per operation, whether it would overwrite data
        that existed before the change set (`replaces_existing`: a
        `patch_node` on an existing node, or values for an existing timeserie
        that has values) with a `summary` of the current data it replaces:
        the patched node fields with their current values, or the value count
        and date range of the timeserie's current values. A target deleted
        since is reported as `missing`.

        When apply_change_set is listed, show the user the title, the
        operations and every replacement before they decide, and pass this
        `review_fingerprint` to apply_change_set; apply fails with
        `review_stale` when the replaced data changed in between. Only a
        `submitted` change set can be applied or rejected. An unknown change
        set, or one of a deleted organisation, is an error.
        """

        def work(session: Session, _: McpPrincipal) -> ChangeSetReview:
            detail, report = change_sets_service.change_set_review(
                session, change_set_key, settings=settings
            )
            return ChangeSetReview(
                **detail.model_dump(),
                replacements=report.operations,
                review_fingerprint=report.review_fingerprint,
            )

        return await runtime.run(busy_on_timeout(work))

    auth = requires_scope(READ_SCOPE)
    for tool in (
        whoami,
        list_organisations,
        list_scenarios,
        list_org_states,
        get_type_catalog,
        get_graph,
        list_timeseries,
        get_timeserie,
        list_events,
        preview_generated_timeserie,
        list_change_sets,
        get_change_set,
        get_change_set_review,
    ):
        server.tool(tool, annotations=READ_TOOL_ANNOTATIONS, auth=auth)
    for skill in load_skills():
        server.prompt(
            _skill_prompt(skill.body),
            name=skill.prompt_name,
            description=skill.description,
            auth=auth,
        )


def _skill_prompt(body: str) -> Callable[[], str]:
    def prompt() -> str:
        return body

    return prompt


def _bounded_timeserie_list(
    timeseries: list[TimeserieResponse], include_values: bool
) -> TimeserieListResult:
    remaining = LIST_TIMESERIES_MAX_VALUES
    bounded: list[TimeserieResponse] = []
    truncated_ids: list[str] = []
    for timeserie in timeseries:
        values = timeserie.values[:remaining] if include_values else []
        if include_values and len(values) < len(timeserie.values):
            truncated_ids.append(timeserie.id)
        remaining -= len(values)
        bounded.append(timeserie.model_copy(update={"values": values}))
    return TimeserieListResult(
        timeseries=bounded,
        values_included=include_values,
        max_values=LIST_TIMESERIES_MAX_VALUES,
        truncated=bool(truncated_ids),
        truncated_timeserie_ids=truncated_ids,
    )


def _bounded_change_sets(change_sets: list[ChangeSetSummary]) -> ChangeSetListResult:
    return ChangeSetListResult(
        change_sets=change_sets[:LIST_CHANGE_SETS_MAX_ITEMS],
        max_items=LIST_CHANGE_SETS_MAX_ITEMS,
        truncated=len(change_sets) > LIST_CHANGE_SETS_MAX_ITEMS,
    )


def _bounded_timeserie_values(
    timeserie: TimeserieResponse,
    value_count: int,
    from_date: dt_date | None,
    to_date: dt_date | None,
) -> TimeserieValuesResult:
    values = timeserie.values
    truncated = len(values) > GET_TIMESERIE_MAX_POINTS
    return TimeserieValuesResult(
        timeserie=timeserie.model_copy(
            update={"values": values[:GET_TIMESERIE_MAX_POINTS]}
        ),
        from_date=from_date,
        to_date=to_date,
        value_count=value_count,
        max_points=GET_TIMESERIE_MAX_POINTS,
        truncated=truncated,
        next_from_date=values[GET_TIMESERIE_MAX_POINTS].date if truncated else None,
    )


def _preview(spec: TimeserieGenerationSpec) -> GeneratedTimeseriePreview:
    try:
        points = generate(spec)
    except TimeserieGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    values = [point.value for point in points]
    count = len(values)
    return GeneratedTimeseriePreview(
        generator_version=GENERATOR_VERSION,
        point_count=count,
        first_date=points[0].date,
        last_date=points[-1].date,
        min=min(values),
        max=max(values),
        # Dividing first keeps the sum finite for values near the float limit.
        mean=math.fsum(value / count for value in values),
        first_points=points[:PREVIEW_SAMPLE_POINTS],
        last_points=points[-PREVIEW_SAMPLE_POINTS:],
    )
