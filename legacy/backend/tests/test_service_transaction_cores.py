from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import StaticPool, create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session, sessionmaker

from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import (
    DerivedMetricEquation,
    Event,
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_states.schemas import (
    DerivedMetricCreateRequest,
    EventCreateRequest,
    OrgStateCreateRequest,
    ScenarioCopyRequest,
    ScenarioCreateRequest,
    TimeserieCreateRequest,
    TimeserieValueRequest,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
)
from app.api.v1.org_twin_structure.schemas import (
    GraphEdgeCreateRequest,
    GraphNodeCreateRequest,
    GraphNodePatchRequest,
)
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.users.models import User
from app.core.models import Base

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

ACTOR_USER_ID = 7
BUSINESS_MODELS = (
    Scenario,
    OrgState,
    Event,
    Timeserie,
    TimeserieValue,
    DerivedMetricEquation,
    GraphNode,
    GraphEdge,
)


class CommitAttemptedError(RuntimeError):
    pass


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    _seed_actor_and_default_metamodel(factory)

    yield factory


@pytest.fixture()
def organisation_key(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        response = organisations_service.create_organisation(
            session,
            OrganisationCreateRequest(name="Acme Corp"),
            ACTOR_USER_ID,
        )
    return response.id


def test_cores_compose_in_one_uncommitted_transaction(
    session_factory: sessionmaker[Session],
    organisation_key: str,
) -> None:
    baseline = _row_counts(session_factory)
    session = session_factory()
    commit_attempts: list[Session] = []

    def reject_commit(committing_session: Session) -> None:
        commit_attempts.append(committing_session)
        raise CommitAttemptedError("Transaction cores must not commit.")

    event.listen(session, "before_commit", reject_commit)
    try:
        scenario = org_states_service.create_scenario_in_transaction(
            session,
            organisation_key,
            ScenarioCreateRequest(name="AI plan"),
            ACTOR_USER_ID,
        )
        org_state = org_states_service.create_org_state_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            OrgStateCreateRequest(name="Plan start", targetDate=date(2026, 1, 1)),
            ACTOR_USER_ID,
        )
        created_event = org_states_service.create_event_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            EventCreateRequest(name="Reorganisation", targetDate=date(2025, 12, 1)),
            ACTOR_USER_ID,
        )
        for key, name in (("headcount", "Headcount"), ("cost", "Cost")):
            org_states_service.create_timeserie_in_transaction(
                session,
                organisation_key,
                scenario.scenario_key,
                TimeserieCreateRequest(
                    id=key,
                    name=name,
                    shortName=key,
                    timeUnit="month",
                    valueUnit="number",
                ),
                ACTOR_USER_ID,
            )
        _replace_values(session, organisation_key, scenario, "headcount", 10)
        _replace_values(session, organisation_key, scenario, "cost", 1000)
        derived = org_states_service.create_derived_metric_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            DerivedMetricCreateRequest(
                name="Cost per head",
                formula="cost / headcount",
            ),
            ACTOR_USER_ID,
        )
        assert _active_values(session, derived) == {
            date(2026, 1, 1): 100.0,
            date(2026, 2, 1): 100.0,
        }

        _replace_values(session, organisation_key, scenario, "headcount", 20)
        assert _active_values(session, derived) == {
            date(2026, 1, 1): 50.0,
            date(2026, 2, 1): 50.0,
        }

        source_node = org_twin_structure_service.create_graph_node_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            org_state.org_state_key,
            GraphNodeCreateRequest(id="node_a", name="Alice", nodeTypeId="nt_person"),
            ACTOR_USER_ID,
        )
        target_node = org_twin_structure_service.create_graph_node_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            org_state.org_state_key,
            GraphNodeCreateRequest(id="node_b", name="Bob", nodeTypeId="nt_person"),
            ACTOR_USER_ID,
        )
        edge = org_twin_structure_service.create_graph_edge_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            org_state.org_state_key,
            GraphEdgeCreateRequest(
                id="edge_a_b",
                name="Reports to",
                edgeTypeId="et_reports_to",
                sourceNodeId="node_a",
                targetNodeId="node_b",
            ),
            ACTOR_USER_ID,
        )
        patched_node = org_twin_structure_service.patch_graph_node_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            org_state.org_state_key,
            "node_a",
            GraphNodePatchRequest(name="Alice Smith", timeserieId="headcount"),
            ACTOR_USER_ID,
        )
        copied_scenario = org_states_service.copy_scenario_in_transaction(
            session,
            organisation_key,
            ScenarioCopyRequest(
                sourceScenarioId=scenario.scenario_key,
                sourceOrgStateId=org_state.org_state_key,
            ),
            ACTOR_USER_ID,
        )

        assert commit_attempts == []
        assert scenario.created_by == ACTOR_USER_ID
        assert org_state.scenario_id == scenario.scenario_id
        assert created_event.scenario_id == scenario.scenario_id
        assert source_node.scenario_id == scenario.scenario_id
        assert source_node.create_date == date(2026, 1, 1)
        assert edge.source_graph_node_id == source_node.graph_node_id
        assert edge.target_graph_node_id == target_node.graph_node_id
        assert patched_node is source_node
        assert patched_node.name == "Alice Smith"
        assert patched_node.modified_by == ACTOR_USER_ID
        assert patched_node.timeserie_id is not None
        assert _scenario_counts(session, copied_scenario) == {
            "events": 1,
            "timeseries": 3,
            "equations": 1,
            "nodes": 2,
            "edges": 1,
        }

        with pytest.raises(CommitAttemptedError):
            session.commit()
        assert len(commit_attempts) == 1
    finally:
        session.rollback()
        session.close()

    assert _row_counts(session_factory) == baseline


def test_create_timeserie_core_maps_flush_integrity_error_without_rollback(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        rollbacks: list[Session] = []
        event.listen(session, "after_rollback", rollbacks.append)

        def fail_flush() -> None:
            raise IntegrityError("INSERT INTO timeseries", {}, Exception("unique"))

        monkeypatch.setattr(session, "flush", fail_flush)

        with pytest.raises(HTTPException) as error:
            org_states_service.create_timeserie_in_transaction(
                session,
                organisation_key,
                "reality",
                TimeserieCreateRequest(
                    id="headcount",
                    name="Headcount",
                    timeUnit="month",
                    valueUnit="number",
                ),
                ACTOR_USER_ID,
            )

        assert error.value.status_code == 409
        assert error.value.detail == (
            "An active timeserie with this id, name, or short name already exists."
        )
        assert isinstance(error.value.__cause__, IntegrityError)
        assert rollbacks == []

        with pytest.raises(HTTPException) as public_error:
            org_states_service.create_timeserie(
                session,
                organisation_key,
                "reality",
                TimeserieCreateRequest(
                    id="headcount",
                    name="Headcount",
                    timeUnit="month",
                    valueUnit="number",
                ),
                ACTOR_USER_ID,
            )

        assert public_error.value.status_code == 409
        assert len(rollbacks) == 1


def _replace_values(
    session: Session,
    organisation_key: str,
    scenario: Scenario,
    timeserie_key: str,
    value: float,
) -> Timeserie:
    return org_states_service.replace_timeserie_values_in_transaction(
        session,
        organisation_key,
        scenario.scenario_key,
        timeserie_key,
        TimeserieValuesPatchRequest(
            values=[
                TimeserieValueRequest(date=date(2026, 1, 1), value=value),
                TimeserieValueRequest(date=date(2026, 2, 1), value=value),
            ],
        ),
        ACTOR_USER_ID,
    )


def _active_values(session: Session, timeserie: Timeserie) -> dict[date, object]:
    values = session.scalars(
        select(TimeserieValue).where(
            TimeserieValue.timeserie_id == timeserie.timeserie_id,
            TimeserieValue.deleted_time.is_(None),
        ),
    ).all()
    return {value.date: value.value["value"] for value in values}


def _scenario_counts(session: Session, scenario: Scenario) -> dict[str, int]:
    def count(scenario_column: InstrumentedAttribute[int]) -> int:
        return (
            session.scalar(
                select(func.count()).where(scenario_column == scenario.scenario_id),
            )
            or 0
        )

    return {
        "events": count(Event.scenario_id),
        "timeseries": count(Timeserie.scenario_id),
        "equations": count(DerivedMetricEquation.scenario_id),
        "nodes": count(GraphNode.scenario_id),
        "edges": count(GraphEdge.scenario_id),
    }


def _row_counts(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model),
            )
            or 0
            for model in BUSINESS_MODELS
        }


def _seed_actor_and_default_metamodel(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        session.add(
            User(
                user_id=ACTOR_USER_ID,
                name="Test Admin",
                email="test-admin@example.test",
                role="admin",
            ),
        )
        metamodel = Metamodel(version=1)
        session.add(metamodel)
        session.flush()

        person_type = NodeType(
            metamodel_id=metamodel.metamodel_id,
            node_type_key="nt_person",
            name="Person",
            display_name="Person",
            ui_color="#FECDC2",
            ui_shape="rectangle",
        )
        edge_type = EdgeType(
            metamodel_id=metamodel.metamodel_id,
            edge_type_key="et_reports_to",
            name="Reports to",
            display_name="Reports to",
            ui_style="solid",
            ui_source_end="none",
            ui_target_end="arrow",
        )
        session.add_all([person_type, edge_type])
        session.flush()
        session.add(
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=edge_type.edge_type_id,
                source_node_type_id=person_type.node_type_id,
                target_node_type_id=person_type.node_type_id,
            ),
        )
        session.commit()
