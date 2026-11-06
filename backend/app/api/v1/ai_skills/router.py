"""Skill zip download, registered only with `MCP_ENABLED=true` (ADR-015).

A business session downloads a Shadow skill's folder zipped, for upload to
claude.ai or Claude Desktop. The zip is built from the same `SKILL.md` files
that the Claude Code plugin ships and the MCP server's prompts serve.
"""

from fastapi import APIRouter, Depends, Response

from app.api.v1.auth.dependencies import AuthHttpError, require_business_request
from app.mcp.skills import UnknownSkill, skill_zip

router = APIRouter(prefix="/api/v1/ai/skills", tags=["ai"])


@router.get(
    "/{name}.zip",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
    dependencies=[Depends(require_business_request)],
)
def download_skill(name: str) -> Response:
    try:
        content = skill_zip(name)
    except UnknownSkill as exc:
        raise AuthHttpError(404, "SKILL_NOT_FOUND", "Skill not found") from exc
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )
