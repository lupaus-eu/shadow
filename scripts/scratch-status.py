#!/usr/bin/env python3
"""Render the local feature portfolio from `.scratch` status metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".scratch"
DONE = {"implemented", "resolved"}
ACTIVE = {"claimed"}
ACTIONABLE = {"claimed", "ready-for-agent", "needs-info", "ready-for-human"}
TICKET_STATUSES = {
    "needs-triage",
    "needs-info",
    "ready-for-human",
    "ready-for-agent",
    "claimed",
    "implemented",
    "resolved",
    "wontfix",
}


@dataclass(frozen=True)
class Ticket:
    number: str
    title: str
    status: str
    blockers: tuple[str, ...]
    open_criteria: int
    link: str


def _field(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "—"


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}[ \t]*\n(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _title(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "Nimetön työ"


def _ticket_title(text: str) -> str:
    return re.sub(r"^Ticket\s+\d+:\s*", "", _title(text))


def _relative(path: Path) -> str:
    return path.relative_to(SCRATCH).as_posix()


def _blockers(text: str) -> tuple[str, ...]:
    """Ticket numbers from a `Blocked by: 01, 02` line or `## Blocked by` list items."""
    line = _field(text, "Blocked by")
    if line != "—":
        numbers = re.findall(r"\b(\d{2})\b", line)
    else:
        numbers = re.findall(r"^-\s+(\d{2})\b", _section(text, "Blocked by"), re.MULTILINE)
    return tuple(dict.fromkeys(numbers))


def _validated(status: str, where: str) -> str:
    if status not in TICKET_STATUSES:
        raise ValueError(
            f"{where}: invalid ticket status {status!r}; see docs/agents/triage-labels.md"
        )
    return status


def _tickets(work: Path) -> list[Ticket]:
    result = []
    for path in sorted((work / "issues").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        result.append(
            Ticket(
                number=path.name[:2],
                title=_ticket_title(text),
                status=_validated(_field(text, "Status"), path.relative_to(ROOT).as_posix()),
                blockers=_blockers(text),
                open_criteria=len(re.findall(r"^- \[ \]", _section(text, "Acceptance criteria"), re.MULTILINE)),
                link=_relative(path),
            )
        )
    return result


def _unblocked(ticket: Ticket, tickets: list[Ticket]) -> bool:
    status = {t.number: t.status for t in tickets}
    return all(status.get(number) in DONE for number in ticket.blockers)


def _next_ticket(tickets: list[Ticket]) -> Ticket | None:
    actionable = [t for t in tickets if t.status in ACTIONABLE]
    return next((t for t in actionable if _unblocked(t, tickets)), actionable[0] if actionable else None)


def _delivery_status(source_status: str, tickets: list[Ticket]) -> str:
    if source_status == "wontfix":
        return "wontfix"
    if not tickets:
        return source_status
    statuses = {ticket.status for ticket in tickets} - {"wontfix"}
    if statuses <= DONE:
        return "implemented"
    if statuses & ACTIVE:
        return "in progress"
    if "needs-info" in statuses or "ready-for-human" in statuses:
        return "needs decision"
    if "ready-for-agent" in statuses:
        return "ready for implementation"
    return "planned"


def _blocker_text(ticket: Ticket, tickets: list[Ticket]) -> str:
    status = {t.number: t.status for t in tickets}
    pending = [n for n in ticket.blockers if status.get(n) not in DONE]
    return ", ".join(pending) if pending else "—"


def _row(work: Path, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    tickets = _tickets(work)
    completed = sum(ticket.status in DONE for ticket in tickets)
    next_ticket = _next_ticket(tickets)
    if next_ticket is None:
        next_text, blocker = "—", "—"
    else:
        next_text = f"[{next_ticket.number} {next_ticket.title}]({next_ticket.link}) — {next_ticket.status}"
        blocker = _blocker_text(next_ticket, tickets)
    return (
        f"| [{_title(text)}]({_relative(source)}) | "
        f"{_delivery_status(_field(text, 'Status'), tickets)} | {completed}/{len(tickets)} | {next_text} | {blocker} |"
    )


def _open_rows(work: Path) -> list[str]:
    tickets = _tickets(work)
    rows = []
    for ticket in tickets:
        if ticket.status in DONE or ticket.status == "wontfix":
            continue
        frontier = "kyllä" if _unblocked(ticket, tickets) else "ei"
        rows.append(
            f"| [{ticket.number} {ticket.title}]({ticket.link}) | {ticket.status} | "
            f"{ticket.open_criteria} | {frontier} | {_blocker_text(ticket, tickets)} |"
        )
    return rows


def _works() -> tuple[list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    features, technical = [], []
    for work in sorted(SCRATCH.iterdir()):
        if not work.is_dir() or work.name.startswith("_"):
            continue
        if work.name.startswith("tech-"):
            design = work / "technical-design.md"
            if design.exists():
                technical.append((work, design))
        else:
            prd = work / "PRD.md"
            if prd.exists():
                features.append((work, prd))
    return features, technical


def render() -> str:
    features, technical = _works()
    header = "| {} | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |"
    divider = "| --- | --- | ---: | --- | --- |"
    open_section = []
    for work, source in features + technical:
        rows = _open_rows(work)
        if not rows:
            continue
        open_section += [
            f"### {_title(source.read_text(encoding='utf-8'))}",
            "",
            "| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |",
            "| --- | --- | ---: | --- | --- |",
            *rows,
            "",
        ]
    if not open_section:
        open_section = ["Ei avoimia ticketejä.", ""]

    return "\n".join(
        [
            "# Shadowin feature-portfolio",
            "",
            "> Tämä näkymä muodostetaan `.scratch`-tiedostojen `Status:`-riveistä ja hyväksymiskriteerien valintaruuduista. Päivitä se komennolla `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` aina, kun feature tai ticket etenee.",
            "",
            header.format("Feature"),
            divider,
            *[_row(work, source) for work, source in features],
            "",
            "## Tekniset työt",
            "",
            "> Tekninen työ seurataan omana listanaan; se ei muuta tuotefeatureiden toteutusastetta.",
            "",
            header.format("Tekninen työ"),
            divider,
            *[_row(work, source) for work, source in technical],
            "",
            "## Avoimet ticketit",
            "",
            "> *Aloitettavissa* tarkoittaa, että kaikki ticketin estäjät ovat `implemented` tai `resolved`. *Avoimia kriteerejä* laskee ticketin rastittamattomat hyväksymiskriteerit.",
            "",
            *open_section,
            "## Tilan tulkinta",
            "",
            "- **implemented**: kaikki ticketit ovat `implemented` tai `resolved`.",
            "- **in progress**: vähintään yksi ticket on varattu (`claimed`).",
            "- **needs decision**: vähintään yksi ticket odottaa liiketoiminta-, suunnittelu- tai ympäristöpäätöstä (`needs-info`, `ready-for-human`).",
            "- **ready for implementation**: ticketit ovat valmiita toteutukseen (`ready-for-agent`), eikä mikään odota päätöstä.",
            "- **Seuraava ticket**: ensimmäinen toimenpidettä odottava ticket, jonka estäjät ovat valmiit; jos sellaista ei ole, ensimmäinen toimenpidettä odottava ticket.",
            "",
            "Tekniset työt ovat erillään tuotefeatureista, jotta niiden tila ei sekoita tuotetoimituksen edistymistä.",
            "",
        ]
    )


if __name__ == "__main__":
    print(render(), end="")
