"""Declarative approval policy: rules, TOML loading, engine, gate and tally."""
from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from cora.core import shellguard
from cora.core.errors import ConfigError
from cora.core.toolgroups import MCP_TOOL_PREFIX, group_of

DECISIONS = ("allow", "ask", "deny")
_SEVERITY = {"allow": 0, "ask": 1, "deny": 2}
POLICY_KEYS = frozenset({"rules", "shell_confinement", "sandbox", "env_passthrough"})
RULE_KEYS = frozenset({"id", "decision", "tool", "group", "command"})
RESERVED_ID_PREFIXES = ("default", "floor:", "confine:", "strict:")
MAX_LISTED_DECISIONS = 200
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FILE_PATH_KEYS = ("path", "paths")
WRITE_TOOLS = frozenset({"edit_file", "write_file", "delete_file"})
POLICY_MODE_NOTICE = (
    "approval: policy - the policy decides every tool call and never prompts; 'ask' rules "
    "count as denials. This is policy-level confinement (argv parsing, path checks, clean "
    "environment), not an OS sandbox."
)
SANDBOX_UNAVAILABLE = (
    "warning: [policy] sandbox = true, but sandbox-exec is not available on this system; "
    "only the policy layer is applied (no OS sandbox)"
)
STRICT_SANDBOX_UNAVAILABLE = (
    "warning: the e2e strict profile could not enable sandbox-exec; only the policy layer "
    "(argv parsing, path checks, clean environment) is applied — not an OS sandbox"
)


def approval_mode_of(approval: Any) -> str:
    return str(getattr(approval, "mode", "ask"))


def _has_glob(p: str) -> bool:
    return any(c in p for c in "*?[")


@dataclass(frozen=True)
class Rule:
    id: str
    decision: str
    tools: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    index: int = 0

    def matches(self, tool: str, group: str | None, segment: str | None) -> bool:
        if self.tools and not any(fnmatchcase(tool, p) for p in self.tools):
            return False
        if self.groups and (
                group is None or not any(fnmatchcase(group, p) for p in self.groups)):
            return False
        if self.commands and (
                segment is None or not any(fnmatchcase(segment, p) for p in self.commands)):
            return False
        return True

    @property
    def specificity(self) -> tuple[int, int, int, int, int]:
        lit = max((len(p) - sum(p.count(c) for c in "*?[]") for p in self.commands), default=0)
        exact = int(bool(self.tools) and not any(_has_glob(p) for p in self.tools))
        return (int(bool(self.commands)), lit, exact, int(bool(self.tools)),
                int(bool(self.groups)))

    def unlocks(self, segment: str) -> bool:
        if self.decision != "allow":
            return False
        return any((first := p.split(" ", 1)[0]) and not _has_glob(first)
                   and fnmatchcase(segment, p) for p in self.commands)


@dataclass(frozen=True)
class PolicySettings:
    rules: tuple[Rule, ...] = ()
    shell_confinement: bool = False
    sandbox: bool = False
    env_passthrough: tuple[str, ...] = ()
    source: str = "builtin"


@dataclass(frozen=True)
class Verdict:
    decision: str
    rule: str
    reason: str = ""
    hard: bool = False


def _resolve(layer, tool, group, segment) -> Verdict | None:
    matches = [r for r in layer if r.matches(tool, group, segment)]
    for d in ("deny", "ask", "allow"):
        cands = [r for r in matches if r.decision == d]
        if cands:
            best = max(cands, key=lambda r: (r.specificity, -r.index))
            return Verdict(d, best.id, f"rule {best.id}")
    return None


class PolicyEngine:
    def __init__(self, settings: PolicySettings, guard: shellguard.PathGuard, *,
                 strict: bool = False) -> None:
        self.settings, self.guard, self.strict = settings, guard, strict
        self.user_rules = () if strict else settings.rules
        self.base_rules = STRICT_RULES if strict else DEFAULT_RULES

    def evaluate(self, tool: str, args: dict[str, Any]) -> Verdict:
        if tool == "run_shell":
            return self._shell(str(args.get("command", "")), full=True)
        if not tool.startswith(MCP_TOOL_PREFIX):
            f = self._tool_paths(tool, args)
            if f is not None:
                return Verdict("deny", f.rule, f.reason, hard=True)
        return self._match(tool, group_of(tool), None)

    def confine(self, command: str) -> Verdict:
        return self._shell(command, full=False)

    def _match(self, tool, group, segment) -> Verdict:
        for layer in (self.user_rules, self.base_rules):
            hit = _resolve(layer, tool, group, segment)
            if hit is not None:
                return hit
        return Verdict("deny", "default", "no policy rule allows this call (default deny)")

    def _shell(self, command: str, *, full: bool) -> Verdict:
        analysis = shellguard.analyze(command, self.guard)
        if analysis.findings:
            f = analysis.findings[0]
            return Verdict("deny", f.rule, f.reason, hard=True)
        worst: Verdict | None = None
        for seg in analysis.segments:
            v = self._segment(seg, full=full)
            if worst is None or (_SEVERITY[v.decision], v.hard) > (
                    _SEVERITY[worst.decision], worst.hard):
                worst = v
        return worst or Verdict("deny", "confine:empty", "empty command", hard=True)

    def _segment(self, seg: shellguard.Segment, *, full: bool) -> Verdict:
        for f in seg.findings:
            if f.severity == shellguard.HARD:
                return Verdict("deny", f.rule, f.reason, hard=True)
        for f in seg.findings:
            if f.severity == shellguard.NETWORK and not full:
                continue
            if self.strict or not self._unlocked(seg.text):
                return Verdict("deny", f.rule, f.reason)
        if not full:
            return Verdict("allow", "confine:ok", "passed shell confinement checks")
        text = f"{seg.text} -" if seg.piped and seg.text in PIPE_SINKS else seg.text
        return self._match("run_shell", "core", text)

    def _unlocked(self, text: str) -> bool:
        return any(r.matches("run_shell", "core", text) and r.unlocks(text)
                   for r in self.user_rules)

    def _tool_paths(self, tool, args) -> shellguard.Finding | None:
        write = tool in WRITE_TOOLS
        values: list[str] = []
        for key in FILE_PATH_KEYS:
            v = args.get(key)
            if isinstance(v, str):
                values.append(v)
            elif isinstance(v, list):
                values.extend(x for x in v if isinstance(x, str))
        for v in values:
            f = self.guard.check_real(self.guard.resolve(os.path.expanduser(v)), write=write)
            if f is not None:
                return f
        return None


@dataclass
class PolicyTally:
    allow: int = 0
    ask: int = 0
    deny: int = 0
    ask_denied: int = 0
    listed: list[dict] = field(default_factory=list)
    dropped: int = 0

    @property
    def total(self) -> int:
        return self.allow + self.ask + self.deny

    def add(self, record: dict) -> None:
        d = record["decision"]
        setattr(self, d, getattr(self, d) + 1)
        if d == "ask" and record["resolved"] == "deny":
            self.ask_denied += 1
        if d != "allow":
            if len(self.listed) < MAX_LISTED_DECISIONS:
                self.listed.append({k: record[k] for k in (
                    "ts", "tool", "args", "decision", "rule", "resolved")})
            else:
                self.dropped += 1

    def to_dict(self, mode: str, source: str) -> dict:
        return {"mode": mode, "source": source, "allow": self.allow, "ask": self.ask,
                "deny": self.deny, "ask_resolved_deny": self.ask_denied,
                "decisions": [dict(x) for x in self.listed], "decisions_dropped": self.dropped}


@dataclass(frozen=True)
class GateVerdict:
    tool: str
    decision: str
    rule: str
    reason: str
    final: bool

    @property
    def blocked(self) -> bool:
        return self.decision == "deny" or (self.decision == "ask" and self.final)

    @property
    def message(self) -> str:
        if self.decision == "ask":
            return (f"denied by policy: '{self.tool}' needs approval under rule {self.rule}, "
                    "and approval mode 'policy' never prompts")
        return f"denied by policy ({self.rule}): {self.reason}"


def _args_summary(tool: str, args: dict[str, Any]) -> str:
    if tool == "run_shell":
        return str(args.get("command", ""))[:200]
    return json.dumps(args, ensure_ascii=False, default=str)[:200]


class PolicyGate:
    def __init__(self, settings: PolicySettings, workspace: Path, *, strict: bool = False,
                 extra_protected: Sequence[Path] = (),
                 hidden_env: Collection[str] = ()) -> None:
        self.settings = settings
        self.strict = strict
        self.guard = shellguard.PathGuard(workspace, shellguard.default_protected(extra_protected))
        self.engine = PolicyEngine(settings, self.guard, strict=strict)
        self.hidden_env = frozenset(hidden_env)
        self.tally = PolicyTally()
        self.sink: Callable[[dict], None] | None = None
        self.warnings: list[str] = []
        self.sandbox = (settings.sandbox or strict) and shellguard.sandbox_available()
        if settings.sandbox and not shellguard.sandbox_available():
            self.warnings.append(SANDBOX_UNAVAILABLE)
        elif strict and sys.platform == "darwin" and not shellguard.sandbox_available():
            self.warnings.append(STRICT_SANDBOX_UNAVAILABLE)

    @property
    def source(self) -> str:
        return "strict" if self.strict else self.settings.source

    def mode_for(self, approval_mode: str, tool: str = "run_shell") -> str | None:
        if self.strict:
            return "strict"
        if approval_mode == "policy":
            return "policy"
        if self.settings.shell_confinement and tool == "run_shell":
            return "confine"
        return None

    def begin_run(self) -> None:
        self.tally = PolicyTally()

    def check(self, tool: str, args: dict[str, Any], approval_mode: str) -> GateVerdict | None:
        mode = self.mode_for(approval_mode, tool)
        if mode is None:
            return None
        final = approval_mode == "policy"
        v = (self.engine.confine(str(args.get("command", ""))) if mode == "confine"
             else self.engine.evaluate(tool, args))
        verdict = GateVerdict(tool, v.decision, v.rule, v.reason, final)
        resolved = "deny" if verdict.blocked else ("allow" if final else "approval")
        record = {"tool": tool, "args": _args_summary(tool, args), "decision": v.decision,
                  "rule": v.rule, "reason": v.reason[:200], "mode": mode, "resolved": resolved}
        self.tally.add({**record, "ts": datetime.now(UTC).isoformat()})
        if self.sink is not None:
            self.sink(record)
        return verdict

    def shell_env(self, approval_mode: str) -> dict[str, str] | None:
        if self.mode_for(approval_mode) is None:
            return None
        home = self.guard.root / ".cora" / "home"
        home.mkdir(parents=True, exist_ok=True)
        return shellguard.clean_env(os.environ, home, self.settings.env_passthrough,
                                    self.hidden_env)

    def sandbox_argv(self, command: str, approval_mode: str) -> list[str] | None:
        if not self.sandbox or self.mode_for(approval_mode) is None:
            return None
        return ["sandbox-exec", "-p", shellguard.sandbox_profile(self.guard),
                "/bin/sh", "-c", command]

    def summary(self, approval_mode: str) -> dict | None:
        mode = self.mode_for(approval_mode)
        if mode is None and self.tally.total == 0:
            return None
        return self.tally.to_dict(mode or "off", self.source)


def _patterns(value: Any, label: str, *, command: bool = False) -> tuple[str, ...]:
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items or not all(
            isinstance(v, str) and v.strip() for v in items):
        raise ConfigError(f"{label}: must be a non-empty string or a non-empty list of "
                          "non-empty strings")
    return tuple(" ".join(v.split()) if command else v.strip() for v in items)


def parse_policy(raw: Any, source: str) -> PolicySettings:
    if raw is None:
        return PolicySettings()
    where = f"invalid policy in {source}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a table")
    unknown = sorted(set(raw) - POLICY_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown keys {unknown}; expected keys from "
                          f"{sorted(POLICY_KEYS)}")
    for key in ("shell_confinement", "sandbox"):
        if key in raw and not isinstance(raw[key], bool):
            raise ConfigError(f"{where}: {key} must be true or false")
    env = raw.get("env_passthrough", [])
    if not isinstance(env, list) or not all(
            isinstance(n, str) and _ENV_NAME.fullmatch(n) for n in env):
        raise ConfigError(f"{where}: env_passthrough must be a list of environment variable names")
    secret = [n for n in env if shellguard.secret_like(n)]
    if secret:
        raise ConfigError(f"{where}: env_passthrough must not pass secret-like variables {secret}")
    rules_raw = raw.get("rules", [])
    if not isinstance(rules_raw, list):
        raise ConfigError(f"{where}: rules must be a list of tables")
    rules: list[Rule] = []
    seen: set[str] = set()
    for n, item in enumerate(rules_raw, 1):
        label = f"invalid policy rule #{n} in {source}"
        if not isinstance(item, dict):
            raise ConfigError(f"{label}: must be a table")
        bad = sorted(set(item) - RULE_KEYS)
        if bad:
            raise ConfigError(f"{label}: unknown keys {bad}; expected keys from "
                              f"{sorted(RULE_KEYS)}")
        decision = item.get("decision")
        if decision not in DECISIONS:
            raise ConfigError(f"{label}: unknown decision {decision!r}; expected one of "
                              f"{list(DECISIONS)}")
        tools = _patterns(item.get("tool"), f"{label}: tool")
        groups = _patterns(item.get("group"), f"{label}: group")
        commands = _patterns(item.get("command"), f"{label}: command", command=True)
        if not (tools or groups or commands):
            raise ConfigError(f"{label}: needs at least one of tool, group, command")
        rid = item.get("id", f"rule#{n}")
        if not isinstance(rid, str) or not rid.strip():
            raise ConfigError(f"{label}: id must be a non-empty string")
        if rid.startswith(RESERVED_ID_PREFIXES):
            raise ConfigError(f"{label}: id {rid!r} uses a reserved prefix "
                              f"{list(RESERVED_ID_PREFIXES)}")
        if rid in seen:
            raise ConfigError(f"{label}: duplicate id {rid!r}")
        seen.add(rid)
        rules.append(Rule(rid, decision, tools, groups, commands, n))
    return PolicySettings(tuple(rules), raw.get("shell_confinement", False),
                          raw.get("sandbox", False), tuple(env), source)


def policy_file(workspace: Path) -> Path:
    return workspace / ".cora" / "policy.toml"


def load_policy(base: PolicySettings, workspace: Path) -> PolicySettings:
    path = policy_file(workspace)
    if not path.is_file():
        return base
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"invalid policy file {path}: {e}") from e
    return parse_policy(data, str(path))


PIPE_SINKS = frozenset({"head", "tail", "wc"})
READ_TOOLS = ("list_files", "read_file", "search", "git_status", "git_diff", "git_log",
              "todo_write", "submit_plan", "delegate")
SHELL_ALLOW = (
    "pytest", "pytest *", "python -m pytest", "python -m pytest *", "python3 -m pytest",
    "python3 -m pytest *", "python -m unittest", "python -m unittest *", "python3 -m unittest",
    "python3 -m unittest *", "uv run pytest", "uv run pytest *", "uv run ruff *", "ruff",
    "ruff *", "python -m ruff *", "python3 -m ruff *", "git status", "git status *",
    "git diff", "git diff *", "git log", "git log *", "git show", "git show *", "git branch",
    "git branch -a", "git branch -v", "git branch -vv", "git branch --list",
    "git branch --list *", "git branch --show-current", "ls", "ls *", "cat *", "grep *",
    "head *", "tail *", "wc *", "pwd", "echo", "echo *", "python *.py", "python *.py *",
    "python3 *.py", "python3 *.py *",
)
DEFAULT_RULES = (
    Rule("default:read-tools", "allow", READ_TOOLS, index=1),
    Rule("default:edit", "allow", ("edit_file", "write_file"), index=2),
    Rule("default:git-write", "ask", ("git_add", "git_commit", "git_branch"), index=3),
    Rule("default:web", "ask", ("web_fetch",), index=4),
    Rule("default:mcp", "ask", ("mcp__*",), index=5),
    Rule("default:shell", "allow", ("run_shell",), commands=SHELL_ALLOW, index=6),
    Rule("default:delete", "ask", ("delete_file",), index=7),
)
STRICT_RULES = (
    Rule("strict:read-tools", "allow", READ_TOOLS, index=1),
    Rule("strict:edit", "allow", ("edit_file", "write_file", "delete_file"), index=2),
    Rule("strict:shell", "allow", ("run_shell",), commands=SHELL_ALLOW, index=3),
)
