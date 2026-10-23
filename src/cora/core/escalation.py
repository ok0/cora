from __future__ import annotations

from dataclasses import dataclass

from cora.core.config import EscalationSettings

TRIGGERS = ("attempt", "ladder_exhausted", "stuck", "tripwire", "budget_fraction")


@dataclass(frozen=True)
class EscalationSignals:
    ladder_exhausted: bool = False
    tripwire: bool = False
    stuck_iterations: int = 0
    budget_fraction: float = 0.0
    check_passed: bool = False


class EscalationPolicy:
    def __init__(self, cfg: EscalationSettings) -> None:
        self.cfg = cfg

    def decide(self, s: EscalationSignals) -> str | None:
        c = self.cfg
        if not c.enabled:
            return None
        if s.ladder_exhausted:
            return "ladder_exhausted"
        if s.tripwire and c.on_tripwire:
            return "tripwire"
        if c.on_stuck_iterations > 0 and s.stuck_iterations >= c.on_stuck_iterations:
            return "stuck"
        if (
            c.on_budget_fraction > 0
            and not s.check_passed
            and s.budget_fraction >= c.on_budget_fraction
        ):
            return "budget_fraction"
        return None
