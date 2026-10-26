from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from cora.core.agent import Agent, RunResult
from cora.core.budget import BudgetGovernor, BudgetLimits, BudgetUsage
from cora.core.errors import ConfigError, CoraError, WorkspaceViolation
from cora.core.metering import CostMeter
from cora.core.observability import EventLog
from cora.core.outcome import OUTCOME_KEYS, error_outcome, exit_code, outcome_stop_reason
from cora.core.policy import approval_mode_of
from cora.core.state import new_session_id
from cora.core.tools.base import ToolContext
from cora.core.tools.builtin import RunShellTool

PLAN_KEYS = frozenset({"goal", "milestones"})
MILESTONE_KEYS = frozenset({"id", "title", "task", "check", "conditions", "ungated"})
CONDITION_FIELDS = {"command": "cmd", "file_exists": "path"}
GATE_FAILED = "gate_failed"
STATUSES = ("pending", "running", "completed", "failed", "interrupted")
CHECKPOINT_FILE = "checkpoint.json"
CHECKPOINT_VERSION = 1
RUN_ID_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")
PROJECT_KEYS = (
    *(k for k in OUTCOME_KEYS if k != "profile"),
    "run_id",
    "milestones",
    "ungated_milestones",
)


class PlanError(ConfigError): ...


class CheckpointError(CoraError): ...


@dataclass(frozen=True)
class Condition:
    kind: str
    cmd: str | None = None
    path: str | None = None

    def to_dict(self) -> dict:
        if self.kind == "command":
            return {"kind": "command", "cmd": self.cmd}
        return {"kind": "file_exists", "path": self.path}

    def describe(self) -> str:
        if self.kind == "command":
            return f"command `{self.cmd}`"
        return f"file_exists `{self.path}`"


@dataclass(frozen=True)
class Milestone:
    id: str
    title: str
    task: str
    check: str | None = None
    conditions: tuple[Condition, ...] = ()
    ungated: bool = False

    def to_dict(self) -> dict:
        data: dict[str, Any] = {"id": self.id, "title": self.title, "task": self.task}
        if self.check is not None:
            data["check"] = self.check
        if self.conditions:
            data["conditions"] = [c.to_dict() for c in self.conditions]
        if self.ungated:
            data["ungated"] = True
        return data


@dataclass(frozen=True)
class ProjectPlan:
    goal: str
    milestones: tuple[Milestone, ...]

    def to_dict(self) -> dict:
        return {"goal": self.goal, "milestones": [m.to_dict() for m in self.milestones]}

    @property
    def ids(self) -> list[str]:
        return [m.id for m in self.milestones]


def parse_conditions(
    raw: Any, where: str, bad: Callable[[str], PlanError]
) -> tuple[Condition, ...]:
    if not isinstance(raw, list):
        raise bad(f"{where}: 'conditions' must be an array of tables")
    out: list[Condition] = []
    for j, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise bad(f"{where}: condition {j} must be a table")
        if "kind" not in item:
            raise bad(f"{where}: condition {j}: missing 'kind' (allowed: command, file_exists)")
        kind = item["kind"]
        if not isinstance(kind, str) or kind not in CONDITION_FIELDS:
            raise bad(
                f"{where}: condition {j}: unknown kind {kind!r} (allowed: command, file_exists)"
            )
        field_name = CONDITION_FIELDS[kind]
        unknown = sorted(set(item) - {"kind", field_name})
        if unknown:
            raise bad(
                f"{where}: condition {j}: unknown key '{unknown[0]}' (allowed: kind, {field_name})"
            )
        value = item.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise bad(f"{where}: condition {j}: '{field_name}' must be a non-empty string")
        value = value.strip()
        if kind == "command":
            out.append(Condition("command", cmd=value))
            continue
        p = value.replace("\\", "/")
        if p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p) or ".." in PurePosixPath(p).parts:
            raise bad(
                f"{where}: condition {j}: 'path' must be relative to the workspace "
                "(no absolute path, no '..')"
            )
        out.append(Condition("file_exists", path=value))
    return tuple(out)


def parse_plan(data: Any, source: str) -> ProjectPlan:
    def bad(msg: str) -> PlanError:
        return PlanError(f"invalid plan {source}: {msg}")

    if not isinstance(data, dict):
        raise bad("must be a TOML table")
    unknown = sorted(set(data) - PLAN_KEYS)
    if unknown:
        raise bad(f"unknown key '{unknown[0]}' (allowed: goal, milestones)")
    if "goal" not in data:
        raise bad("missing 'goal' (string)")
    if not isinstance(data["goal"], str):
        raise bad("'goal' must be a string")
    if "milestones" not in data or (
        isinstance(data["milestones"], list) and not data["milestones"]
    ):
        raise bad("no milestones ([[milestones]] is missing or empty)")
    raw = data["milestones"]
    if not isinstance(raw, list):
        raise bad("'milestones' must be an array of tables ([[milestones]])")

    milestones: list[Milestone] = []
    seen: set[str] = set()
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise bad(f"milestone {i} must be a table")
        unknown = sorted(set(item) - MILESTONE_KEYS)
        if unknown:
            raise bad(
                f"milestone {i}: unknown key '{unknown[0]}' "
                "(allowed: check, conditions, id, task, title, ungated)"
            )
        mid = item.get("id")
        if not isinstance(mid, str) or not mid.strip():
            raise bad(f"milestone {i}: 'id' must be a non-empty string")
        mid = mid.strip()
        if mid in seen:
            raise bad(f"milestone {i}: duplicate id '{mid}'")
        seen.add(mid)
        where = f"milestone {i} ('{mid}')"
        if "title" not in item:
            raise bad(f"{where}: missing 'title'")
        if not isinstance(item["title"], str):
            raise bad(f"{where}: 'title' must be a string")
        if "task" in item and not isinstance(item["task"], str):
            raise bad(f"{where}: 'task' must be a string")
        task = item.get("task", "")
        if not task.strip():
            raise bad(f"{where}: 'task' is missing or empty")
        check: str | None = None
        if "check" in item:
            if not isinstance(item["check"], str) or not item["check"].strip():
                raise bad(f"{where}: 'check' must be a non-empty string")
            check = item["check"].strip()
        conditions = (
            parse_conditions(item["conditions"], where, bad) if "conditions" in item else ()
        )
        ungated = item.get("ungated", False)
        if not isinstance(ungated, bool):
            raise bad(f"{where}: 'ungated' must be true or false")
        milestones.append(
            Milestone(mid, item["title"], task.strip(), check, conditions, ungated)
        )
    return ProjectPlan(data["goal"], tuple(milestones))


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


def plan_to_toml(plan: ProjectPlan) -> str:
    lines = [f"goal = {_toml_str(plan.goal)}"]
    for m in plan.milestones:
        lines += [
            "",
            "[[milestones]]",
            f"id = {_toml_str(m.id)}",
            f"title = {_toml_str(m.title)}",
            f"task = {_toml_str(m.task)}",
        ]
        if m.check is not None:
            lines.append(f"check = {_toml_str(m.check)}")
        if m.conditions:
            lines.append("conditions = [")
            for c in m.conditions:
                if c.kind == "command":
                    lines.append(f"  {{ kind = \"command\", cmd = {_toml_str(c.cmd or '')} }},")
                else:
                    lines.append(
                        f"  {{ kind = \"file_exists\", path = {_toml_str(c.path or '')} }},"
                    )
            lines.append("]")
        if m.ungated:
            lines.append("ungated = true")
    return "\n".join(lines) + "\n"


def load_plan(path: Path) -> ProjectPlan:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise PlanError(f"plan file not found: {path}") from None
    except OSError as e:
        raise PlanError(f"cannot read plan file {path}: {e}") from e
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise PlanError(f"invalid plan {path}: bad TOML: {e}") from e
    return parse_plan(data, str(path))


def _valid_gate(g: Any) -> bool:
    if not isinstance(g, dict):
        return False
    attempts = g.get("attempts")
    return (
        isinstance(attempts, int)
        and not isinstance(attempts, bool)
        and attempts >= 0
        and isinstance(g.get("passed"), bool)
        and (g.get("failed_condition") is None or isinstance(g.get("failed_condition"), str))
        and (g.get("feedback") is None or isinstance(g.get("feedback"), str))
    )


@dataclass
class MilestoneRecord:
    status: str = "pending"
    session_id: str | None = None
    cost_usd: float = 0.0
    stop_reason: str | None = None
    answer: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    models: list[str] = field(default_factory=list)
    tools: dict[str, int] = field(default_factory=dict)
    policy: dict | None = None
    gate: dict | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if d["gate"] is None:
            del d["gate"]
        return d

    @classmethod
    def from_dict(cls, d: Any) -> MilestoneRecord:
        if not isinstance(d, dict):
            raise CheckpointError("milestone record must be an object")
        status = d.get("status", "pending")
        if status not in STATUSES:
            raise CheckpointError(f"bad milestone status {status!r}")
        if d.get("gate") is not None and not _valid_gate(d["gate"]):
            raise CheckpointError("bad gate record")
        names = {f.name for f in dataclasses.fields(cls)}
        try:
            return cls(**{k: v for k, v in d.items() if k in names})
        except (TypeError, ValueError) as e:
            raise CheckpointError(str(e)) from e


@dataclass
class Checkpoint:
    run_id: str
    plan: ProjectPlan
    completed: list[str]
    current: str | None
    records: dict[str, MilestoneRecord]
    budget_used: BudgetUsage
    stop_reason: str | None = None
    planning: dict | None = None

    def to_dict(self) -> dict:
        ids = self.plan.ids
        data: dict[str, Any] = {
            "version": CHECKPOINT_VERSION,
            "run_id": self.run_id,
            "plan": self.plan.to_dict(),
            "completed": list(self.completed),
            "current": self.current,
            "session_ids": {
                i: self.records[i].session_id for i in ids if self.records[i].session_id
            },
            "milestones": {i: self.records[i].to_dict() for i in ids},
            "budget_used": dataclasses.asdict(self.budget_used),
            "stop_reason": self.stop_reason,
        }
        if self.planning is not None:
            data["planning"] = self.planning
        return data

    @classmethod
    def from_dict(cls, d: Any) -> Checkpoint:
        if not isinstance(d, dict) or d.get("version") != CHECKPOINT_VERSION:
            raise CheckpointError("unsupported checkpoint format")
        try:
            try:
                plan = parse_plan(d["plan"], "embedded in checkpoint")
            except PlanError as e:
                raise CheckpointError(str(e)) from e
            ids = plan.ids
            completed = d["completed"]
            if not isinstance(completed, list) or any(c not in ids for c in completed):
                raise CheckpointError("'completed' must be a list of plan ids")
            current = d["current"]
            if current is not None and current not in ids:
                raise CheckpointError("'current' must be null or a plan id")
            run_id = d["run_id"]
            if not isinstance(run_id, str):
                raise CheckpointError("'run_id' must be a string")
            raw_records = d.get("milestones", {})
            records = {
                m.id: MilestoneRecord.from_dict(raw_records.get(m.id, {"status": "pending"}))
                for m in plan.milestones
            }
            u = d["budget_used"]
            budget_used = BudgetUsage(
                float(u["cost_usd"]),
                int(u["iterations"]),
                float(u["wall_s"]),
                int(u["tool_calls"]),
            )
            stop_reason = d.get("stop_reason")
            planning = d.get("planning")
            if planning is not None and not isinstance(planning, dict):
                raise CheckpointError("'planning' must be an object or null")
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise CheckpointError(f"missing or invalid field: {e}") from e
        return cls(
            run_id=run_id,
            plan=plan,
            completed=list(completed),
            current=current,
            records=records,
            budget_used=budget_used,
            stop_reason=stop_reason,
            planning=planning,
        )


def new_checkpoint(run_id: str, plan: ProjectPlan) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        plan=plan,
        completed=[],
        current=None,
        records={m.id: MilestoneRecord() for m in plan.milestones},
        budget_used=BudgetUsage(),
    )


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    with contextlib.suppress(OSError):
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def dir_for(self, run_id: str) -> Path:
        if not RUN_ID_RE.fullmatch(run_id):
            raise CheckpointError(f"invalid run id: {run_id!r} (expected YYYYmmdd-HHMMSS-xxxxxx)")
        return self.root / run_id

    def path_for(self, run_id: str) -> Path:
        return self.dir_for(run_id) / CHECKPOINT_FILE

    def new_run_id(self) -> str:
        for _ in range(100):
            run_id = new_session_id()
            if not self.dir_for(run_id).exists():
                return run_id
        raise CoraError("could not allocate a project run id")

    def create(self, plan: ProjectPlan, *, planning: dict | None = None) -> Checkpoint:
        cp = new_checkpoint(self.new_run_id(), plan)
        cp.planning = planning
        self.save(cp)
        return cp

    def save(self, cp: Checkpoint) -> Path:
        path = self.path_for(cp.run_id)
        atomic_write_text(path, json.dumps(cp.to_dict(), ensure_ascii=False, indent=2))
        return path

    def load(self, run_id: str) -> Checkpoint:
        path = self.path_for(run_id)
        if not path.is_file():
            raise CheckpointError(f"project run not found: {run_id}")
        prefix = f"checkpoint for run {run_id} is unreadable"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise CheckpointError(f"{prefix}: {e}") from e
        try:
            cp = Checkpoint.from_dict(data)
        except CheckpointError as e:
            raise CheckpointError(f"{prefix}: {e}") from e
        if cp.run_id != run_id:
            raise CheckpointError(f"{prefix}: run_id mismatch")
        return cp

    def list_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / CHECKPOINT_FILE).is_file())


class ProjectGovernor(BudgetGovernor):
    def __init__(
        self, limits: BudgetLimits, *, base: BudgetUsage | None = None, **kwargs: Any
    ) -> None:
        self.base = base or BudgetUsage()
        super().__init__(limits, **kwargs)

    def begin(self, seed: BudgetUsage | None = None) -> None:
        s = seed or BudgetUsage()
        b = self.base
        warned = list(getattr(self, "_warned", []))
        super().begin(
            BudgetUsage(
                b.cost_usd + s.cost_usd,
                b.iterations + s.iterations,
                b.wall_s + s.wall_s,
                b.tool_calls + s.tool_calls,
            )
        )
        self._warned = warned

    def commit(self) -> BudgetUsage:
        self.base = self.usage()
        return self.base


def merge_policy(items: Sequence[dict | None]) -> dict | None:
    present = [p for p in items if p is not None]
    if not present:
        return None
    last = present[-1]
    out: dict[str, Any] = {"mode": last.get("mode"), "source": last.get("source")}
    for key in ("allow", "ask", "deny", "ask_resolved_deny", "decisions_dropped"):
        out[key] = sum(int(p.get(key, 0)) for p in present)
    out["decisions"] = [d for p in present for d in p.get("decisions", [])]
    return out


def public_status(status: str) -> str:
    return "interrupted" if status == "running" else status


def milestone_list(cp: Checkpoint) -> list[dict]:
    out: list[dict] = []
    for m in cp.plan.milestones:
        rec = cp.records[m.id]
        item: dict[str, Any] = {
            "id": m.id,
            "status": public_status(rec.status),
            "session_id": rec.session_id,
            "cost_usd": rec.cost_usd,
        }
        if m.conditions:
            item["gate"] = (
                None
                if rec.gate is None
                else {
                    "attempts": rec.gate["attempts"],
                    "passed": rec.gate["passed"],
                    "failed_condition": rec.gate["failed_condition"],
                }
            )
        out.append(item)
    return out


def ungated_ids(plan: ProjectPlan) -> list[str]:
    return [m.id for m in plan.milestones if m.ungated]


def project_outcome(
    cp: Checkpoint,
    governor: BudgetGovernor | None,
    *,
    stop_reason: str,
    wall_s: float,
    warnings: Sequence[str] = (),
    errors: Sequence[str] = (),
    signal: int | None = None,
    session_id: str | None = None,
) -> dict:
    recs = [cp.records[m.id] for m in cp.plan.milestones]
    ok = stop_reason == "final_answer"
    final_answer = recs[-1].answer if ok else None
    if session_id is None:
        session_id = next((r.session_id for r in reversed(recs) if r.session_id), None)
    p = cp.planning or {}
    models: list[str] = []
    if "model" in p:
        models.append(p["model"])
    for r in recs:
        for mid in r.models:
            if mid not in models:
                models.append(mid)
    tools: dict[str, int] = {}
    for r in recs:
        for name, n in r.tools.items():
            tools[name] = tools.get(name, 0) + n
    return {
        "ok": ok,
        "stop_reason": stop_reason,
        "final_answer": final_answer,
        "session_id": session_id,
        "iterations": governor.usage().iterations if governor else cp.budget_used.iterations,
        "cost_usd": sum((r.cost_usd for r in recs), 0.0) + float(p.get("cost_usd", 0.0)),
        "tokens": {
            "in": sum(r.tokens_in for r in recs) + int(p.get("tokens_in", 0)),
            "out": sum(r.tokens_out for r in recs) + int(p.get("tokens_out", 0)),
        },
        "wall_s": round(wall_s, 3),
        "models": models,
        "tools": tools,
        "policy": merge_policy([r.policy for r in recs]),
        "budget": governor.to_dict() if governor else None,
        "warnings": list(warnings),
        "errors": list(errors),
        "exit_code": exit_code(stop_reason, signal=signal),
        "run_id": cp.run_id,
        "milestones": milestone_list(cp),
        "ungated_milestones": ungated_ids(cp.plan),
    }


def project_error_outcome(
    message: str,
    code: int = 2,
    *,
    checkpoint: Checkpoint | None = None,
    session_id: str | None = None,
    warnings: Sequence[str] = (),
    wall_s: float = 0.0,
    stop_reason: str = "error",
) -> dict:
    return {
        **{
            k: v
            for k, v in error_outcome(
                message,
                code,
                session_id=session_id,
                warnings=warnings,
                wall_s=wall_s,
                stop_reason=stop_reason,
            ).items()
            if k != "profile"
        },
        "run_id": checkpoint.run_id if checkpoint else None,
        "milestones": milestone_list(checkpoint) if checkpoint else [],
        "ungated_milestones": ungated_ids(checkpoint.plan) if checkpoint else [],
    }


async def run_condition(
    cond: Condition, ctx: ToolContext, *, timeout_s: int, max_chars: int
) -> tuple[bool, str]:
    if cond.kind == "file_exists":
        try:
            p = ctx.workspace.resolve(cond.path or "")
        except WorkspaceViolation as e:
            return False, f"denied: {e}"
        return (True, "") if p.exists() else (False, f"file not found: {cond.path}")
    args = {"command": cond.cmd or ""}
    gate = ctx.gate
    verdict = (
        gate.check("run_shell", args, approval_mode_of(ctx.approval)) if gate is not None else None
    )
    if verdict is not None and verdict.blocked:
        return False, verdict.message[-max_chars:]
    tool = RunShellTool()
    try:
        tool.preflight(args, ctx)
        res = await tool.run(args, dataclasses.replace(ctx, shell_timeout_s=timeout_s))
    except WorkspaceViolation as e:
        return False, f"denied: {e}"
    except ValueError as e:
        return False, f"invalid command: {e}"
    except OSError as e:
        return False, f"error: {e}"
    return res.ok, res.output[-max_chars:]


def gate_task(task: str, feedback: str) -> str:
    return (
        f"{task}\n\n[completion check failed] A previous attempt at this milestone ended "
        "with a final answer, but this completion condition did not pass:\n"
        f"{feedback}\nMake the condition pass, then give your final answer."
    )


class ProjectRunner:
    def __init__(
        self,
        checkpoint: Checkpoint,
        store: CheckpointStore,
        governor: ProjectGovernor,
        agent_factory: Callable[[], Agent],
        *,
        denials: Callable[[], int] = lambda: 0,
        on_event: Callable[[dict], None] | None = None,
        gate_retries: int = 1,
        condition_timeout_s: int = 60,
        condition_output_chars: int = 2000,
    ) -> None:
        self.checkpoint = checkpoint
        self.store = store
        self.governor = governor
        self.agent_factory = agent_factory
        self.denials = denials
        self.log = EventLog(store.dir_for(checkpoint.run_id) / "events.jsonl", on_event)
        self.current_agent: Agent | None = None
        self.stop_requested = False
        self.last_session_id: str | None = None
        self.gate_retries = gate_retries
        self.condition_timeout_s = condition_timeout_s
        self.condition_output_chars = condition_output_chars
        self._gate_agent: Agent | None = None

    def request_stop(self) -> None:
        self.stop_requested = True
        if self.current_agent is not None:
            self.current_agent.request_stop()

    def _save(self) -> None:
        cp = self.checkpoint
        cp.budget_used = self.governor.base
        self.store.save(cp)
        self.log.emit("checkpoint", completed=list(cp.completed), current=cp.current)

    async def execute(self) -> str:
        cp = self.checkpoint
        self.log.emit(
            "project_start",
            run_id=cp.run_id,
            completed=list(cp.completed),
            milestones=cp.plan.ids,
        )
        stop = "final_answer"
        for m in cp.plan.milestones:
            if m.id in cp.completed:
                continue
            prev = cp.records.get(m.id) or MilestoneRecord()
            gate: dict | None = None
            if m.conditions:
                if prev.gate is not None and prev.stop_reason != GATE_FAILED:
                    gate = dict(prev.gate)
                else:
                    gate = {
                        "attempts": 0,
                        "passed": False,
                        "failed_condition": None,
                        "feedback": None,
                    }
            rec = MilestoneRecord(
                status="running",
                cost_usd=prev.cost_usd,
                tokens_in=prev.tokens_in,
                tokens_out=prev.tokens_out,
                models=list(prev.models),
                tools=dict(prev.tools),
                gate=gate,
            )
            cp.records[m.id] = rec
            cp.current = m.id
            if self.stop_requested:
                rec.status = rec.stop_reason = "interrupted"
                stop = "interrupted"
                self._save()
                break
            self._save()
            self.log.emit("milestone_start", id=m.id, title=m.title)
            stop = await (self._run_gated(m, rec) if m.conditions else self._run_one(m, rec))
            self.log.emit(
                "milestone_end",
                id=m.id,
                status=rec.status,
                stop_reason=rec.stop_reason,
                session_id=rec.session_id,
                cost_usd=rec.cost_usd,
            )
            if rec.status != "completed":
                break
        if len(cp.completed) == len(cp.plan.milestones):
            stop = "final_answer"
            cp.current = None
        elif self.stop_requested:
            stop = "interrupted"
        cp.stop_reason = stop
        self._save()
        return stop

    async def _check_conditions(self, m: Milestone) -> tuple[Condition | None, str, str | None]:
        for c in m.conditions:
            cap = self.governor.check_tool_call()
            if cap:
                return None, "", cap
            self.governor.add_tool_calls(1)
            ok, out = await run_condition(
                c,
                self._gate_agent.ctx,
                timeout_s=self.condition_timeout_s,
                max_chars=self.condition_output_chars,
            )
            if not ok:
                return c, out, None
        return None, "", None

    async def _run_gated(self, m: Milestone, rec: MilestoneRecord) -> str:
        cp = self.checkpoint
        gate = rec.gate
        max_attempts = 1 + self.gate_retries
        while True:
            task = gate_task(m.task, gate["feedback"]) if gate["feedback"] else m.task
            stop = await self._run_one(m, rec, task, gated=True)
            if stop != "final_answer":
                return stop
            failed, out, cap = await self._check_conditions(m)
            self.governor.commit()
            if cap is not None:
                rec.status = "failed"
                rec.stop_reason = "budget_exceeded"
                self._save()
                return "budget_exceeded"
            gate["attempts"] += 1
            if failed is None:
                gate.update(passed=True, failed_condition=None, feedback=None)
                rec.status = "completed"
                cp.completed.append(m.id)
                cp.current = None
                self.log.emit(
                    "gate", id=m.id, attempt=gate["attempts"], passed=True, condition=None
                )
                self._save()
                return "final_answer"
            desc = failed.describe()
            gate.update(passed=False, failed_condition=desc, feedback=f"{desc}\n{out}")
            self.log.emit(
                "gate",
                id=m.id,
                attempt=gate["attempts"],
                passed=False,
                condition=desc,
                output_tail=out[-500:],
            )
            if gate["attempts"] >= max_attempts:
                rec.status = "failed"
                rec.stop_reason = GATE_FAILED
                self._save()
                return GATE_FAILED
            if self.stop_requested:
                rec.status = rec.stop_reason = "interrupted"
                self._save()
                return "interrupted"
            self._save()

    async def _run_one(
        self, m: Milestone, rec: MilestoneRecord, task: str | None = None, *, gated: bool = False
    ) -> str:
        cp = self.checkpoint
        agent = self.agent_factory()
        self.current_agent = agent
        self._gate_agent = agent
        if self.stop_requested:
            agent.request_stop()
        before = self.denials()
        r: RunResult | None = None
        try:
            r = await agent.run(
                task if task is not None else m.task,
                check_command=m.check,
                sensor=True,
            )
        finally:
            self.current_agent = None
            self.governor.commit()
            if r is None:
                rec.status = rec.stop_reason = "interrupted"
                if agent.current is not None:
                    rec.session_id = agent.current.id
                    rec.cost_usd += CostMeter.from_list(agent.current.meter).total_cost_usd
                self.last_session_id = rec.session_id
                self._save()
        stop = outcome_stop_reason(
            r, tripped=self.governor.tripped, denials=self.denials() - before
        )
        by_model = r.summary.get("by_model", {})
        rec.session_id = r.session.id
        rec.answer = r.answer
        rec.stop_reason = stop
        rec.cost_usd += float(r.summary.get("total_cost_usd", 0.0))
        rec.tokens_in += sum(int(v.get("input_tokens", 0)) for v in by_model.values())
        rec.tokens_out += sum(int(v.get("output_tokens", 0)) for v in by_model.values())
        for model_id in by_model:
            if model_id not in rec.models:
                rec.models.append(model_id)
        for name, n in self.governor.tool_counts.items():
            rec.tools[name] = rec.tools.get(name, 0) + n
        rec.policy = r.summary.get("policy")
        if stop == "final_answer" and not gated:
            rec.status = "completed"
            cp.completed.append(m.id)
            cp.current = None
        elif stop == "final_answer":
            pass
        elif stop == "interrupted":
            rec.status = "interrupted"
        else:
            rec.status = "failed"
        self.last_session_id = rec.session_id
        self._save()
        return stop
