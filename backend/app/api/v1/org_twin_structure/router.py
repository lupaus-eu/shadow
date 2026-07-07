from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.schemas import (
    BulkPositionUpdate,
    GraphEdgeCreateRequest,
    GraphEdgePatchRequest,
    GraphEdgeResponse,
    GraphNodeCreateRequest,
    GraphNodePatchRequest,
    GraphNodeResponse,
    GraphResponse,
    TypeCatalogResponse,
)
from app.core.database import get_db_session

router = APIRouter(prefix="/organisations", tags=["org-twin-structure"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph",
    response_model=GraphResponse,
)
def get_graph(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    session: SessionDependency,
) -> GraphResponse:
    return org_twin_structure_service.get_graph(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/types",
    response_model=TypeCatalogResponse,
)
def get_graph_type_catalog(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    session: SessionDependency,
) -> TypeCatalogResponse:
    return org_twin_structure_service.get_graph_type_catalog(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )


@router.post(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/nodes",
    response_model=GraphNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_graph_node(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: GraphNodeCreateRequest,
    session: SessionDependency,
) -> GraphNodeResponse:
    return org_twin_structure_service.create_graph_node(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        payload,
    )


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/nodes/{node_key}",
    response_model=GraphNodeResponse,
)
def patch_graph_node(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    node_key: str,
    payload: GraphNodePatchRequest,
    session: SessionDependency,
) -> GraphNodeResponse:
    return org_twin_structure_service.patch_graph_node(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        node_key,
        payload,
    )


@router.delete(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/nodes/{node_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_graph_node(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    node_key: str,
    session: SessionDependency,
) -> Response:
    org_twin_structure_service.soft_delete_graph_node(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        node_key,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/edges",
    response_model=GraphEdgeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_graph_edge(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: GraphEdgeCreateRequest,
    session: SessionDependency,
) -> GraphEdgeResponse:
    return org_twin_structure_service.create_graph_edge(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        payload,
    )


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/edges/{edge_key}",
    response_model=GraphEdgeResponse,
)
def patch_graph_edge(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    edge_key: str,
    payload: GraphEdgePatchRequest,
    session: SessionDependency,
) -> GraphEdgeResponse:
    return org_twin_structure_service.patch_graph_edge(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        edge_key,
        payload,
    )


@router.delete(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/edges/{edge_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_graph_edge(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    edge_key: str,
    session: SessionDependency,
) -> Response:
    org_twin_structure_service.soft_delete_graph_edge(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        edge_key,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}"
    "/graph/positions",
    response_model=GraphResponse,
)
def bulk_update_positions(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: BulkPositionUpdate,
    session: SessionDependency,
) -> GraphResponse:
    return org_twin_structure_service.bulk_update_positions(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        payload,
    )
