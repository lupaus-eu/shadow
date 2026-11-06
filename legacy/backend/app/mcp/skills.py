"""Shadow skills, each with one source text (ADR-015).

`plugin/skills/<name>/SKILL.md` is the only copy of a skill. The Claude Code
plugin ships its folder, `GET /api/v1/ai/skills/{name}.zip` serves the folder
zipped and the Shadow MCP server serves its body as an MCP prompt. This module does
not import `fastmcp`, so the zip route works without loading it.
"""

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIRECTORY = Path(__file__).parent / "plugin" / "skills"
# Skill name -> MCP prompt name on the Shadow MCP server.
SKILL_PROMPT_NAMES = {
    "shadow-model-building": "model_building",
    "shadow-timeseries-generation": "timeseries_generation",
}
FRONTMATTER_KEYS = ("name", "description")
# A fixed timestamp keeps the zip of the same files byte-identical.
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)


class UnknownSkill(LookupError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    prompt_name: str
    description: str
    # The Markdown after the frontmatter.
    body: str


def load_skills() -> list[Skill]:
    return [_load_skill(name) for name in SKILL_PROMPT_NAMES]


def skill_zip(name: str) -> bytes:
    """Zip the skill's folder under its own name, as claude.ai uploads expect."""
    if name not in SKILL_PROMPT_NAMES:
        raise UnknownSkill(name)
    directory = SKILLS_DIRECTORY / name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            arcname = f"{name}/{path.relative_to(directory).as_posix()}"
            info = zipfile.ZipInfo(arcname, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def _load_skill(name: str) -> Skill:
    text = (SKILLS_DIRECTORY / name / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    if frontmatter["name"] != name:
        raise ValueError(f"Skill {name} declares the name {frontmatter['name']}.")
    return Skill(
        name=name,
        prompt_name=SKILL_PROMPT_NAMES[name],
        description=frontmatter["description"],
        body=body,
    )


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split `SKILL.md` into its frontmatter and body.

    The frontmatter holds exactly `name` and `description`, each a one-line
    value, so it needs no YAML parser.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        raise ValueError("SKILL.md must start with a --- frontmatter line.")
    try:
        end = next(
            index for index, line in enumerate(lines[1:], 1) if line.rstrip() == "---"
        )
    except StopIteration:
        raise ValueError("SKILL.md frontmatter is not closed with ---.") from None

    frontmatter: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator or key in frontmatter or not value.strip():
            raise ValueError(f"Invalid SKILL.md frontmatter line: {line.rstrip()}")
        frontmatter[key] = value.strip()
    if set(frontmatter) != set(FRONTMATTER_KEYS):
        raise ValueError("SKILL.md frontmatter must hold exactly name and description.")
    return frontmatter, "".join(lines[end + 1 :]).lstrip("\n")
