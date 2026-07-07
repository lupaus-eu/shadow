from copy import deepcopy
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.v1.org_states.models import OrgState, Scenario
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
    TypeAttribute,
)
from app.api.v1.org_twin_structure.schemas import (
    BulkPositionUpdate,
    GraphEdgeCreateRequest,
    GraphEdgePatchRequest,
    GraphEdgeResponse,
    GraphNodeCreateRequest,
    GraphNodePatchRequest,
    GraphNodeResponse,
    GraphResponse,
    Position,
)
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.service import get_active_organisation

ALLOWED_ATTR_DATA_TYPES = {
    "string",
    "int",
    "float",
    "bool",
    "date",
    "datetime",
    "enum",
    "list",
}
ALLOWED_NODE_SHAPES = {
    "rectangle",
    "round-rectangle",
    "ellipse",
    "diamond",
    "hexagon",
}
ALLOWED_EDGE_ENDINGS = {"none", "arrow", "circle", "diamond"}


def get_graph(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
) -> GraphResponse:
    organisation, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    return to_graph_response(session, organisation, scenario, org_state)


def create_graph_node(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: GraphNodeCreateRequest,
) -> GraphNodeResponse:
    organisation, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    metamodel = _get_active_organisation_metamodel(session, organisation)
    node_type = _get_active_node_type(session, metamodel, payload.node_type_id)
    _ensure_node_key_available(session, scenario, payload.id)

    node = GraphNode(
        scenario_id=scenario.scenario_id,
        node_key=payload.id,
        name=payload.name,
        description=payload.description,
        node_type_id=node_type.node_type_id,
        create_date=org_state.target_date,
        position_x=payload.position.x if payload.position is not None else None,
        position_y=payload.position.y if payload.position is not None else None,
        attributes=payload.attributes,
    )
    session.add(node)
    session.commit()
    session.refresh(node)

    return to_graph_node_response(session, node)


def patch_graph_node(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    node_key: str,
    payload: GraphNodePatchRequest,
) -> GraphNodeResponse:
    organisation, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    node = _get_visible_graph_node(session, scenario, org_state, node_key)
    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data and payload.name is not None:
        node.name = payload.name
    if "description" in update_data:
        node.description = payload.description
    if "node_type_id" in update_data and payload.node_type_id is not None:
        metamodel = _get_active_organisation_metamodel(session, organisation)
        node_type = _get_active_node_type(session, metamodel, payload.node_type_id)
        _ensure_node_type_change_keeps_edges_allowed(
            session,
            scenario,
            metamodel,
            node,
            node_type.node_type_id,
        )
        node.node_type_id = node_type.node_type_id
    if "position" in update_data:
        _apply_position(node, payload.position)
    if "attributes" in update_data and payload.attributes is not None:
        node.attributes = payload.attributes

    node.modified_time = datetime.now(UTC)
    session.commit()
    session.refresh(node)

    return to_graph_node_response(session, node)


def soft_delete_graph_node(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    node_key: str,
) -> None:
    _, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    node = _get_visible_graph_node(session, scenario, org_state, node_key)
    now = datetime.now(UTC)

    connected_edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.scenario_id == scenario.scenario_id,
            GraphEdge.deleted_time.is_(None),
            or_(
                GraphEdge.source_graph_node_id == node.graph_node_id,
                GraphEdge.target_graph_node_id == node.graph_node_id,
            ),
        ),
    ).all()
    for edge in connected_edges:
        edge.deleted_time = now
        edge.modified_time = now

    node.deleted_time = now
    node.modified_time = now
    session.commit()


def create_graph_edge(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: GraphEdgeCreateRequest,
) -> GraphEdgeResponse:
    organisation, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    metamodel = _get_active_organisation_metamodel(session, organisation)
    edge_type = _get_active_edge_type(session, metamodel, payload.edge_type_id)
    source_node = _get_visible_graph_node(
        session,
        scenario,
        org_state,
        payload.source_node_id,
    )
    target_node = _get_visible_graph_node(
        session,
        scenario,
        org_state,
        payload.target_node_id,
    )
    _ensure_connection_is_allowed(
        session,
        metamodel,
        edge_type,
        source_node,
        target_node,
    )
    _ensure_edge_key_available(session, scenario, payload.id)

    edge = GraphEdge(
        scenario_id=scenario.scenario_id,
        edge_key=payload.id,
        name=payload.name,
        description=payload.description,
        edge_type_id=edge_type.edge_type_id,
        source_graph_node_id=source_node.graph_node_id,
        target_graph_node_id=target_node.graph_node_id,
        create_date=org_state.target_date,
        attributes=payload.attributes,
    )
    session.add(edge)
    session.commit()
    session.refresh(edge)

    return to_graph_edge_response(session, edge)


def patch_graph_edge(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    edge_key: str,
    payload: GraphEdgePatchRequest,
) -> GraphEdgeResponse:
    organisation, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    edge = _get_visible_graph_edge(session, scenario, org_state, edge_key)
    update_data = payload.model_dump(exclude_unset=True)

    metamodel = _get_active_organisation_metamodel(session, organisation)
    edge_type = (
        _get_active_edge_type(session, metamodel, payload.edge_type_id)
        if "edge_type_id" in update_data and payload.edge_type_id is not None
        else _get_active_edge_type_by_id(session, metamodel, edge.edge_type_id)
    )
    source_node = (
        _get_visible_graph_node(session, scenario, org_state, payload.source_node_id)
        if "source_node_id" in update_data and payload.source_node_id is not None
        else _get_active_graph_node_by_id(
            session,
            scenario,
            edge.source_graph_node_id,
        )
    )
    target_node = (
        _get_visible_graph_node(session, scenario, org_state, payload.target_node_id)
        if "target_node_id" in update_data and payload.target_node_id is not None
        else _get_active_graph_node_by_id(
            session,
            scenario,
            edge.target_graph_node_id,
        )
    )

    connection_fields_updated = (
        "edge_type_id" in update_data
        or "source_node_id" in update_data
        or "target_node_id" in update_data
    )
    if connection_fields_updated:
        _ensure_connection_is_allowed(
            session,
            metamodel,
            edge_type,
            source_node,
            target_node,
        )
        edge.edge_type_id = edge_type.edge_type_id
        edge.source_graph_node_id = source_node.graph_node_id
        edge.target_graph_node_id = target_node.graph_node_id
    if "name" in update_data and payload.name is not None:
        edge.name = payload.name
    if "description" in update_data:
        edge.description = payload.description
    if "attributes" in update_data and payload.attributes is not None:
        edge.attributes = payload.attributes

    edge.modified_time = datetime.now(UTC)
    session.commit()
    session.refresh(edge)

    return to_graph_edge_response(session, edge)


def soft_delete_graph_edge(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    edge_key: str,
) -> None:
    _, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    edge = _get_visible_graph_edge(session, scenario, org_state, edge_key)
    now = datetime.now(UTC)

    edge.deleted_time = now
    edge.modified_time = now
    session.commit()


def bulk_update_positions(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: BulkPositionUpdate,
) -> GraphResponse:
    organisation, scenario, org_state = _get_active_context(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )
    node_ids = [position.node_id for position in payload.positions]
    if len(node_ids) != len(set(node_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bulk position update contains duplicate node ids.",
        )

    nodes_by_key = {
        node.node_key: node
        for node in session.scalars(
            select(GraphNode).where(
                GraphNode.scenario_id == scenario.scenario_id,
                GraphNode.node_key.in_(node_ids),
                GraphNode.create_date <= org_state.target_date,
                GraphNode.deleted_time.is_(None),
            ),
        ).all()
    }
    missing_node_ids = [node_id for node_id in node_ids if node_id not in nodes_by_key]
    if missing_node_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph node '{missing_node_ids[0]}' not found.",
        )

    now = datetime.now(UTC)
    for position in payload.positions:
        node = nodes_by_key[position.node_id]
        node.position_x = position.x
        node.position_y = position.y
        node.modified_time = now

    session.commit()

    return to_graph_response(session, organisation, scenario, org_state)


def copy_active_default_metamodel(
    session: Session,
    organisation: Organisation,
) -> Metamodel:
    source = _get_active_default_metamodel(session)
    copied = Metamodel(
        organisation_id=organisation.organisation_id,
        version=source.version,
    )
    session.add(copied)
    session.flush()

    node_type_id_map = _copy_node_types(session, source, copied)
    edge_type_id_map = _copy_edge_types(session, source, copied)
    _copy_type_attributes(
        session,
        source,
        copied,
        node_type_id_map,
        edge_type_id_map,
    )
    _copy_allowed_connections(
        session,
        source,
        copied,
        node_type_id_map,
        edge_type_id_map,
    )

    return copied


def soft_delete_graph_structure_for_scenario(
    session: Session,
    scenario_id: int,
    deleted_time: datetime,
) -> None:
    graph_edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.scenario_id == scenario_id,
            GraphEdge.deleted_time.is_(None),
        ),
    ).all()
    graph_nodes = session.scalars(
        select(GraphNode).where(
            GraphNode.scenario_id == scenario_id,
            GraphNode.deleted_time.is_(None),
        ),
    ).all()

    for edge in graph_edges:
        edge.deleted_time = deleted_time
        edge.modified_time = deleted_time

    for node in graph_nodes:
        node.deleted_time = deleted_time
        node.modified_time = deleted_time


def soft_delete_graphs_for_org_states(
    session: Session,
    org_state_ids: list[int],
    deleted_time: datetime,
) -> None:
    if not org_state_ids:
        return

    org_states = session.scalars(
        select(OrgState)
        .where(OrgState.org_state_id.in_(org_state_ids))
        .order_by(OrgState.org_state_id),
    ).all()

    for org_state in org_states:
        graph_nodes = session.scalars(
            select(GraphNode).where(
                GraphNode.scenario_id == org_state.scenario_id,
                GraphNode.create_date == org_state.target_date,
                GraphNode.deleted_time.is_(None),
            ),
        ).all()
        graph_node_ids = [node.graph_node_id for node in graph_nodes]

        edge_filters = [
            GraphEdge.create_date == org_state.target_date,
        ]
        if graph_node_ids:
            edge_filters.append(GraphEdge.source_graph_node_id.in_(graph_node_ids))
            edge_filters.append(GraphEdge.target_graph_node_id.in_(graph_node_ids))

        graph_edges = session.scalars(
            select(GraphEdge).where(
                GraphEdge.scenario_id == org_state.scenario_id,
                GraphEdge.deleted_time.is_(None),
                or_(*edge_filters),
            ),
        ).all()

        for edge in graph_edges:
            edge.deleted_time = deleted_time
            edge.modified_time = deleted_time

        for node in graph_nodes:
            node.deleted_time = deleted_time
            node.modified_time = deleted_time


def copy_graph_snapshots_for_org_states(
    session: Session,
    copied_org_state_id_by_source_id: dict[int, int],
) -> None:
    if not copied_org_state_id_by_source_id:
        return

    source_org_states = session.scalars(
        select(OrgState)
        .where(OrgState.org_state_id.in_(list(copied_org_state_id_by_source_id)))
        .order_by(OrgState.target_date, OrgState.org_state_id),
    ).all()
    copied_org_states = session.scalars(
        select(OrgState).where(
            OrgState.org_state_id.in_(list(copied_org_state_id_by_source_id.values())),
        ),
    ).all()

    source_scenario_ids = {org_state.scenario_id for org_state in source_org_states}
    copied_scenario_ids = {org_state.scenario_id for org_state in copied_org_states}
    if len(source_scenario_ids) != 1 or len(copied_scenario_ids) != 1:
        raise _invalid_graph_copy_exception(
            "Graph copy requires one source and one copied scenario.",
        )
    if not source_org_states:
        return

    source_scenario_id = source_scenario_ids.pop()
    copied_scenario_id = copied_scenario_ids.pop()
    boundary_date = max(org_state.target_date for org_state in source_org_states)

    source_nodes = session.scalars(
        select(GraphNode)
        .where(
            GraphNode.scenario_id == source_scenario_id,
            GraphNode.create_date <= boundary_date,
            GraphNode.deleted_time.is_(None),
        )
        .order_by(GraphNode.graph_node_id),
    ).all()

    node_id_map: dict[int, int] = {}
    for source_node in source_nodes:
        copied_node = GraphNode(
            scenario_id=copied_scenario_id,
            node_key=source_node.node_key,
            name=source_node.name,
            description=source_node.description,
            node_type_id=source_node.node_type_id,
            create_date=source_node.create_date,
            position_x=source_node.position_x,
            position_y=source_node.position_y,
            attributes=deepcopy(source_node.attributes),
            timeserie_id=None,
            timeserie_secondary_id=None,
        )
        session.add(copied_node)
        session.flush()
        node_id_map[source_node.graph_node_id] = copied_node.graph_node_id

    source_edges = session.scalars(
        select(GraphEdge)
        .where(
            GraphEdge.scenario_id == source_scenario_id,
            GraphEdge.create_date <= boundary_date,
            GraphEdge.deleted_time.is_(None),
        )
        .order_by(GraphEdge.graph_edge_id),
    ).all()
    for source_edge in source_edges:
        if (
            source_edge.source_graph_node_id not in node_id_map
            or source_edge.target_graph_node_id not in node_id_map
        ):
            continue
        session.add(
            GraphEdge(
                scenario_id=copied_scenario_id,
                edge_key=source_edge.edge_key,
                name=source_edge.name,
                description=source_edge.description,
                edge_type_id=source_edge.edge_type_id,
                source_graph_node_id=node_id_map[source_edge.source_graph_node_id],
                target_graph_node_id=node_id_map[source_edge.target_graph_node_id],
                create_date=source_edge.create_date,
                attributes=deepcopy(source_edge.attributes),
            ),
        )

    session.flush()


def to_graph_response(
    session: Session,
    organisation: Organisation,
    scenario: Scenario,
    org_state: OrgState,
) -> GraphResponse:
    _get_active_organisation_metamodel(session, organisation)
    nodes = session.scalars(
        select(GraphNode)
        .where(
            GraphNode.scenario_id == scenario.scenario_id,
            GraphNode.create_date <= org_state.target_date,
            GraphNode.deleted_time.is_(None),
        )
        .order_by(GraphNode.graph_node_id),
    ).all()
    visible_node_ids = [node.graph_node_id for node in nodes]
    edges: list[GraphEdge] = []
    if visible_node_ids:
        edges = list(
            session.scalars(
                select(GraphEdge)
                .where(
                    GraphEdge.scenario_id == scenario.scenario_id,
                    GraphEdge.create_date <= org_state.target_date,
                    GraphEdge.source_graph_node_id.in_(visible_node_ids),
                    GraphEdge.target_graph_node_id.in_(visible_node_ids),
                    GraphEdge.deleted_time.is_(None),
                )
                .order_by(GraphEdge.graph_edge_id),
            ).all(),
        )

    return GraphResponse(
        id=scenario.scenario_key,
        name=scenario.name,
        description=scenario.description or "",
        nodes=[to_graph_node_response(session, node) for node in nodes],
        edges=[to_graph_edge_response(session, edge) for edge in edges],
    )


def to_graph_node_response(session: Session, node: GraphNode) -> GraphNodeResponse:
    node_type = session.get(NodeType, node.node_type_id)
    if node_type is None:
        raise _invalid_graph_exception("Graph node type is missing.")

    position = None
    if node.position_x is not None and node.position_y is not None:
        position = Position(x=node.position_x, y=node.position_y)

    return GraphNodeResponse(
        id=node.node_key,
        name=node.name,
        description=node.description or "",
        nodeTypeId=node_type.node_type_key,
        createDate=node.create_date,
        position=position,
        attributes=node.attributes,
    )


def to_graph_edge_response(session: Session, edge: GraphEdge) -> GraphEdgeResponse:
    edge_type = session.get(EdgeType, edge.edge_type_id)
    source_node = session.get(GraphNode, edge.source_graph_node_id)
    target_node = session.get(GraphNode, edge.target_graph_node_id)
    if edge_type is None:
        raise _invalid_graph_exception("Graph edge type is missing.")
    if source_node is None or target_node is None:
        raise _invalid_graph_exception("Graph edge endpoint is missing.")

    return GraphEdgeResponse(
        id=edge.edge_key,
        name=edge.name,
        description=edge.description or "",
        edgeTypeId=edge_type.edge_type_key,
        sourceNodeId=source_node.node_key,
        targetNodeId=target_node.node_key,
        createDate=edge.create_date,
        attributes=edge.attributes,
    )


def _get_active_context(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
) -> tuple[Organisation, Scenario, OrgState]:
    organisation = get_active_organisation(session, organisation_key)
    scenario = session.scalar(
        select(Scenario).where(
            Scenario.organisation_id == organisation.organisation_id,
            Scenario.scenario_key == scenario_key,
            Scenario.deleted_time.is_(None),
        ),
    )
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    org_state = session.scalar(
        select(OrgState).where(
            OrgState.scenario_id == scenario.scenario_id,
            OrgState.org_state_key == org_state_key,
            OrgState.deleted_time.is_(None),
        ),
    )
    if org_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation state not found.",
        )

    return organisation, scenario, org_state


def _get_visible_graph_node(
    session: Session,
    scenario: Scenario,
    org_state: OrgState,
    node_key: str,
) -> GraphNode:
    node = session.scalar(
        select(GraphNode).where(
            GraphNode.scenario_id == scenario.scenario_id,
            GraphNode.node_key == node_key,
            GraphNode.create_date <= org_state.target_date,
            GraphNode.deleted_time.is_(None),
        ),
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph node not found.",
        )

    return node


def _get_active_graph_node_by_id(
    session: Session,
    scenario: Scenario,
    graph_node_id: int,
) -> GraphNode:
    node = session.scalar(
        select(GraphNode).where(
            GraphNode.scenario_id == scenario.scenario_id,
            GraphNode.graph_node_id == graph_node_id,
            GraphNode.deleted_time.is_(None),
        ),
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph node not found.",
        )

    return node


def _get_visible_graph_edge(
    session: Session,
    scenario: Scenario,
    org_state: OrgState,
    edge_key: str,
) -> GraphEdge:
    edge = session.scalar(
        select(GraphEdge).where(
            GraphEdge.scenario_id == scenario.scenario_id,
            GraphEdge.edge_key == edge_key,
            GraphEdge.create_date <= org_state.target_date,
            GraphEdge.deleted_time.is_(None),
        ),
    )
    if edge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph edge not found.",
        )

    _get_visible_graph_node(
        session,
        scenario,
        org_state,
        edge_source_key(session, edge),
    )
    _get_visible_graph_node(
        session,
        scenario,
        org_state,
        edge_target_key(session, edge),
    )
    return edge


def edge_source_key(session: Session, edge: GraphEdge) -> str:
    source_node = session.get(GraphNode, edge.source_graph_node_id)
    if source_node is None:
        raise _invalid_graph_exception("Graph edge source node is missing.")
    return source_node.node_key


def edge_target_key(session: Session, edge: GraphEdge) -> str:
    target_node = session.get(GraphNode, edge.target_graph_node_id)
    if target_node is None:
        raise _invalid_graph_exception("Graph edge target node is missing.")
    return target_node.node_key


def _get_active_organisation_metamodel(
    session: Session,
    organisation: Organisation,
) -> Metamodel:
    metamodel = session.scalar(
        select(Metamodel)
        .where(
            Metamodel.organisation_id == organisation.organisation_id,
            Metamodel.deleted_time.is_(None),
        )
        .order_by(Metamodel.version.desc(), Metamodel.metamodel_id.desc())
        .limit(1),
    )
    if metamodel is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Active organisation metamodel is not configured.",
        )

    return metamodel


def _get_active_node_type(
    session: Session,
    metamodel: Metamodel,
    node_type_key: str,
) -> NodeType:
    node_type = session.scalar(
        select(NodeType).where(
            NodeType.metamodel_id == metamodel.metamodel_id,
            NodeType.node_type_key == node_type_key,
            NodeType.deleted_time.is_(None),
        ),
    )
    if node_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node type not found.",
        )

    return node_type


def _get_active_edge_type(
    session: Session,
    metamodel: Metamodel,
    edge_type_key: str,
) -> EdgeType:
    edge_type = session.scalar(
        select(EdgeType).where(
            EdgeType.metamodel_id == metamodel.metamodel_id,
            EdgeType.edge_type_key == edge_type_key,
            EdgeType.deleted_time.is_(None),
        ),
    )
    if edge_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Edge type not found.",
        )

    return edge_type


def _get_active_edge_type_by_id(
    session: Session,
    metamodel: Metamodel,
    edge_type_id: int,
) -> EdgeType:
    edge_type = session.scalar(
        select(EdgeType).where(
            EdgeType.metamodel_id == metamodel.metamodel_id,
            EdgeType.edge_type_id == edge_type_id,
            EdgeType.deleted_time.is_(None),
        ),
    )
    if edge_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Edge type not found.",
        )

    return edge_type


def _ensure_node_key_available(
    session: Session,
    scenario: Scenario,
    node_key: str,
) -> None:
    node_id = session.scalar(
        select(GraphNode.graph_node_id).where(
            GraphNode.scenario_id == scenario.scenario_id,
            GraphNode.node_key == node_key,
            GraphNode.deleted_time.is_(None),
        ),
    )
    if node_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active graph node with this id already exists.",
        )


def _ensure_edge_key_available(
    session: Session,
    scenario: Scenario,
    edge_key: str,
) -> None:
    edge_id = session.scalar(
        select(GraphEdge.graph_edge_id).where(
            GraphEdge.scenario_id == scenario.scenario_id,
            GraphEdge.edge_key == edge_key,
            GraphEdge.deleted_time.is_(None),
        ),
    )
    if edge_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active graph edge with this id already exists.",
        )


def _ensure_connection_is_allowed(
    session: Session,
    metamodel: Metamodel,
    edge_type: EdgeType,
    source_node: GraphNode,
    target_node: GraphNode,
) -> None:
    allowed_connection_id = session.scalar(
        select(AllowedConnection.allowed_connection_id).where(
            AllowedConnection.metamodel_id == metamodel.metamodel_id,
            AllowedConnection.edge_type_id == edge_type.edge_type_id,
            AllowedConnection.source_node_type_id == source_node.node_type_id,
            AllowedConnection.target_node_type_id == target_node.node_type_id,
            AllowedConnection.deleted_time.is_(None),
        ),
    )
    if allowed_connection_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Edge connection is not allowed by the active metamodel.",
        )


def _ensure_node_type_change_keeps_edges_allowed(
    session: Session,
    scenario: Scenario,
    metamodel: Metamodel,
    node: GraphNode,
    proposed_node_type_id: int,
) -> None:
    connected_edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.scenario_id == scenario.scenario_id,
            GraphEdge.deleted_time.is_(None),
            or_(
                GraphEdge.source_graph_node_id == node.graph_node_id,
                GraphEdge.target_graph_node_id == node.graph_node_id,
            ),
        ),
    ).all()

    for edge in connected_edges:
        source_node = _get_active_graph_node_by_id(
            session,
            scenario,
            edge.source_graph_node_id,
        )
        target_node = _get_active_graph_node_by_id(
            session,
            scenario,
            edge.target_graph_node_id,
        )
        source_node_type_id = (
            proposed_node_type_id
            if source_node.graph_node_id == node.graph_node_id
            else source_node.node_type_id
        )
        target_node_type_id = (
            proposed_node_type_id
            if target_node.graph_node_id == node.graph_node_id
            else target_node.node_type_id
        )
        allowed_connection_id = session.scalar(
            select(AllowedConnection.allowed_connection_id).where(
                AllowedConnection.metamodel_id == metamodel.metamodel_id,
                AllowedConnection.edge_type_id == edge.edge_type_id,
                AllowedConnection.source_node_type_id == source_node_type_id,
                AllowedConnection.target_node_type_id == target_node_type_id,
                AllowedConnection.deleted_time.is_(None),
            ),
        )
        if allowed_connection_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Node type change would invalidate connected edges.",
            )


def _apply_position(node: GraphNode, position: Position | None) -> None:
    if position is None:
        node.position_x = None
        node.position_y = None
        return

    node.position_x = position.x
    node.position_y = position.y


def _invalid_graph_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    )


def _get_active_default_metamodel(session: Session) -> Metamodel:
    metamodel = session.scalar(
        select(Metamodel)
        .where(
            Metamodel.organisation_id.is_(None),
            Metamodel.deleted_time.is_(None),
        )
        .order_by(Metamodel.version.desc(), Metamodel.metamodel_id.desc())
        .limit(1),
    )

    if metamodel is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Active default metamodel is not configured.",
        )

    return metamodel


def _copy_node_types(
    session: Session,
    source: Metamodel,
    copied: Metamodel,
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    node_types = session.scalars(
        select(NodeType)
        .where(
            NodeType.metamodel_id == source.metamodel_id,
            NodeType.deleted_time.is_(None),
        )
        .order_by(NodeType.node_type_id),
    ).all()

    for source_node_type in node_types:
        _validate_node_type(source_node_type)
        copied_node_type = NodeType(
            metamodel_id=copied.metamodel_id,
            node_type_key=source_node_type.node_type_key,
            name=source_node_type.name,
            display_name=source_node_type.display_name,
            ui_color=source_node_type.ui_color,
            ui_shape=source_node_type.ui_shape,
            timeserie_id=source_node_type.timeserie_id,
            timeserie_secondary_id=source_node_type.timeserie_secondary_id,
            timeserie_id_rule=source_node_type.timeserie_id_rule,
        )
        session.add(copied_node_type)
        session.flush()
        id_map[source_node_type.node_type_id] = copied_node_type.node_type_id

    return id_map


def _copy_edge_types(
    session: Session,
    source: Metamodel,
    copied: Metamodel,
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    edge_types = session.scalars(
        select(EdgeType)
        .where(
            EdgeType.metamodel_id == source.metamodel_id,
            EdgeType.deleted_time.is_(None),
        )
        .order_by(EdgeType.edge_type_id),
    ).all()

    for source_edge_type in edge_types:
        _validate_edge_type(source_edge_type)
        copied_edge_type = EdgeType(
            metamodel_id=copied.metamodel_id,
            edge_type_key=source_edge_type.edge_type_key,
            name=source_edge_type.name,
            display_name=source_edge_type.display_name,
            ui_style=source_edge_type.ui_style,
            ui_source_end=source_edge_type.ui_source_end,
            ui_target_end=source_edge_type.ui_target_end,
        )
        session.add(copied_edge_type)
        session.flush()
        id_map[source_edge_type.edge_type_id] = copied_edge_type.edge_type_id

    return id_map


def _copy_type_attributes(
    session: Session,
    source: Metamodel,
    copied: Metamodel,
    node_type_id_map: dict[int, int],
    edge_type_id_map: dict[int, int],
) -> None:
    type_attributes = session.scalars(
        select(TypeAttribute)
        .where(
            TypeAttribute.metamodel_id == source.metamodel_id,
            TypeAttribute.deleted_time.is_(None),
        )
        .order_by(TypeAttribute.type_attribute_id),
    ).all()

    for source_attribute in type_attributes:
        _validate_type_attribute(source_attribute)
        owner_node_type_id = _mapped_optional_id(
            source_attribute.owner_node_type_id,
            node_type_id_map,
            "node type",
        )
        owner_edge_type_id = _mapped_optional_id(
            source_attribute.owner_edge_type_id,
            edge_type_id_map,
            "edge type",
        )
        session.add(
            TypeAttribute(
                metamodel_id=copied.metamodel_id,
                owner_kind=source_attribute.owner_kind,
                owner_node_type_id=owner_node_type_id,
                owner_edge_type_id=owner_edge_type_id,
                attribute_key=source_attribute.attribute_key,
                name=source_attribute.name,
                display_name=source_attribute.display_name,
                data_type=source_attribute.data_type,
                mandatory=source_attribute.mandatory,
                max_length=source_attribute.max_length,
                multiline=source_attribute.multiline,
            ),
        )

    session.flush()


def _copy_allowed_connections(
    session: Session,
    source: Metamodel,
    copied: Metamodel,
    node_type_id_map: dict[int, int],
    edge_type_id_map: dict[int, int],
) -> None:
    allowed_connections = session.scalars(
        select(AllowedConnection)
        .where(
            AllowedConnection.metamodel_id == source.metamodel_id,
            AllowedConnection.deleted_time.is_(None),
        )
        .order_by(AllowedConnection.allowed_connection_id),
    ).all()

    for source_connection in allowed_connections:
        session.add(
            AllowedConnection(
                metamodel_id=copied.metamodel_id,
                edge_type_id=_mapped_id(
                    source_connection.edge_type_id,
                    edge_type_id_map,
                    "edge type",
                ),
                source_node_type_id=_mapped_id(
                    source_connection.source_node_type_id,
                    node_type_id_map,
                    "source node type",
                ),
                target_node_type_id=_mapped_id(
                    source_connection.target_node_type_id,
                    node_type_id_map,
                    "target node type",
                ),
                name=source_connection.name,
            ),
        )

    session.flush()


def _validate_node_type(node_type: NodeType) -> None:
    if node_type.ui_shape not in ALLOWED_NODE_SHAPES:
        raise _invalid_metamodel_exception(
            f"Invalid node shape '{node_type.ui_shape}'.",
        )


def _validate_edge_type(edge_type: EdgeType) -> None:
    if edge_type.ui_source_end not in ALLOWED_EDGE_ENDINGS:
        raise _invalid_metamodel_exception(
            f"Invalid edge source ending '{edge_type.ui_source_end}'.",
        )
    if edge_type.ui_target_end not in ALLOWED_EDGE_ENDINGS:
        raise _invalid_metamodel_exception(
            f"Invalid edge target ending '{edge_type.ui_target_end}'.",
        )


def _validate_type_attribute(type_attribute: TypeAttribute) -> None:
    if type_attribute.data_type not in ALLOWED_ATTR_DATA_TYPES:
        raise _invalid_metamodel_exception(
            f"Invalid attribute data type '{type_attribute.data_type}'.",
        )


def _mapped_optional_id(
    source_id: int | None,
    id_map: dict[int, int],
    label: str,
) -> int | None:
    if source_id is None:
        return None
    return _mapped_id(source_id, id_map, label)


def _mapped_id(source_id: int, id_map: dict[int, int], label: str) -> int:
    mapped_id = id_map.get(source_id)
    if mapped_id is None:
        raise _invalid_metamodel_exception(f"Missing copied {label}.")
    return mapped_id


def _invalid_metamodel_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    )


def _invalid_graph_copy_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    )
