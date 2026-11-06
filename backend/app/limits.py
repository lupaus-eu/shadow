"""Operational ceilings (docs/architecture/operational-limits.md).

Creation beyond a ceiling fails with 409 and a machine-readable reason, so
a runaway client never degrades the service silently. Each ceiling is configurable; the
parent row is locked while counting so concurrent requests cannot overshoot.
"""

import os
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class Ceiling:
    name: str
    variable: str
    default: int

    @property
    def maximum(self) -> int:
        return int(os.getenv(self.variable, str(self.default)))


BILLING_CONTACT_CHANGES = Ceiling("billing_contact_changes_per_day", "LIMIT_BILLING_CONTACT_CHANGES_PER_DAY", 5)
CEILINGS = (BILLING_CONTACT_CHANGES,)


def _refuse_at(ceiling: Ceiling, count: int) -> None:
    if count >= ceiling.maximum:
        raise HTTPException(status_code=409, detail={"reason": "limit_reached", "limit": ceiling.name, "maximum": ceiling.maximum})
