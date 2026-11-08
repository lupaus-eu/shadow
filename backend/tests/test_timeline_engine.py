"""The replay engine: changes, chains, ordering, branches and compaction (model timeline ticket 01). No database."""
import random
from datetime import date
from uuid import uuid4

import pytest

from app.timeline.chain import (
    EventRecord, LineRecord, branch_prefix, chain_events, descendants, replay, sort_events, state_after, state_as_of, validate_lines,
)
from app.timeline.compact import compact
from app.timeline.errors import ChainBroken, ChangeInvalid
from app.timeline.state import Change, Metamodel, State, apply_change, apply_changes

TEAM, PERSON, PRODUCT = uuid4(), uuid4(), uuid4()
MEMBER_OF, OWNS = uuid4(), uuid4()
METAMODEL = Metamodel(
    node_type_ids=frozenset({TEAM, PERSON, PRODUCT}),
    connection_type_ids=frozenset({MEMBER_OF, OWNS}),
    allowed=frozenset({(MEMBER_OF, PERSON, TEAM), (OWNS, TEAM, PRODUCT)}),
)


def add_node(type_id, name="N", node_id=None):
    node_id = node_id or uuid4()
    return Change("add_node", node_id, {"node_type_id": str(type_id), "name": name})


def add_connection(type_id, source, target, connection_id=None):
    return Change("add_connection", connection_id or uuid4(), {"connection_type_id": str(type_id), "source_node_id": str(source), "target_node_id": str(target)})


_seq = iter(range(1, 10_000))


def event(line_id, day, *changes, title="e", event_id=None):
    return EventRecord(event_id or uuid4(), line_id, day, next(_seq), title, tuple(changes))


def d(month, day=1, year=2026):
    return date(year, month, day)


def test_every_change_applies_and_a_node_removal_takes_its_connections_with_it() -> None:
    ada, support, product = uuid4(), uuid4(), uuid4()
    link, owns = uuid4(), uuid4()
    state = apply_changes(State(), [
        add_node(PERSON, "Ada", ada), add_node(TEAM, "Support", support), add_node(PRODUCT, "App", product),
        add_connection(MEMBER_OF, ada, support, link), add_connection(OWNS, support, product, owns),
    ], METAMODEL)
    assert len(state.nodes) == 3 and len(state.connections) == 2
    state = apply_changes(state, [Change("update_node", ada, {"name": "Ada L.", "description": None})], METAMODEL)
    assert state.nodes[ada].name == "Ada L." and state.nodes[ada].description is None
    state = apply_changes(state, [Change("change_connection_type", owns, {"connection_type_id": str(OWNS)})], METAMODEL)
    other_team = uuid4()
    state = apply_changes(state, [add_node(TEAM, "Sales", other_team), Change("reroute_connection", link, {"target_node_id": str(other_team)})], METAMODEL)
    assert state.connections[link].target_node_id == other_team
    state = apply_changes(state, [Change("remove_connection", owns, {})], METAMODEL)
    assert owns not in state.connections
    state = apply_changes(state, [Change("remove_node", other_team, {})], METAMODEL)
    assert link not in state.connections and other_team not in state.nodes


@pytest.mark.parametrize("changes, cause", [
    ([Change("remove_node", uuid4(), {})], "missing_element"),
    ([Change("update_node", uuid4(), {"name": "x"})], "missing_element"),
    ([Change("remove_connection", uuid4(), {})], "missing_element"),
    ([add_node(uuid4(), "Unknown type")], "missing_type"),
])
def test_invalid_changes_name_their_cause(changes, cause) -> None:
    with pytest.raises(ChangeInvalid) as raised:
        apply_changes(State(), changes, METAMODEL)
    assert raised.value.cause == cause


def test_connection_rules_each_refuse_with_their_cause() -> None:
    ada, support, product, twin = uuid4(), uuid4(), uuid4(), uuid4()
    base = apply_changes(State(), [add_node(PERSON, "Ada", ada), add_node(TEAM, "Support", support), add_node(PRODUCT, "App", product)], METAMODEL)
    cases = {
        "missing_endpoint": add_connection(MEMBER_OF, ada, uuid4()),
        "self_connection": add_connection(OWNS, support, support),
        "connection_not_allowed": add_connection(MEMBER_OF, support, ada),
        "missing_type": add_connection(uuid4(), ada, support),
    }
    for cause, change in cases.items():
        with pytest.raises(ChangeInvalid) as raised:
            apply_change(base.copy(), change, METAMODEL)
        assert raised.value.cause == cause, cause
    once = apply_changes(base, [add_connection(MEMBER_OF, ada, support)], METAMODEL)
    with pytest.raises(ChangeInvalid) as raised:
        apply_change(once.copy(), add_connection(MEMBER_OF, ada, support), METAMODEL)
    assert raised.value.cause == "duplicate_connection"
    with pytest.raises(ChangeInvalid) as raised:
        apply_change(once.copy(), add_node(TEAM, "Again", support), METAMODEL)
    assert raised.value.cause == "duplicate_element"
    with pytest.raises(ChangeInvalid) as raised:  # re-typing the node would make its connection illegal
        apply_change(once.copy(), Change("update_node", ada, {"node_type_id": str(TEAM)}), METAMODEL)
    assert raised.value.cause == "connection_not_allowed"
    del twin


def test_a_malformed_payload_is_refused_before_it_is_applied() -> None:
    with pytest.raises(ValueError):
        apply_change(State(), Change("add_node", uuid4(), {"name": "no type"}), METAMODEL)
    with pytest.raises(ValueError):
        apply_change(State(), Change("update_node", uuid4(), {}), METAMODEL)
    with pytest.raises(ValueError):
        apply_change(State(), Change("explode", uuid4(), {}), METAMODEL)


def test_events_sort_by_date_then_entry_order_and_replay_follows_that_order() -> None:
    line = uuid4()
    node = uuid4()
    late_rename = event(line, d(5), Change("update_node", node, {"name": "Second"}))
    created = event(line, d(3), add_node(TEAM, "First", node))
    same_day = event(line, d(5), Change("update_node", node, {"name": "Third"}))
    assert [item.id for item in sort_events([late_rename, created, same_day])] == [created.id, late_rename.id, same_day.id]
    lines = {line: LineRecord(line)}
    state = state_after(lines, {line: [late_rename, created, same_day]}, METAMODEL, line)
    assert state.nodes[node].name == "Third"
    assert state_after(lines, {line: [late_rename, created, same_day]}, METAMODEL, line, late_rename.id).nodes[node].name == "Second"
    assert state_after(lines, {line: [late_rename, created, same_day]}, METAMODEL, line, created.id).nodes[node].name == "First"


def test_a_scenario_starts_from_its_branch_point_and_ignores_later_parent_events() -> None:
    base, scenario, nested = uuid4(), uuid4(), uuid4()
    node = uuid4()
    founded = event(base, d(1), add_node(TEAM, "Support", node))
    renamed = event(base, d(2), Change("update_node", node, {"name": "Helpdesk"}))
    branched = event(scenario, d(3), Change("update_node", node, {"name": "Own"}))
    deeper = event(nested, d(4), add_node(PRODUCT, "Idea"))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, founded.id), nested: LineRecord(nested, scenario, branched.id)}
    events = {base: [founded, renamed], scenario: [branched], nested: [deeper]}
    assert state_after(lines, events, METAMODEL, scenario).nodes[node].name == "Own"
    assert state_after(lines, events, METAMODEL, base).nodes[node].name == "Helpdesk"
    assert [item.id for item in chain_events(lines, events, scenario)] == [founded.id, branched.id]  # not the parent's later event
    assert [item.id for item in chain_events(lines, events, nested)] == [founded.id, branched.id, deeper.id]
    assert len(state_after(lines, events, METAMODEL, nested).nodes) == 2
    assert descendants(lines, base) == [scenario, nested] or set(descendants(lines, base)) == {scenario, nested}
    assert descendants(lines, nested) == []
    assert branch_prefix(lines, events, base) == () and branch_prefix(lines, events, nested) == (founded.id, branched.id)


def test_state_as_of_a_date_is_the_state_after_the_last_event_of_that_day_or_earlier() -> None:
    line = uuid4()
    node = uuid4()
    lines = {line: LineRecord(line)}
    events = {line: [event(line, d(1), add_node(TEAM, "A", node)), event(line, d(3), Change("update_node", node, {"name": "B"}))]}
    assert state_as_of(lines, events, METAMODEL, line, d(1, 1, 2025)).nodes == {}
    assert state_as_of(lines, events, METAMODEL, line, d(2)).nodes[node].name == "A"
    assert state_as_of(lines, events, METAMODEL, line, d(3)).nodes[node].name == "B"
    assert state_as_of(lines, events, METAMODEL, line, d(12)).nodes[node].name == "B"


def test_a_scenario_as_of_a_date_before_its_own_events_shows_its_branch_point() -> None:
    base, scenario = uuid4(), uuid4()
    node = uuid4()
    founded = event(base, d(1), add_node(TEAM, "A", node))
    own = event(scenario, d(6), Change("update_node", node, {"name": "B"}))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, founded.id)}
    events = {base: [founded], scenario: [own]}
    assert state_as_of(lines, events, METAMODEL, scenario, d(3)).nodes[node].name == "A"
    assert state_as_of(lines, events, METAMODEL, scenario, d(6)).nodes[node].name == "B"


def test_breaking_a_chain_names_the_line_event_position_cause_and_element() -> None:
    line = uuid4()
    ada, support = uuid4(), uuid4()
    founded = event(line, d(1), add_node(TEAM, "Support", support))
    moved = event(line, d(2), add_node(PERSON, "Ada", ada), add_connection(MEMBER_OF, ada, support))
    lines = {line: LineRecord(line)}
    validate_lines(lines, {line: [founded, moved]}, METAMODEL)
    # The founding event is moved after the event that depends on it: the chain breaks at the dependent change.
    late_founding = EventRecord(founded.id, line, d(9), founded.seq, founded.title, founded.changes)
    with pytest.raises(ChainBroken) as raised:
        validate_lines(lines, {line: [late_founding, moved]}, METAMODEL)
    broken = raised.value
    assert (broken.line_id, broken.event_id, broken.position, broken.cause, broken.element_id) == (line, moved.id, 1, "missing_endpoint", support)
    with pytest.raises(ChainBroken) as raised:  # deleting the founding event does the same
        validate_lines(lines, {line: [moved]}, METAMODEL)
    assert raised.value.cause == "missing_endpoint"


def test_a_scenario_needs_its_branch_event_and_may_not_start_before_it() -> None:
    base, scenario = uuid4(), uuid4()
    founded = event(base, d(5), add_node(TEAM, "A"))
    early = event(scenario, d(2), add_node(TEAM, "B"))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, founded.id)}
    with pytest.raises(ChainBroken) as raised:
        validate_lines(lines, {base: [founded], scenario: [early]}, METAMODEL)
    assert (raised.value.cause, raised.value.event_id) == ("before_branch_event", early.id)
    with pytest.raises(ChainBroken) as raised:  # the branch event is gone from the parent
        validate_lines(lines, {base: [], scenario: []}, METAMODEL)
    assert raised.value.cause == "missing_branch_event"
    validate_lines(lines, {base: [founded], scenario: [event(scenario, d(5), add_node(TEAM, "C"))]}, METAMODEL)
    # Only the lines named are replayed.
    validate_lines(lines, {base: [founded], scenario: [early]}, METAMODEL, line_ids=[base])


def test_a_correction_in_the_parent_flows_into_a_scenario_but_not_its_later_events() -> None:
    base, scenario = uuid4(), uuid4()
    node = uuid4()
    founded = event(base, d(1), add_node(TEAM, "A", node))
    later = event(base, d(8), Change("update_node", node, {"name": "Later"}))
    branch = event(base, d(4), Change("update_node", node, {"name": "Branch"}))
    child = event(scenario, d(5), Change("update_node", node, {"name": "Child"}))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, branch.id)}
    before = branch_prefix(lines, {base: [founded, branch, later], scenario: [child]}, scenario)
    correction = event(base, d(2), Change("update_node", node, {"name": "Corrected"}))
    after = branch_prefix(lines, {base: [founded, branch, later, correction], scenario: [child]}, scenario)
    assert before == (founded.id, branch.id) and after == (founded.id, correction.id, branch.id)
    assert state_after(lines, {base: [founded, branch, later, correction], scenario: [child]}, METAMODEL, scenario).nodes[node].name == "Child"


def test_compaction_folds_merges_and_drops_without_changing_the_outcome() -> None:
    node, other, link = uuid4(), uuid4(), uuid4()
    base = apply_changes(State(), [add_node(TEAM, "Existing", other)], METAMODEL)
    changes = [
        add_node(TEAM, "Draft", node),
        Change("update_node", node, {"name": "Final"}),
        Change("update_node", other, {"name": "Renamed"}),
        Change("update_node", other, {"description": "Twice"}),
    ]
    tidy = compact(changes, base, METAMODEL)
    assert [item.op for item in tidy] == ["add_node", "update_node"]
    assert tidy[0].payload["name"] == "Final" and tidy[1].payload == {"name": "Renamed", "description": "Twice"}
    assert apply_changes(base, tidy, METAMODEL).nodes == apply_changes(base, changes, METAMODEL).nodes

    scratch = uuid4()
    drawn = [add_node(TEAM, "Scratch", scratch), add_node(PERSON, "P", node), add_connection(MEMBER_OF, node, scratch, link),
             Change("update_node", scratch, {"name": "Scratch 2"}), Change("remove_node", scratch, {})]
    kept = compact(drawn, base, METAMODEL)
    assert [item.op for item in kept] == ["add_node"] and kept[0].element_id == node
    assert apply_changes(base, kept, METAMODEL).nodes.keys() == apply_changes(base, drawn, METAMODEL).nodes.keys()


def test_compaction_leaves_changes_alone_when_unsure() -> None:
    node = uuid4()
    invalid = [Change("remove_node", node, {})]
    assert compact(invalid, State(), METAMODEL) == invalid
    plain = [add_node(TEAM, "A", node)]
    assert compact(plain, State(), METAMODEL) == plain
    # Removing an element that existed before the event is a real change and stays.
    base = apply_changes(State(), [add_node(TEAM, "Old", node)], METAMODEL)
    removal = [Change("remove_node", node, {})]
    assert compact(removal, base, METAMODEL) == removal


def test_random_valid_sequences_replay_to_the_same_graph_as_a_direct_reference() -> None:
    rng = random.Random(7)
    for _ in range(25):
        line = uuid4()
        reference = State()
        events = []
        day = 1
        for _ in range(rng.randint(3, 12)):
            changes = []
            scratch = reference.copy()
            for _ in range(rng.randint(1, 4)):
                choice = rng.choice(["person", "team", "link", "remove", "rename"])
                if choice in ("person", "team"):
                    change = add_node(PERSON if choice == "person" else TEAM, f"n{rng.randint(0, 99)}")
                elif choice == "link":
                    people = [n for n in scratch.nodes.values() if n.node_type_id == PERSON]
                    teams = [n for n in scratch.nodes.values() if n.node_type_id == TEAM]
                    if not people or not teams:
                        continue
                    change = add_connection(MEMBER_OF, rng.choice(people).id, rng.choice(teams).id)
                elif choice == "remove" and scratch.nodes:
                    change = Change("remove_node", rng.choice(list(scratch.nodes)), {})
                elif choice == "rename" and scratch.nodes:
                    change = Change("update_node", rng.choice(list(scratch.nodes)), {"name": f"r{rng.randint(0, 99)}"})
                else:
                    continue
                try:
                    apply_change(scratch, change, METAMODEL)
                except ChangeInvalid:
                    continue
                changes.append(change)
            reference = scratch
            events.append(event(line, date(2026, 1, 1).replace(day=min(day, 28)), *changes))
            day += rng.randint(0, 2)
        shuffled = list(events)
        rng.shuffle(shuffled)
        lines = {line: LineRecord(line)}
        state = state_after(lines, {line: shuffled}, METAMODEL, line)
        assert state.nodes == reference.nodes and state.connections == reference.connections
        assert replay(chain_events(lines, {line: events}, line), METAMODEL).nodes == reference.nodes
