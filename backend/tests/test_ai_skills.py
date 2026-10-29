import io
import json
import re
import zipfile
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from auth_helpers import authenticate_test_client
from fastapi.testclient import TestClient
from fastmcp import Client
from mcp.types import TextContent
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.ai_change_sets import engine
from app.api.v1.ai_change_sets.schemas import OPERATION_ADAPTER
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    Metamodel,
    NodeType,
)
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.timeserie_generation.generator import generate
from app.api.v1.timeserie_generation.schemas import TimeserieGenerationSpec
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app
from app.mcp.read_server import build_read_server
from app.mcp.runtime import McpToolRuntime
from app.mcp.skills import (
    SKILL_PROMPT_NAMES,
    SKILLS_DIRECTORY,
    load_skills,
    parse_frontmatter,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIRECTORY = SKILLS_DIRECTORY.parent
DEFAULT_METAMODEL_PATH = (
    REPOSITORY_ROOT / "db" / "init" / "metamodel_state_##default##.json"
)
EXAMPLE_USER_ID = 1
SKILL_NAMES = tuple(SKILL_PROMPT_NAMES)
PRODUCTION_MCP_URLS = {
    "schatten-read": "https://schatten.lupaus.eu/api/mcp/read",
    "schatten-write": "https://schatten.lupaus.eu/api/mcp/write",
}
# Characters that start a YAML indicator or would end a plain scalar early.
YAML_UNSAFE_START = tuple("-?:,[]{}#&*!|>'\"%@`")


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@contextmanager
def _client(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    role: str = "consultant",
) -> Generator[TestClient, None, None]:
    app = create_app(settings=settings)

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        authenticate_test_client(client, session_factory, role=role)
        yield client
    app.dependency_overrides.clear()


def _mcp_enabled() -> Settings:
    return Settings.model_validate({"MCP_ENABLED": True})


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _skill_text(name: str) -> str:
    return (SKILLS_DIRECTORY / name / "SKILL.md").read_text(encoding="utf-8")


def _json_blocks(name: str) -> list[Any]:
    return [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)```", _skill_text(name), re.DOTALL)
    ]


def _seed_default_metamodel(factory: sessionmaker[Session]) -> None:
    """Load the default metamodel's types and connections as the seed does."""
    metamodel_json = _read_json(DEFAULT_METAMODEL_PATH)
    with factory() as session:
        session.add(
            User(
                user_id=EXAMPLE_USER_ID,
                name="Example",
                email="example@example.test",
                role="consultant",
            )
        )
        metamodel = Metamodel(version=metamodel_json["version"])
        session.add(metamodel)
        session.flush()
        node_types = {
            item["id"]: NodeType(
                metamodel_id=metamodel.metamodel_id,
                node_type_key=item["id"],
                name=item["display_name"],
                display_name=item["display_name"],
                ui_color=item["ui"]["color"],
                ui_shape=item["ui"]["shape"],
            )
            for item in metamodel_json["node_types"]
        }
        edge_types = {
            item["id"]: EdgeType(
                metamodel_id=metamodel.metamodel_id,
                edge_type_key=item["id"],
                name=item["display_name"],
                display_name=item["display_name"],
                ui_style=item["ui"]["style"],
                ui_source_end=item["ui"]["source_end"],
                ui_target_end=item["ui"]["target_end"],
            )
            for item in metamodel_json["edge_types"]
        }
        session.add_all([*node_types.values(), *edge_types.values()])
        session.flush()
        session.add_all(
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=edge_types[edge_type["id"]].edge_type_id,
                source_node_type_id=node_types[source_id].node_type_id,
                target_node_type_id=node_types[target_id].node_type_id,
            )
            for edge_type in metamodel_json["edge_types"]
            for connection in edge_type["allowed_connections"]
            for source_id in connection["source_node_type_ids"]
            for target_id in connection["target_node_type_ids"]
        )
        session.commit()


def test_skill_catalog_lists_every_skill_folder() -> None:
    folders = {path.name for path in SKILLS_DIRECTORY.iterdir() if path.is_dir()}

    assert folders == set(SKILL_NAMES)


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_every_skill_has_valid_frontmatter(name: str) -> None:
    frontmatter, body = parse_frontmatter(_skill_text(name))

    assert frontmatter["name"] == name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
    description = frontmatter["description"]
    assert 0 < len(description) <= 1024
    # One plain YAML scalar, and no XML tags, which claude.ai rejects.
    assert not description.startswith(YAML_UNSAFE_START)
    assert ": " not in description and " #" not in description
    assert "<" not in description and ">" not in description
    assert body.startswith("# ")


@pytest.mark.parametrize(
    "text",
    [
        "# No frontmatter\n",
        "---\nname: x\ndescription: y\n",
        "---\nname: x\n---\nbody\n",
        "---\nname: x\ndescription: y\nlicense: MIT\n---\nbody\n",
        "---\nname: x\nname: x\ndescription: y\n---\nbody\n",
        "---\nname: x\ndescription:\n---\nbody\n",
    ],
)
def test_parse_frontmatter_rejects_invalid_frontmatter(text: str) -> None:
    with pytest.raises(ValueError):
        parse_frontmatter(text)


def test_plugin_and_marketplace_manifests_are_valid() -> None:
    plugin = _read_json(PLUGIN_DIRECTORY / ".claude-plugin" / "plugin.json")
    mcp = _read_json(PLUGIN_DIRECTORY / ".mcp.json")
    marketplace = _read_json(REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json")

    assert plugin["name"] == "schatten"
    assert plugin["version"] and plugin["description"]
    assert {
        name: server["url"] for name, server in mcp["mcpServers"].items()
    } == PRODUCTION_MCP_URLS
    assert {server["type"] for server in mcp["mcpServers"].values()} == {"http"}
    assert marketplace["name"] and marketplace["owner"]["name"]
    [entry] = marketplace["plugins"]
    assert entry["name"] == plugin["name"]
    assert entry["source"].startswith("./")
    assert (REPOSITORY_ROOT / entry["source"]).resolve() == PLUGIN_DIRECTORY


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_examples_match_the_tool_contracts(name: str) -> None:
    blocks = _json_blocks(name)

    assert blocks
    for parsed in blocks:
        items = cast(
            list[dict[str, Any]], parsed if isinstance(parsed, list) else [parsed]
        )
        for item in items:
            if "type" in item:
                OPERATION_ADAPTER.validate_python(item)
            else:
                assert generate(TimeserieGenerationSpec.model_validate(item))


def test_model_building_example_runs_against_the_default_metamodel(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_default_metamodel(session_factory)
    with session_factory() as session:
        organisation_key = organisations_service.create_organisation(
            session, OrganisationCreateRequest(name="Acme Corp"), EXAMPLE_USER_ID
        ).id
    [example] = _json_blocks("schatten-model-building")
    staged = [
        engine.StagedOperation(position, OPERATION_ADAPTER.validate_python(item))
        for position, item in enumerate(example)
    ]

    with session_factory() as session:
        organisation = organisations_service.get_active_organisation(
            session, organisation_key
        )
        result = engine.execute_operations(
            session, organisation, staged, EXAMPLE_USER_ID
        )
        session.rollback()

    assert result.ok, [item.error for item in result.operations if item.error]
    assert [item.status for item in result.operations] == ["ok"] * len(staged)


@pytest.mark.anyio
async def test_read_server_prompts_return_the_skill_content() -> None:
    server = build_read_server(McpToolRuntime(sessionmaker(), anyio.CapacityLimiter(1)))

    async with Client(server) as client:
        prompts = {prompt.name: prompt for prompt in await client.list_prompts()}
        results = {
            name: await client.get_prompt(name)
            for name in ("model_building", "timeseries_generation")
        }

    assert set(prompts) == {"model_building", "timeseries_generation"}
    for skill in load_skills():
        frontmatter, body = parse_frontmatter(_skill_text(skill.name))
        assert prompts[skill.prompt_name].description == frontmatter["description"]
        assert prompts[skill.prompt_name].arguments == []
        [message] = results[skill.prompt_name].messages
        assert message.role == "user"
        assert isinstance(message.content, TextContent)
        assert message.content.text == body


@pytest.mark.parametrize("role", ["admin", "consultant"])
@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_zip_returns_the_skill_folder(
    session_factory: sessionmaker[Session], name: str, role: str
) -> None:
    with _client(session_factory, _mcp_enabled(), role=role) as client:
        response = client.get(f"/api/v1/ai/skills/{name}.zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"] == f'attachment; filename="{name}.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [f"{name}/SKILL.md"]
        assert archive.read(f"{name}/SKILL.md").decode() == _skill_text(name)


def test_skill_zip_is_the_same_bytes_every_time(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, _mcp_enabled()) as client:
        first = client.get("/api/v1/ai/skills/schatten-model-building.zip")
        second = client.get("/api/v1/ai/skills/schatten-model-building.zip")

    assert first.content == second.content


@pytest.mark.parametrize("name", ["unknown", "SKILL", "plugin"])
def test_skill_zip_of_an_unknown_skill_is_not_found(
    session_factory: sessionmaker[Session], name: str
) -> None:
    with _client(session_factory, _mcp_enabled()) as client:
        response = client.get(f"/api/v1/ai/skills/{name}.zip")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_skill_zip_is_not_registered_with_mcp_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, Settings()) as client:
        response = client.get("/api/v1/ai/skills/schatten-model-building.zip")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
