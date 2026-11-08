"""Model tools for agents: models, versions, canvas edits in events, metrics, simulations and analysis.

Each tool calls the same endpoint function the REST API serves, so the rules, the roles, the
read-only subscription block and the audit entries are the REST API's own. The endpoint
functions are taken from the routers, not copied.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ValidationError

from app.analysis_routes import ProposalRequest, SummaryRequest, create_analysis_router
from app.mcp_server.runtime import ToolRuntime
from app.mcp_server.tools import READ_ONLY, UNTRUSTED, WRITES
from app.metric_routes import MetricRequest, ValuesRequest, create_metric_router
from app.model_routes import ModelRequest, create_model_router
from app.simulation_routes import SimulationRequest, create_simulation_router
from app.timeline_edit_routes import ConnectionCreate, NodeCreate, create_timeline_edit_router
from app.version_routes import VersionRequest, create_version_router

REQUEST = SimpleNamespace(headers={})  # the audit entry takes only a request id from it


def _endpoints(router: APIRouter) -> dict[str, Callable[..., Any]]:
    return {route.name: route.endpoint for route in router.routes}  # type: ignore[attr-defined]


def _body(model: type[BaseModel], data: dict) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise ToolError("Invalid input: " + "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors())) from None


def register_model_tools(server: MCPServer, runtime: ToolRuntime) -> None:
    factory = runtime.session_factory

    def dependency():  # never called: the tools pass the signed-in person themselves
        raise RuntimeError

    models = _endpoints(create_model_router(session_factory=factory, authenticated_user_dependency=dependency))
    versions = _endpoints(create_version_router(session_factory=factory, authenticated_user_dependency=dependency))
    edits = _endpoints(create_timeline_edit_router(session_factory=factory, authenticated_user_dependency=dependency, clock=lambda: datetime.now(UTC)))
    metrics = _endpoints(create_metric_router(session_factory=factory, authenticated_user_dependency=dependency))
    simulations = _endpoints(create_simulation_router(session_factory=factory, authenticated_user_dependency=dependency))
    analysis = _endpoints(create_analysis_router(session_factory=factory, authenticated_user_dependency=dependency))

    async def read(organization_id: UUID, function: Callable[..., Any], **arguments: Any) -> dict:
        result = await runtime.call(lambda user: function(organization_id=organization_id, user=user, **arguments), organization_id=organization_id)
        return {"result": result, "notice": UNTRUSTED}

    async def write(organization_id: UUID, function: Callable[..., Any], **arguments: Any) -> dict:
        result = await runtime.call(lambda user: function(organization_id=organization_id, user=user, request=REQUEST, **arguments), organization_id=organization_id)
        return {"result": result, "notice": UNTRUSTED}

    @server.tool(title="List models", annotations=READ_ONLY)
    async def list_models(organization_id: UUID) -> dict:
        """List the digital-twin models of an Organization."""
        return await read(organization_id, models["list_models"])

    @server.tool(title="Get a model graph", annotations=READ_ONLY)
    async def get_model(organization_id: UUID, model_id: UUID, version_id: UUID | None = None) -> dict:
        """Get a model's versions, its node and connection types, and the nodes and connections of one version (the baseline unless version_id is given) after its last event. latest_event is the event that create_node and create_connection write into (null while the line has no events yet): pass its id (and, if you want a stale-write check, its version). version_id is also the id of the version's line."""
        return await read(organization_id, models["read_graph"], model_id=model_id, version_id=version_id)

    @server.tool(title="List the metrics of a line", annotations=READ_ONLY)
    async def list_metrics(organization_id: UUID, model_id: UUID, line_id: UUID) -> dict:
        """List the metrics (KPIs) of a line (the Base line or a Scenario; the line id is the id of a version listed by get_model). A derived metric has a formula over other metric keys."""
        return await read(organization_id, metrics["list_metrics"], model_id=model_id, line_id=line_id)

    @server.tool(title="Get a metric's monthly values", annotations=READ_ONLY)
    async def get_metric_series(organization_id: UUID, model_id: UUID, line_id: UUID, metric_id: UUID) -> dict:
        """Get the monthly values of a metric (derived metrics are calculated). Periods are first-of-month dates."""
        return await read(organization_id, metrics["read_series"], model_id=model_id, line_id=line_id, metric_id=metric_id)

    @server.tool(title="List simulations", annotations=READ_ONLY)
    async def list_simulations(organization_id: UUID, model_id: UUID, line_id: UUID) -> dict:
        """List the forecast simulations that were run on a line."""
        return await read(organization_id, simulations["list_simulations"], model_id=model_id, line_id=line_id)

    @server.tool(title="Get a simulation result", annotations=READ_ONLY)
    async def get_simulation(organization_id: UUID, model_id: UUID, line_id: UUID, simulation_id: UUID) -> dict:
        """Get a simulation's history, forecast and 95% bands per metric."""
        return await read(organization_id, simulations["read"], model_id=model_id, line_id=line_id, simulation_id=simulation_id)

    @server.tool(title="Get the analysis of a simulation", annotations=READ_ONLY)
    async def get_analysis(organization_id: UUID, model_id: UUID, simulation_id: UUID, compare_to: UUID | None = None) -> dict:
        """Get the findings of a simulation and the stored action proposals (optionally compared with another simulation)."""
        return await read(organization_id, analysis["read"], model_id=model_id, simulation_id=simulation_id, compare_to=compare_to)

    @server.tool(title="Create a model", annotations=WRITES)
    async def create_model(organization_id: UUID, name: str, description: str | None = None) -> dict:
        """Create a model with the default node and connection types and an empty baseline. Owner or Admin only."""
        return await write(organization_id, models["create_model"], body=_body(ModelRequest, {"name": name, "description": description}))

    @server.tool(title="Add a node", annotations=WRITES)
    async def create_node(organization_id: UUID, model_id: UUID, event_id: UUID, node_type_id: UUID, name: str, description: str | None = None, x: float = 0, y: float = 0, expected_version: int | None = None) -> dict:
        """Add a node as a change inside an event (event_id is the latest_event of get_model, or any event of a line you may write). Use a node_type_id from get_model. The result holds the new node's id. expected_version is the event's current version (optional; refused with a conflict when stale). A chain that would break is refused with the reason and nothing is saved."""
        body = _body(NodeCreate, {"expected_version": expected_version, "node_type_id": node_type_id, "name": name, "description": description, "x": x, "y": y})
        return await write(organization_id, edits["create_node"], model_id=model_id, event_id=event_id, body=body)

    @server.tool(title="Connect two nodes", annotations=WRITES)
    async def create_connection(organization_id: UUID, model_id: UUID, event_id: UUID, connection_type_id: UUID, source_node_id: UUID, target_node_id: UUID, expected_version: int | None = None) -> dict:
        """Connect two nodes as a change inside an event (see create_node for event_id and expected_version). The model's metamodel must allow the connection type between their node types; otherwise the call is refused with the reason and nothing is saved."""
        body = _body(ConnectionCreate, {"expected_version": expected_version, "connection_type_id": connection_type_id, "source_node_id": source_node_id, "target_node_id": target_node_id})
        return await write(organization_id, edits["create_connection"], model_id=model_id, event_id=event_id, body=body)

    @server.tool(title="Create a version", annotations=WRITES)
    async def create_version(organization_id: UUID, model_id: UUID, name: str, base_version_id: UUID | None = None, description: str | None = None) -> dict:
        """Fork a version (the baseline unless base_version_id is given): the new version copies the graph and the metrics."""
        body = _body(VersionRequest, {"name": name, "description": description, "base_version_id": base_version_id})
        return await write(organization_id, versions["create_version"], model_id=model_id, body=body)

    @server.tool(title="Create a metric", annotations=WRITES)
    async def create_metric(organization_id: UUID, model_id: UUID, line_id: UUID, key: str, name: str, unit: str | None = None, formula: str | None = None, node_id: UUID | None = None) -> dict:
        """Create a metric. key is lower-case letters, digits and underscores; give a formula over other metric keys for a derived metric."""
        body = _body(MetricRequest, {"key": key, "name": name, "unit": unit, "formula": formula, "node_id": node_id})
        return await write(organization_id, metrics["create_metric"], model_id=model_id, line_id=line_id, body=body)

    @server.tool(title="Set monthly values of a metric", annotations=WRITES)
    async def set_metric_values(organization_id: UUID, model_id: UUID, line_id: UUID, metric_id: UUID, values: list[dict]) -> dict:
        """Set monthly values of an input metric. values is a list of {"period": "YYYY-MM-01", "value": number}; a null value clears the month."""
        return await write(organization_id, metrics["write_values"], model_id=model_id, line_id=line_id, metric_id=metric_id, body=_body(ValuesRequest, {"values": values}))

    @server.tool(title="Run a simulation", annotations=WRITES)
    async def run_simulation(organization_id: UUID, model_id: UUID, line_id: UUID, name: str, method: str = "linear", horizon_months: int = 12, adjustments: list[dict] | None = None) -> dict:
        """Forecast the metrics of a line. adjustments is a list of {"metric_key": ..., "change_pct": ...} what-if changes."""
        body = _body(SimulationRequest, {"name": name, "method": method, "horizon_months": horizon_months, "adjustments": adjustments or []})
        return await write(organization_id, simulations["run"], model_id=model_id, line_id=line_id, body=body)

    @server.tool(title="Generate the analysis of a simulation", annotations=WRITES)
    async def generate_analysis(organization_id: UUID, model_id: UUID, simulation_id: UUID, compare_to: UUID | None = None) -> dict:
        """Generate the findings and action proposals of a simulation. Decisions already taken on proposals are kept."""
        return await write(organization_id, analysis["generate"], model_id=model_id, simulation_id=simulation_id, compare_to=compare_to)

    @server.tool(title="Write the summary of a simulation's analysis", annotations=WRITES)
    async def set_analysis_summary(organization_id: UUID, model_id: UUID, simulation_id: UUID, text: str) -> dict:
        """Store your own written summary (1-4000 characters, plain text) of a simulation's analysis; it replaces the previous summary and is shown to the Organization labelled as written by an agent. Base it on get_analysis and get_simulation."""
        return await write(organization_id, analysis["set_summary"], model_id=model_id, simulation_id=simulation_id, body=_body(SummaryRequest, {"text": text}))

    @server.tool(title="Add an action proposal to an analysis", annotations=WRITES)
    async def add_proposal(organization_id: UUID, model_id: UUID, simulation_id: UUID, metric_key: str, title: str, rationale: str, severity: str = "medium") -> dict:
        """Propose one action for a metric of a simulation (metric_key as in get_analysis findings; severity high, medium or low; title up to 200 and rationale up to 1500 characters, citing the figures it rests on). One agent proposal exists per metric: repeating the call replaces it and puts it back to 'proposed' for a new decision. People accept or dismiss proposals in the web application."""
        return await write(organization_id, analysis["set_proposal"], model_id=model_id, simulation_id=simulation_id, metric_key=metric_key, body=_body(ProposalRequest, {"title": title, "rationale": rationale, "severity": severity}))
