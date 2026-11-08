"""Why a change or a chain is invalid (ADR-0049). The causes are stable codes; the interface words them."""

from dataclasses import dataclass
from uuid import UUID

CAUSES = (
    "missing_element",
    "duplicate_element",
    "missing_type",
    "connection_not_allowed",
    "missing_endpoint",
    "self_connection",
    "duplicate_connection",
    "missing_branch_event",
    "before_branch_event",
)


class ChangeInvalid(Exception):
    """One change cannot be applied to the state it meets."""

    def __init__(self, cause: str, element_id: UUID | None = None) -> None:
        super().__init__(cause)
        self.cause = cause
        self.element_id = element_id


class ChainBroken(Exception):
    """A chain cannot be replayed: where it fails (line, event, change position) and why."""

    def __init__(self, line_id: UUID, event_id: UUID | None, position: int | None, cause: str, element_id: UUID | None = None) -> None:
        super().__init__(f"chain broken in line {line_id}: {cause}")
        self.line_id = line_id
        self.event_id = event_id
        self.position = position
        self.cause = cause
        self.element_id = element_id
