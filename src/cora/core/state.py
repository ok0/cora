from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from cora.core.errors import CoraError, InvalidTransition


class AgentState(StrEnum):
    IDLE = "idle"
    ROUTING = "routing"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    CHECKING = "checking"
    REFLECTING = "reflecting"
    DONE = "done"
    STOPPED = "stopped"
    FAILED = "failed"


TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.ROUTING},
    AgentState.ROUTING: {AgentState.THINKING, AgentState.STOPPED, AgentState.FAILED},
    AgentState.THINKING: {
        AgentState.ACTING,
        AgentState.THINKING,
        AgentState.CHECKING,
        AgentState.DONE,
        AgentState.STOPPED,
        AgentState.FAILED,
    },
    AgentState.ACTING: {AgentState.OBSERVING, AgentState.STOPPED, AgentState.FAILED},
    AgentState.OBSERVING: {AgentState.THINKING, AgentState.STOPPED, AgentState.FAILED},
    AgentState.CHECKING: {
        AgentState.DONE,
        AgentState.REFLECTING,
        AgentState.THINKING,
        AgentState.STOPPED,
        AgentState.FAILED,
    },
    AgentState.REFLECTING: {AgentState.ROUTING, AgentState.STOPPED, AgentState.FAILED},
    AgentState.DONE: {AgentState.ROUTING},
    AgentState.STOPPED: {AgentState.ROUTING, AgentState.THINKING},
    AgentState.FAILED: {AgentState.ROUTING, AgentState.THINKING},
}


class StopReason(StrEnum):
    FINAL_ANSWER = "final_answer"
    MAX_ITERATIONS = "max_iterations"
    COST_LIMIT = "cost_limit"
    CHECK_FAILED = "check_failed"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    TRIPWIRE = "tripwire"
    BUDGET_EXCEEDED = "budget_exceeded"
    POLICY_BLOCKED = "policy_blocked"
    PROVIDER_TIMEOUT = "provider_timeout"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Session:
    id: str
    task: str
    state: AgentState = AgentState.IDLE
    attempt: int = 0
    iteration: int = 0
    total_iterations: int = 0
    model_id: str | None = None
    tier: str | None = None
    reflections: list[str] = field(default_factory=list)
    memory: dict = field(default_factory=dict)
    meter: list[dict] = field(default_factory=list)
    stop_reason: str | None = None
    final_answer: str | None = None
    check_command: str | None = None
    last_failure: str | None = None
    delegations: int = 0
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    tool_groups: list[str] = field(default_factory=list)
    sensor: bool = False
    check_runs: int = 0
    sensor_retries: int = 0
    sensor_calls: int = 0
    sensor_cost_usd: float = 0.0
    escalated: bool = False
    explore_calls: int = 0
    delegation_stats: dict = field(default_factory=dict)
    budget: dict | None = None
    check_source: str | None = None
    test_hashes: dict = field(default_factory=dict)
    selftest: bool = False
    selftest_result: dict | None = None
    ladder_reflected: bool = False
    ladder_exhausted: bool = False
    escalation_trigger: str | None = None
    escalated_at_check: int = 0

    def transition(self, to: AgentState) -> None:
        if to not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {to.value}")
        self.state = to

    def force_state(self, to: AgentState) -> None:
        self.state = to

    def to_dict(self) -> dict:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        data = dict(d)
        data["state"] = AgentState(data["state"])
        return cls(**data)


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def dir_for(self, session_id: str) -> Path:
        return self.root / session_id

    def save(self, s: Session) -> Path:
        s.updated_at = _utc_now()
        directory = self.dir_for(s.id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "session.json"
        tmp = directory / "session.json.tmp"
        tmp.write_text(
            json.dumps(s.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, target)
        return target

    def load(self, session_id: str) -> Session:
        path = self.dir_for(session_id) / "session.json"
        if not path.exists():
            raise CoraError(f"session not found: {session_id}")
        return Session.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "session.json").exists())
