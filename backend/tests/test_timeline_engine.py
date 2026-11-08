"""The replay engine: edits, chains, ordering, branches and compaction (model timeline ticket 01). No database."""
import random
from datetime import date
from uuid import uuid4

import pytest

from app.timeline.chain import (
    ChangeRecord, LineRecord, branch_prefix, chain_changes, descendants, replay, sort_changes, state_after, state_as_of, validate_lines,
)
from app.timeline.compact import compact
from app.timeline.errors import ChainBroken, EditInvalid
from app.timeline.state import Edit, Metamodel, State, apply_edit, apply_edits

TEAM, PERSON, PRODUCT = uuid4(), uuid4(), uuid4()
MEMBER_OF, OWNS = uuid4(), uuid4()
METAMODEL = Metamodel(
    node_type_ids=frozenset({TEAM, PERSON, PRODUCT}),
    connection_type_ids=frozenset({MEMBER_OF, OWNS}),
    allowed=frozenset({(MEMBER_OF, PERSON, TEAM), (OWNS, TEAM, PRODUCT)}),
)


def add_node(type_id, name="N", node_id=None):
    node_id = node_id or uuid4()
    return Edit("add_node", node_id, {"node_type_id": str(type_id), "name": name})


def add_connection(type_id, source, target, connection_id=None):
    return Edit("add_connection", connection_id or uuid4(), {"connection_type_id": str(type_id), "source_node_id": str(source), "target_node_id": str(target)})


_seq = iter(range(1, 10_000))


def change(line_id, day, *edits, title="e", change_id=None):
    return ChangeRecord(change_id or uuid4(), line_id, day, next(_seq), title, tuple(edits))


def d(month, day=1, year=2026):
    return date(year, month, day)


def test_every_edit_applies_and_a_node_removal_takes_its_connections_with_it() -> None:
    ada, support, product = uuid4(), uuid4(), uuid4()
    link, owns = uuid4(), uuid4()
    state = apply_edits(State(), [
        add_node(PERSON, "Ada", ada), add_node(TEAM, "Support", support), add_node(PRODUCT, "App", product),
        add_connection(MEMBER_OF, ada, support, link), add_connection(OWNS, support, product, owns),
    ], METAMODEL)
    assert len(state.nodes) == 3 and len(state.connections) == 2
    state = apply_edits(state, [Edit("update_node", ada, {"name": "Ada L.", "description": None})], METAMODEL)
    assert state.nodes[ada].name == "Ada L." and state.nodes[ada].description is None
    state = apply_edits(state, [Edit("change_connection_type", owns, {"connection_type_id": str(OWNS)})], METAMODEL)
    other_team = uuid4()
    state = apply_edits(state, [add_node(TEAM, "Sales", other_team), Edit("reroute_connection", link, {"target_node_id": str(other_team)})], METAMODEL)
    assert state.connections[link].target_node_id == other_team
    state = apply_edits(state, [Edit("remove_connection", owns, {})], METAMODEL)
    assert owns not in state.connections
    state = apply_edits(state, [Edit("remove_node", other_team, {})], METAMODEL)
    assert link not in state.connections and other_team not in state.nodes


@pytest.mark.parametrize("edits, cause", [
    ([Edit("remove_node", uuid4(), {})], "missing_element"),
    ([Edit("update_node", uuid4(), {"name": "x"})], "missing_element"),
    ([Edit("remove_connection", uuid4(), {})], "missing_element"),
    ([add_node(uuid4(), "Unknown type")], "missing_type"),
])
def test_invalid_edits_name_their_cause(edits, cause) -> None:
    with pytest.raises(EditInvalid) as raised:
        apply_edits(State(), edits, METAMODEL)
    assert raised.value.cause == cause


def test_connection_rules_each_refuse_with_their_cause() -> None:
    ada, support, product, twin = uuid4(), uuid4(), uuid4(), uuid4()
    base = apply_edits(State(), [add_node(PERSON, "Ada", ada), add_node(TEAM, "Support", support), add_node(PRODUCT, "App", product)], METAMODEL)
    cases = {
        "missing_endpoint": add_connection(MEMBER_OF, ada, uuid4()),
        "self_connection": add_connection(OWNS, support, support),
        "connection_not_allowed": add_connection(MEMBER_OF, support, ada),
        "missing_type": add_connection(uuid4(), ada, support),
    }
    for cause, edit in cases.items():
        with pytest.raises(EditInvalid) as raised:
            apply_edit(base.copy(), edit, METAMODEL)
        assert raised.value.cause == cause, cause
    once = apply_edits(base, [add_connection(MEMBER_OF, ada, support)], METAMODEL)
    with pytest.raises(EditInvalid) as raised:
        apply_edit(once.copy(), add_connection(MEMBER_OF, ada, support), METAMODEL)
    assert raised.value.cause == "duplicate_connection"
    with pytest.raises(EditInvalid) as raised:
        apply_edit(once.copy(), add_node(TEAM, "Again", support), METAMODEL)
    assert raised.value.cause == "duplicate_element"
    with pytest.raises(EditInvalid) as raised:  # re-typing the node would make its connection illegal
        apply_edit(once.copy(), Edit("update_node", ada, {"node_type_id": str(TEAM)}), METAMODEL)
    assert raised.value.cause == "connection_not_allowed"
    del twin


def test_a_malformed_payload_is_refused_before_it_is_applied() -> None:
    with pytest.raises(ValueError):
        apply_edit(State(), Edit("add_node", uuid4(), {"name": "no type"}), METAMODEL)
    with pytest.raises(ValueError):
        apply_edit(State(), Edit("update_node", uuid4(), {}), METAMODEL)
    with pytest.raises(ValueError):
        apply_edit(State(), Edit("explode", uuid4(), {}), METAMODEL)


def test_changes_sort_by_date_then_entry_order_and_replay_follows_that_order() -> None:
    line = uuid4()
    node = uuid4()
    late_rename = change(line, d(5), Edit("update_node", node, {"name": "Second"}))
    created = change(line, d(3), add_node(TEAM, "First", node))
    same_day = change(line, d(5), Edit("update_node", node, {"name": "Third"}))
    assert [item.id for item in sort_changes([late_rename, created, same_day])] == [created.id, late_rename.id, same_day.id]
    lines = {line: LineRecord(line)}
    state = state_after(lines, {line: [late_rename, created, same_day]}, METAMODEL, line)
    assert state.nodes[node].name == "Third"
    assert state_after(lines, {line: [late_rename, created, same_day]}, METAMODEL, line, late_rename.id).nodes[node].name == "Second"
    assert state_after(lines, {line: [late_rename, created, same_day]}, METAMODEL, line, created.id).nodes[node].name == "First"


def test_a_scenario_starts_from_its_branch_point_and_ignores_later_parent_changes() -> None:
    base, scenario, nested = uuid4(), uuid4(), uuid4()
    node = uuid4()
    founded = change(base, d(1), add_node(TEAM, "Support", node))
    renamed = change(base, d(2), Edit("update_node", node, {"name": "Helpdesk"}))
    branched = change(scenario, d(3), Edit("update_node", node, {"name": "Own"}))
    deeper = change(nested, d(4), add_node(PRODUCT, "Idea"))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, founded.id), nested: LineRecord(nested, scenario, branched.id)}
    changes = {base: [founded, renamed], scenario: [branched], nested: [deeper]}
    assert state_after(lines, changes, METAMODEL, scenario).nodes[node].name == "Own"
    assert state_after(lines, changes, METAMODEL, base).nodes[node].name == "Helpdesk"
    assert [item.id for item in chain_changes(lines, changes, scenario)] == [founded.id, branched.id]  # not the parent's later change
    assert [item.id for item in chain_changes(lines, changes, nested)] == [founded.id, branched.id, deeper.id]
    assert len(state_after(lines, changes, METAMODEL, nested).nodes) == 2
    assert descendants(lines, base) == [scenario, nested] or set(descendants(lines, base)) == {scenario, nested}
    assert descendants(lines, nested) == []
    assert branch_prefix(lines, changes, base) == () and branch_prefix(lines, changes, nested) == (founded.id, branched.id)


def test_state_as_of_a_date_is_the_state_after_the_last_change_of_that_day_or_earlier() -> None:
    line = uuid4()
    node = uuid4()
    lines = {line: LineRecord(line)}
    changes = {line: [change(line, d(1), add_node(TEAM, "A", node)), change(line, d(3), Edit("update_node", node, {"name": "B"}))]}
    assert state_as_of(lines, changes, METAMODEL, line, d(1, 1, 2025)).nodes == {}
    assert state_as_of(lines, changes, METAMODEL, line, d(2)).nodes[node].name == "A"
    assert state_as_of(lines, changes, METAMODEL, line, d(3)).nodes[node].name == "B"
    assert state_as_of(lines, changes, METAMODEL, line, d(12)).nodes[node].name == "B"


def test_a_scenario_as_of_a_date_before_its_own_changes_shows_its_branch_point() -> None:
    base, scenario = uuid4(), uuid4()
    node = uuid4()
    founded = change(base, d(1), add_node(TEAM, "A", node))
    own = change(scenario, d(6), Edit("update_node", node, {"name": "B"}))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, founded.id)}
    changes = {base: [founded], scenario: [own]}
    assert state_as_of(lines, changes, METAMODEL, scenario, d(3)).nodes[node].name == "A"
    assert state_as_of(lines, changes, METAMODEL, scenario, d(6)).nodes[node].name == "B"


def test_breaking_a_chain_names_the_line_change_position_cause_and_element() -> None:
    line = uuid4()
    ada, support = uuid4(), uuid4()
    founded = change(line, d(1), add_node(TEAM, "Support", support))
    moved = change(line, d(2), add_node(PERSON, "Ada", ada), add_connection(MEMBER_OF, ada, support))
    lines = {line: LineRecord(line)}
    validate_lines(lines, {line: [founded, moved]}, METAMODEL)
    # The founding change is moved after the change that depends on it: the chain breaks at the dependent edit.
    late_founding = ChangeRecord(founded.id, line, d(9), founded.seq, founded.title, founded.edits)
    with pytest.raises(ChainBroken) as raised:
        validate_lines(lines, {line: [late_founding, moved]}, METAMODEL)
    broken = raised.value
    assert (broken.line_id, broken.change_id, broken.position, broken.cause, broken.element_id) == (line, moved.id, 1, "missing_endpoint", support)
    with pytest.raises(ChainBroken) as raised:  # deleting the founding change does the same
        validate_lines(lines, {line: [moved]}, METAMODEL)
    assert raised.value.cause == "missing_endpoint"


def test_a_scenario_needs_its_branch_change_and_may_not_start_before_it() -> None:
    base, scenario = uuid4(), uuid4()
    founded = change(base, d(5), add_node(TEAM, "A"))
    early = change(scenario, d(2), add_node(TEAM, "B"))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, founded.id)}
    with pytest.raises(ChainBroken) as raised:
        validate_lines(lines, {base: [founded], scenario: [early]}, METAMODEL)
    assert (raised.value.cause, raised.value.change_id) == ("before_branch_change", early.id)
    with pytest.raises(ChainBroken) as raised:  # the branch change is gone from the parent
        validate_lines(lines, {base: [], scenario: []}, METAMODEL)
    assert raised.value.cause == "missing_branch_change"
    validate_lines(lines, {base: [founded], scenario: [change(scenario, d(5), add_node(TEAM, "C"))]}, METAMODEL)
    # Only the lines named are replayed.
    validate_lines(lines, {base: [founded], scenario: [early]}, METAMODEL, line_ids=[base])


def test_a_correction_in_the_parent_flows_into_a_scenario_but_not_its_later_changes() -> None:
    base, scenario = uuid4(), uuid4()
    node = uuid4()
    founded = change(base, d(1), add_node(TEAM, "A", node))
    later = change(base, d(8), Edit("update_node", node, {"name": "Later"}))
    branch = change(base, d(4), Edit("update_node", node, {"name": "Branch"}))
    child = change(scenario, d(5), Edit("update_node", node, {"name": "Child"}))
    lines = {base: LineRecord(base), scenario: LineRecord(scenario, base, branch.id)}
    before = branch_prefix(lines, {base: [founded, branch, later], scenario: [child]}, scenario)
    correction = change(base, d(2), Edit("update_node", node, {"name": "Corrected"}))
    after = branch_prefix(lines, {base: [founded, branch, later, correction], scenario: [child]}, scenario)
    assert before == (founded.id, branch.id) and after == (founded.id, correction.id, branch.id)
    assert state_after(lines, {base: [founded, branch, later, correction], scenario: [child]}, METAMODEL, scenario).nodes[node].name == "Child"


def test_compaction_folds_merges_and_drops_without_changing_the_outcome() -> None:
    node, other, link = uuid4(), uuid4(), uuid4()
    base = apply_edits(State(), [add_node(TEAM, "Existing", other)], METAMODEL)
    edits = [
        add_node(TEAM, "Draft", node),
        Edit("update_node", node, {"name": "Final"}),
        Edit("update_node", other, {"name": "Renamed"}),
        Edit("update_node", other, {"description": "Twice"}),
    ]
    tidy = compact(edits, base, METAMODEL)
    assert [item.op for item in tidy] == ["add_node", "update_node"]
    assert tidy[0].payload["name"] == "Final" and tidy[1].payload == {"name": "Renamed", "description": "Twice"}
    assert apply_edits(base, tidy, METAMODEL).nodes == apply_edits(base, edits, METAMODEL).nodes

    scratch = uuid4()
    drawn = [add_node(TEAM, "Scratch", scratch), add_node(PERSON, "P", node), add_connection(MEMBER_OF, node, scratch, link),
             Edit("update_node", scratch, {"name": "Scratch 2"}), Edit("remove_node", scratch, {})]
    kept = compact(drawn, base, METAMODEL)
    assert [item.op for item in kept] == ["add_node"] and kept[0].element_id == node
    assert apply_edits(base, kept, METAMODEL).nodes.keys() == apply_edits(base, drawn, METAMODEL).nodes.keys()


def test_compaction_merges_connection_edits_and_drops_edits_that_edit_nothing() -> None:
    a, b, c, link = uuid4(), uuid4(), uuid4(), uuid4()
    base = apply_edits(State(), [add_node(PERSON, "Ada", a), add_node(TEAM, "T1", b), add_node(TEAM, "T2", c), add_connection(MEMBER_OF, a, b, link)], METAMODEL)
    # re-routes merge, and routing back to where it started is no edit at all
    back = [Edit("reroute_connection", link, {"target_node_id": str(c)}), Edit("reroute_connection", link, {"target_node_id": str(b)})]
    assert compact(back, base, METAMODEL) == []
    away = compact([Edit("reroute_connection", link, {"target_node_id": str(c)}), Edit("reroute_connection", link, {"source_node_id": str(a)}), Edit("change_connection_type", link, {"connection_type_id": str(MEMBER_OF)})], base, METAMODEL)
    assert away == [Edit("reroute_connection", link, {"target_node_id": str(c), "source_node_id": str(a)})] or away == [Edit("reroute_connection", link, {"target_node_id": str(c)})]
    # inside the change that adds the connection, re-routes fold into the add
    fresh, owns = uuid4(), uuid4()
    product = uuid4()
    added = [add_node(PRODUCT, "P", product), add_connection(OWNS, b, product, fresh), Edit("reroute_connection", fresh, {"source_node_id": str(c)}), Edit("change_connection_type", fresh, {"connection_type_id": str(OWNS)})]
    tidy = compact(added, base, METAMODEL)
    assert [item.op for item in tidy] == ["add_node", "add_connection"] and tidy[1].payload["source_node_id"] == str(c)
    assert apply_edits(base, tidy, METAMODEL).connections == apply_edits(base, added, METAMODEL).connections and owns
    # a rename back and forth is a no-op; a different final name stays one edit
    rename = [Edit("update_node", a, {"name": "X"}), Edit("update_node", a, {"name": "Ada"})]
    assert compact(rename, base, METAMODEL) == []
    assert compact([Edit("update_node", a, {"name": "X"}), Edit("update_node", a, {"name": "Y"})], base, METAMODEL) == [Edit("update_node", a, {"name": "Y"})]
    # a merge that would be invalid at the point of the earlier edit is not made
    late = uuid4()
    risky = [add_connection(OWNS, b, product, fresh), add_node(PRODUCT, "P", late), Edit("reroute_connection", fresh, {"target_node_id": str(late)})]
    assert compact(risky, apply_edits(base, [add_node(PRODUCT, "P0", product)], METAMODEL), METAMODEL) == risky


def test_compaction_leaves_edits_alone_when_unsure() -> None:
    node = uuid4()
    invalid = [Edit("remove_node", node, {})]
    assert compact(invalid, State(), METAMODEL) == invalid
    plain = [add_node(TEAM, "A", node)]
    assert compact(plain, State(), METAMODEL) == plain
    # Removing an element that existed before the change is a real edit and stays.
    base = apply_edits(State(), [add_node(TEAM, "Old", node)], METAMODEL)
    removal = [Edit("remove_node", node, {})]
    assert compact(removal, base, METAMODEL) == removal


def test_random_valid_sequences_replay_to_the_same_graph_as_a_direct_reference() -> None:
    rng = random.Random(7)
    for _ in range(25):
        line = uuid4()
        reference = State()
        changes = []
        day = 1
        for _ in range(rng.randint(3, 12)):
            edits = []
            scratch = reference.copy()
            for _ in range(rng.randint(1, 4)):
                choice = rng.choice(["person", "team", "link", "remove", "rename"])
                if choice in ("person", "team"):
                    edit = add_node(PERSON if choice == "person" else TEAM, f"n{rng.randint(0, 99)}")
                elif choice == "link":
                    people = [n for n in scratch.nodes.values() if n.node_type_id == PERSON]
                    teams = [n for n in scratch.nodes.values() if n.node_type_id == TEAM]
                    if not people or not teams:
                        continue
                    edit = add_connection(MEMBER_OF, rng.choice(people).id, rng.choice(teams).id)
                elif choice == "remove" and scratch.nodes:
                    edit = Edit("remove_node", rng.choice(list(scratch.nodes)), {})
                elif choice == "rename" and scratch.nodes:
                    edit = Edit("update_node", rng.choice(list(scratch.nodes)), {"name": f"r{rng.randint(0, 99)}"})
                else:
                    continue
                try:
                    apply_edit(scratch, edit, METAMODEL)
                except EditInvalid:
                    continue
                edits.append(edit)
            reference = scratch
            changes.append(change(line, date(2026, 1, 1).replace(day=min(day, 28)), *edits))
            day += rng.randint(0, 2)
        shuffled = list(changes)
        rng.shuffle(shuffled)
        lines = {line: LineRecord(line)}
        state = state_after(lines, {line: shuffled}, METAMODEL, line)
        assert state.nodes == reference.nodes and state.connections == reference.connections
        assert replay(chain_changes(lines, {line: changes}, line), METAMODEL).nodes == reference.nodes
