from copy import deepcopy
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
    TypeAttribute,
)
from app.api.v1.organisations.models import Organisation

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


def soft_delete_graphs_for_org_states(
    session: Session,
    org_state_ids: list[int],
    deleted_time: datetime,
) -> None:
    if not org_state_ids:
        return

    graphs = session.scalars(
        select(Graph).where(
            Graph.org_state_id.in_(org_state_ids),
            Graph.deleted_time.is_(None),
        ),
    ).all()
    graph_ids = [graph.graph_id for graph in graphs]

    if graph_ids:
        graph_edges = session.scalars(
            select(GraphEdge).where(
                GraphEdge.graph_id.in_(graph_ids),
                GraphEdge.deleted_time.is_(None),
            ),
        ).all()
        graph_nodes = session.scalars(
            select(GraphNode).where(
                GraphNode.graph_id.in_(graph_ids),
                GraphNode.deleted_time.is_(None),
            ),
        ).all()

        for graph_edge in graph_edges:
            graph_edge.deleted_time = deleted_time
            graph_edge.modified_time = deleted_time

        for graph_node in graph_nodes:
            graph_node.deleted_time = deleted_time
            graph_node.modified_time = deleted_time

    for graph in graphs:
        graph.deleted_time = deleted_time
        graph.modified_time = deleted_time


def copy_graph_snapshots_for_org_states(
    session: Session,
    copied_org_state_id_by_source_id: dict[int, int],
) -> None:
    if not copied_org_state_id_by_source_id:
        return

    source_org_state_ids = list(copied_org_state_id_by_source_id)
    source_graphs = session.scalars(
        select(Graph)
        .where(
            Graph.org_state_id.in_(source_org_state_ids),
            Graph.deleted_time.is_(None),
        )
        .order_by(Graph.org_state_id, Graph.graph_id),
    ).all()

    for source_graph in source_graphs:
        copied_org_state_id = copied_org_state_id_by_source_id.get(
            source_graph.org_state_id,
        )
        if copied_org_state_id is None:
            raise _invalid_graph_copy_exception(
                "Missing copied organisation state for graph.",
            )

        copied_graph = Graph(
            org_state_id=copied_org_state_id,
            name=source_graph.name,
            description=source_graph.description,
        )
        session.add(copied_graph)
        session.flush()

        graph_node_id_map = _copy_graph_nodes(session, source_graph, copied_graph)
        _copy_graph_edges(session, source_graph, copied_graph, graph_node_id_map)


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


def _copy_graph_nodes(
    session: Session,
    source: Graph,
    copied: Graph,
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    graph_nodes = session.scalars(
        select(GraphNode)
        .where(
            GraphNode.graph_id == source.graph_id,
            GraphNode.deleted_time.is_(None),
        )
        .order_by(GraphNode.graph_node_id),
    ).all()

    for source_node in graph_nodes:
        copied_node = GraphNode(
            graph_id=copied.graph_id,
            node_key=source_node.node_key,
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
        id_map[source_node.graph_node_id] = copied_node.graph_node_id

    return id_map


def _copy_graph_edges(
    session: Session,
    source: Graph,
    copied: Graph,
    graph_node_id_map: dict[int, int],
) -> None:
    graph_edges = session.scalars(
        select(GraphEdge)
        .where(
            GraphEdge.graph_id == source.graph_id,
            GraphEdge.deleted_time.is_(None),
        )
        .order_by(GraphEdge.graph_edge_id),
    ).all()

    for source_edge in graph_edges:
        session.add(
            GraphEdge(
                graph_id=copied.graph_id,
                edge_key=source_edge.edge_key,
                edge_type_id=source_edge.edge_type_id,
                source_graph_node_id=_mapped_id(
                    source_edge.source_graph_node_id,
                    graph_node_id_map,
                    "source graph node",
                ),
                target_graph_node_id=_mapped_id(
                    source_edge.target_graph_node_id,
                    graph_node_id_map,
                    "target graph node",
                ),
                create_date=source_edge.create_date,
                attributes=deepcopy(source_edge.attributes),
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
