"""The timeline tables: constraints, ordering, protection of branch points and row-level security (ticket 01)."""
from contextlib import ExitStack
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database import RequestContext, create_session_factory, transaction_session
from app.models import ChangeEdit, ModelLine, NodePosition, TimelineChange
from test_models_graph import _tenant


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _seed(stack: ExitStack, database_url: str, subject: str):
    application, owner, organization_id, base = _tenant(stack, database_url, subject)
    model_id = owner.post(f"{base}/models", json={"name": "Timeline"}).json()["id"]
    factory = create_session_factory(application.state.database_engine)
    with transaction_session(factory, RequestContext(organization_id=organization_id)) as session:  # a new Model comes with a Base line (ticket 02); these tests build their own
        session.execute(text("DELETE FROM model_lines WHERE model_id = :id"), {"id": model_id})
    return factory, application, organization_id, model_id


def _base_line(session, organization_id, model_id, name="Base line"):
    line = ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, name=name, kind="base")
    session.add(line)
    session.flush()
    return line


def test_a_model_has_one_base_line_and_scenarios_need_a_parent_and_branch_change(database_url: str, stack: ExitStack) -> None:
    factory, _, organization_id, model_id = _seed(stack, database_url, "timeline-lines")
    context = RequestContext(organization_id=organization_id)
    with transaction_session(factory, context) as session:
        base = _base_line(session, organization_id, model_id)
        founded = TimelineChange(id=uuid4(), organization_id=organization_id, model_id=model_id, line_id=base.id, occurred_on=date(2026, 1, 1), title="Initial situation")
        session.add(founded)
        session.flush()
        scenario = ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, name="What if", kind="scenario", parent_line_id=base.id, branch_change_id=founded.id)
        session.add(scenario)
        session.flush()
        assert scenario.version == 1
    for bad in (
        dict(name="Second base", kind="base"),
        dict(name="Orphan", kind="scenario"),
        dict(name="what if", kind="scenario", parent_line_id=base.id, branch_change_id=founded.id),
        dict(name="Odd", kind="base", parent_line_id=base.id),
    ):
        with pytest.raises(IntegrityError):
            with transaction_session(factory, context) as session:
                session.add(ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, **bad))
                session.flush()


def test_changes_keep_entry_order_and_a_branch_change_cannot_be_deleted(database_url: str, stack: ExitStack) -> None:
    factory, _, organization_id, model_id = _seed(stack, database_url, "timeline-changes")
    context = RequestContext(organization_id=organization_id)
    with transaction_session(factory, context) as session:
        base = _base_line(session, organization_id, model_id)
        ids = []
        for title, day in (("b", date(2026, 3, 1)), ("a", date(2026, 3, 1)), ("c", date(2026, 2, 1))):
            change = TimelineChange(id=uuid4(), organization_id=organization_id, model_id=model_id, line_id=base.id, occurred_on=day, title=title)
            session.add(change)
            session.flush()
            ids.append(change.id)
        ordered = session.scalars(select(TimelineChange).where(TimelineChange.line_id == base.id).order_by(TimelineChange.occurred_on, TimelineChange.seq)).all()
        assert [item.title for item in ordered] == ["c", "b", "a"]
        assert ordered[1].seq < ordered[2].seq
        session.add(ChangeEdit(id=uuid4(), organization_id=organization_id, change_id=ids[0], position=0, op="add_node", element_id=uuid4(), payload={"name": "x"}))
        session.flush()
        scenario = ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, name="Branch", kind="scenario", parent_line_id=base.id, branch_change_id=ids[0])
        session.add(scenario)
        session.flush()
    with pytest.raises(IntegrityError):  # the line branches from it
        with transaction_session(factory, context) as session:
            session.execute(text("DELETE FROM timeline_changes WHERE id = :id"), {"id": ids[0]})
    with pytest.raises(IntegrityError):  # a parent with Scenarios cannot be deleted either
        with transaction_session(factory, context) as session:
            session.execute(text("DELETE FROM model_lines WHERE id = :id"), {"id": base.id})
    with pytest.raises(IntegrityError):  # unknown edit operation and duplicate position
        with transaction_session(factory, context) as session:
            session.add(ChangeEdit(id=uuid4(), organization_id=organization_id, change_id=ids[1], position=0, op="explode", element_id=uuid4()))
            session.flush()
    with pytest.raises(IntegrityError):
        with transaction_session(factory, context) as session:
            for _ in range(2):
                session.add(ChangeEdit(id=uuid4(), organization_id=organization_id, change_id=ids[1], position=0, op="remove_node", element_id=uuid4()))
            session.flush()
    with transaction_session(factory, context) as session:  # removing the scenario first frees the change
        session.execute(text("DELETE FROM model_lines WHERE kind = 'scenario' AND model_id = :id"), {"id": model_id})
        session.execute(text("DELETE FROM timeline_changes WHERE id = :id"), {"id": ids[0]})
        assert session.scalar(select(ChangeEdit).where(ChangeEdit.change_id == ids[0])) is None  # its edits went with it


def test_positions_are_per_line_and_node_and_deleted_with_the_line(database_url: str, stack: ExitStack) -> None:
    factory, _, organization_id, model_id = _seed(stack, database_url, "timeline-positions")
    context = RequestContext(organization_id=organization_id)
    node = uuid4()
    with transaction_session(factory, context) as session:
        base = _base_line(session, organization_id, model_id)
        session.add(NodePosition(line_id=base.id, node_id=node, organization_id=organization_id, model_id=model_id, x=1, y=2))
        session.flush()
    with pytest.raises(IntegrityError):
        with transaction_session(factory, context) as session:
            session.add(NodePosition(line_id=base.id, node_id=node, organization_id=organization_id, model_id=model_id, x=3, y=4))
            session.flush()
    with transaction_session(factory, context) as session:
        session.execute(text("DELETE FROM model_lines WHERE id = :id"), {"id": base.id})
        assert session.scalar(select(NodePosition).where(NodePosition.line_id == base.id)) is None


def test_another_organization_and_anonymous_requests_see_no_timeline_rows(database_url: str, stack: ExitStack) -> None:
    factory, application, organization_id, model_id = _seed(stack, database_url, "timeline-rls-a")
    _, _, other_id, _ = _tenant(stack, database_url, "timeline-rls-b")
    with transaction_session(factory, RequestContext(organization_id=organization_id)) as session:
        base = _base_line(session, organization_id, model_id)
        session.add(TimelineChange(id=uuid4(), organization_id=organization_id, model_id=model_id, line_id=base.id, occurred_on=date(2026, 1, 1), title="Secret"))
        session.add(NodePosition(line_id=base.id, node_id=uuid4(), organization_id=organization_id, model_id=model_id, x=0, y=0))
        session.flush()
    tables = ("model_lines", "timeline_changes", "change_edits", "node_positions")
    with transaction_session(factory, RequestContext(organization_id=other_id)) as session:
        foreign = {table: session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": organization_id}).scalar_one() for table in tables}
    with transaction_session(factory, RequestContext()) as session:
        anonymous = {table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables}
    assert set(foreign.values()) == {0}, foreign
    assert set(anonymous.values()) == {0}, anonymous
    with pytest.raises(Exception):  # inserting for another Organization is refused by the policy
        with transaction_session(factory, RequestContext(organization_id=other_id)) as session:
            session.add(ModelLine(id=uuid4(), organization_id=organization_id, model_id=model_id, name="Intruder", kind="base"))
            session.flush()
