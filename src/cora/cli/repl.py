from __future__ import annotations

import dataclasses
import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from cora import __version__
from cora.cli.common import (
    MCP_NONE,
    apply_agent_overrides,
    fmt_price,
    load_resolved,
    mcp_tool_list,
    normalize_answer,
    parse_price,
    run_interruptible,
    tool_line,
    unpriced_warnings,
)
from cora.cli.io import ReplIO
from cora.cli.ui.banner import Banner, BannerInfo
from cora.cli.ui.state import UiState, next_approval
from cora.cli.ui.statusline import context_percent
from cora.cli.ui.theme import THEMES
from cora.cli.ui.todoview import todo_text
from cora.cli.ui.toolview import ToolCallView, args_summary, collapse
from cora.core.agent import Agent
from cora.core.config import (
    APPROVAL_MODES,
    DECIDER_USES,
    GRADES,
    TIERS,
    CoraConfig,
    ModelOverride,
    ModelSpec,
    apply_model_override,
    apply_pin,
    load_user_overrides,
    save_user_overrides,
    user_models_path,
)
from cora.core.errors import ConfigError, CoraError, describe_provider_error
from cora.core.mentions import expand_mentions
from cora.core.metering import CostMeter, format_summary
from cora.core.policy import POLICY_MODE_NOTICE
from cora.core.project import (
    draft_guide,
    git_output,
    is_git_repo,
    load_project_context,
)
from cora.core.state import Session, StopReason
from cora.core.toolgroups import (
    GROUPS,
    OPTIONAL_GROUPS,
    excluded_tools,
    is_mcp_group,
    mcp_group,
)
from cora.core.tools import ApprovalPolicy, ApprovalRequest, TodoList, unified_diff
from cora.core.tools.mcp import McpManager
from cora.core.tools.sizes import format_size_report, group_sizes, measure, size_report

COMMANDS: dict[str, str] = {
    "/help": "Show this help",
    "/model": (
        "Show or change tier models: /model [<tier> <model-id> [IN,OUT]] | /model reset [tier] "
        "| /model pin <model-id> [IN,OUT] | /model unpin"
    ),
    "/route": "Show the last routing decision (grade, model, reason)",
    "/cost": "Show the cost of the current session",
    "/clear": "Clear conversation context (next request starts a new session)",
    "/reset": (
        "Reset this REPL to its start state (model pin, approval, tool groups, check, plan, "
        "delegation, TODOs, context; saved sessions and cost are kept): /reset [--all] "
        "(--all also deletes saved model overrides after confirmation)"
    ),
    "/compact": "Move older context into the memory summary now",
    "/resume": "Resume a saved session: /resume [id]",
    "/sessions": "List saved sessions",
    "/approval": "Show or set approval mode: /approval [ask|auto|deny|policy]",
    "/diff": "Show changes (git diff in git repos, else files edited this session)",
    "/plan": "Plan mode: read-only tools; the model submits a plan for approval: /plan [off]",
    "/todo": "Show the TODO list of this session",
    "/tools": (
        "Show tool groups and prompt sizes; toggle for this session: "
        "/tools [report | <group> on|off]"
    ),
    "/mcp": "Show MCP servers: state, tool count and names, last error (never starts a server)",
    "/check": "Sensor gate: run a check before accepting a final answer: /check [<command>|off]",
    "/delegate": (
        "Show or set sub-agent delegation (incl. parallel explore) for this session: "
        "/delegate [on|off]"
    ),
    "/decider": (
        "Show the active decider (kind, model, uses) and recent decisions; "
        "input text is never shown"
    ),
    "/init": "Create a CORA.md project guide draft (never overwrites)",
    "/status": "Show models, approval mode, session, cost and workdir",
    "/theme": (
        "Show themes or switch the terminal UI theme for this session: "
        "/theme [default|dark|light|mono]"
    ),
    "/expand": (
        "Show the full text of the last collapsed tool result (terminal UI collapses results "
        "over 10 lines)"
    ),
    "/mouse": (
        "TUI only: mouse capture on/off (wheel scrolls; off keeps terminal text selection): "
        "/mouse [on|off]"
    ),
    "/copy": "TUI only: copy the last answer to the clipboard (OSC 52)",
    "/exit": "Exit (also Ctrl-D)",
    "/quit": "Exit",
}
PROMPT = "> "
PLAN_PROMPT = "[plan] > "
CONTINUATION = "... "
EXECUTE_PLAN_TASK = "Execute the approved plan."
RESET_USAGE = "usage: /reset [--all]"
DELEGATE_USAGE = "usage: /delegate [on|off]"
DECIDER_RECENT = 10
DECIDER_USAGE = "usage: /decider"
THEME_USAGE = "usage: /theme [default|dark|light|mono]"
EXPAND_USAGE = "usage: /expand"
MOUSE_USAGE = "usage: /mouse [on|off]"
COPY_USAGE = "usage: /copy"


@dataclass
class ReplOptions:
    workdir: Path
    config_path: Path
    approval: str | None = None
    max_iterations: int | None = None
    max_cost: float | None = None
    verbose: bool = False
    delegate: bool = False
    resume_id: str | None = None


@dataclass(frozen=True)
class ReplSnapshot:
    models: str
    pin: str
    approval: str
    always_allowed: str
    tool_groups: str
    check: str
    plan_mode: str
    delegation: str
    todos: str
    session: str
    edited_files: str


RESET_FIELDS: tuple[tuple[str, str], ...] = (
    ("models", "models"),
    ("pin", "model pin"),
    ("approval", "approval"),
    ("always_allowed", "always-allowed approvals"),
    ("tool_groups", "tool group overrides"),
    ("check", "check"),
    ("plan_mode", "plan mode"),
    ("delegation", "delegation"),
    ("todos", "TODO items"),
    ("session", "session"),
    ("edited_files", "files tracked for /diff"),
)


def reset_changes(before: ReplSnapshot, after: ReplSnapshot) -> list[str]:
    lines: list[str] = []
    for field, label in RESET_FIELDS:
        old, new = getattr(before, field), getattr(after, field)
        if old == new:
            continue
        line = f"{label}: {old} -> {new}"
        if field == "session" and old != "new":
            line += f" (saved; /resume {old} reopens it)"
        lines.append(line)
    return lines


class Repl:
    def __init__(self, io: ReplIO, opts: ReplOptions) -> None:
        self.io = io
        self.opts = opts
        self._start_opts = dataclasses.replace(opts)
        self.workdir = opts.workdir.resolve()
        self.policy = ApprovalPolicy("ask", review=self._review)
        self._streamed = False
        self._rest = ""
        self._tool_output: str | None = None
        self.mcp: McpManager | None = None
        self.turns = 0
        self.last_answer: str | None = None
        self._init_session_state()
        self.policy.mode = self.cfg.agent.approval
        self._start_approval = self.policy.mode
        self.ui = UiState.from_settings(self.cfg.ui)
        self.ui.on_cycle_approval = self.cycle_approval
        self.ui.on_toggle_todos = self.toggle_todos
        self.ui.get_todos = lambda: self.todos.items
        self.fancy = self.io.attach(self.ui)
        self._sync_ui()
        if opts.resume_id is not None:
            try:
                self.agent.sessions.load(opts.resume_id)
            except CoraError:
                self.close()
                raise

    def _sync_ui(self) -> None:
        ui = self.ui
        tier, model = self._route
        ui.model = f"{tier}:{model}" if model else (f"pin:{self.pin[0]}" if self.pin else None)
        ui.approval = self.policy.mode
        ui.groups = tuple(g for g in OPTIONAL_GROUPS if g not in self.agent.ctx.disabled_groups)
        ui.plan, ui.check = self.plan_mode, self.check_command is not None
        ui.delegate = self.cfg.delegation.enabled
        meter = self.session.meter if self.session else []
        ui.cost_usd = CostMeter.from_list(meter).total_cost_usd if meter else None
        cheap = next((m for m in self._sorted_models() if m.tier == "cheap"), None)
        ui.context_pct = context_percent(
            meter[-1].get("input_tokens") if meter else None,
            cheap.context_tokens if cheap else None,
        )

    def _init_session_state(self) -> None:
        self.session: Session | None = None
        self.originals: dict[str, str | None] = {}
        self.policy.always_allowed.clear()
        self.project = load_project_context(self.workdir)
        self._route: tuple[str | None, str | None] = (None, None)
        self._last_route: dict | None = None
        self.pin: tuple[str, tuple[float, float] | None] | None = None
        self.todos = TodoList()
        self.plan_mode = False
        self.group_overrides: dict[str, bool] = {}
        self.check_command: str | None = None
        self.delegate_override: bool | None = None
        self._decisions: deque[dict] = deque(maxlen=DECIDER_RECENT)
        self._reload()

    def _reload(self) -> None:
        self.base_cfg, cfg = load_resolved(self.opts.config_path, self.workdir)
        cfg = apply_agent_overrides(
            cfg,
            self.opts.approval,
            self.opts.max_iterations,
            self.opts.max_cost,
            delegate=self.opts.delegate,
        )
        if self.delegate_override is not None:
            cfg = dataclasses.replace(
                cfg,
                delegation=dataclasses.replace(cfg.delegation, enabled=self.delegate_override),
            )
        if self.pin is not None:
            cfg = apply_pin(cfg, self.pin[0], self.pin[1])
        self.cfg: CoraConfig = cfg
        if self.mcp is None:
            self.mcp = McpManager(cfg.mcp, self.workdir)
        self.agent = Agent(
            self.cfg,
            self.workdir,
            self.policy,
            on_event=self._on_event,
            on_answer_delta=self._on_delta,
            on_tool_output=self._on_tool_output,
            project_context=self.project.render(),
            mcp=self.mcp,
        )
        self.agent.ctx.originals = self.originals
        self.agent.ctx.todos = self.todos
        self.agent.ctx.plan_mode = self.plan_mode
        self._apply_groups()

    def _apply_groups(self) -> None:
        disabled = set(self.cfg.tool_groups.disabled)
        for g, on in self.group_overrides.items():
            if on:
                disabled.discard(g)
            else:
                disabled.add(g)
        self.agent.ctx.disabled_groups = frozenset(disabled)
        forced = {g for g, on in self.group_overrides.items() if on}
        if self.delegate_override and self.group_overrides.get("delegate", True):
            forced.add("delegate")
        self.agent.ctx.forced_groups = frozenset(forced)

    def _sorted_models(self) -> list[ModelSpec]:
        return sorted(
            (m for m in self.cfg.models if m.source != "pin"),
            key=lambda m: TIERS.index(m.tier),
        )

    def snapshot(self) -> ReplSnapshot:
        always = sorted(self.policy.always_allowed)
        groups = [f"{g}={'on' if on else 'off'}" for g, on in sorted(self.group_overrides.items())]
        return ReplSnapshot(
            models=" ".join(f"{m.tier}={m.id}" for m in self._sorted_models()),
            pin=self.pin[0] if self.pin else "off",
            approval=self.policy.mode,
            always_allowed=", ".join(always) if always else "none",
            tool_groups=", ".join(groups) if groups else "none",
            check=self.check_command or "off",
            plan_mode="on" if self.plan_mode else "off",
            delegation="on" if self.cfg.delegation.enabled else "off",
            todos=str(len(self.todos.items)),
            session=self.session.id if self.session else "new",
            edited_files=str(len(self.originals)),
        )

    def run(self) -> int:
        try:
            self._banner()
            for w in self.agent.policy_warnings:
                self.io.print(w)
            if self.policy.mode == "policy":
                self.io.print(POLICY_MODE_NOTICE)
            if self.opts.resume_id is not None:
                try:
                    self.cmd_resume([self.opts.resume_id])
                except CoraError as e:
                    self.io.error(f"error: {e}")
            while True:
                try:
                    line = self._read()
                except KeyboardInterrupt:
                    self.io.print("(Ctrl-D or /exit to quit)")
                    continue
                except EOFError:
                    break
                text = line.strip()
                if not text:
                    continue
                if text.startswith("/"):
                    if self.dispatch(text):
                        break
                    continue
                self.submit(text)
            self._farewell()
            return 0
        finally:
            self.close()

    def close(self) -> None:
        if self.mcp is not None:
            self.mcp.close()

    def _read(self) -> str:
        self._sync_ui()
        line = self.io.read(PLAN_PROMPT if self.plan_mode else PROMPT)
        while line.endswith("\\"):
            line = line[:-1] + "\n" + self.io.read(CONTINUATION)
        return line

    def dispatch(self, text: str) -> bool:
        name, _, rest = text.partition(" ")
        args = rest.split()
        if name in ("/exit", "/quit"):
            return True
        handlers = {
            "/help": self.cmd_help,
            "/model": self.cmd_model,
            "/route": self.cmd_route,
            "/cost": self.cmd_cost,
            "/clear": self.cmd_clear,
            "/reset": self.cmd_reset,
            "/compact": self.cmd_compact,
            "/resume": self.cmd_resume,
            "/sessions": self.cmd_sessions,
            "/approval": self.cmd_approval,
            "/diff": self.cmd_diff,
            "/plan": self.cmd_plan,
            "/todo": self.cmd_todo,
            "/tools": self.cmd_tools,
            "/mcp": self.cmd_mcp,
            "/check": self.cmd_check,
            "/delegate": self.cmd_delegate,
            "/decider": self.cmd_decider,
            "/init": self.cmd_init,
            "/status": self.cmd_status,
            "/theme": self.cmd_theme,
            "/expand": self.cmd_expand,
            "/mouse": self.cmd_mouse,
            "/copy": self.cmd_copy,
        }
        handler = handlers.get(name)
        if handler is None:
            self.io.print(f"Unknown command: {name}. Type /help to see available commands.")
            return False
        self._rest = rest.strip()
        try:
            handler(args)
        except CoraError as e:
            self.io.error(f"error: {e}")
        return False

    def _banner(self) -> None:
        if self.fancy:
            git = None
            if self.project.git_status:
                lines = self.project.git_status.splitlines()
                git = f"{lines[0].removeprefix('## ')} ({len(lines) - 1} changed)"
            info = BannerInfo(
                __version__,
                str(self.workdir),
                tuple(f"{m.tier}={m.id}" for m in self._sorted_models()),
                self.policy.mode,
                self.project.guide_path.name if self.project.guide_path else None,
                git,
            )
            self.io.render(Banner(info, self.ui.theme, self.ui.glyphs))
            for w in unpriced_warnings(self.cfg):
                self.io.error(w)
            for w in self.cfg.mcp.warnings:
                self.io.error(w)
            return
        self.io.print("CORA - Cost-Oriented Routing Agent")
        self.io.print(f"workdir: {self.workdir}")
        self.io.print(
            "models: " + "  ".join(f"{m.tier}={m.id}" for m in self._sorted_models())
        )
        self.io.print(f"approval: {self.policy.mode}")
        if self.project.guide_path is not None:
            self.io.print(
                f"guide: {self.project.guide_path.name} (loaded into the system prompt)"
            )
        else:
            self.io.print("guide: none (run /init to create CORA.md)")
        if self.project.git_status:
            lines = self.project.git_status.splitlines()
            self.io.print(
                f"git: {lines[0].removeprefix('## ')} ({len(lines) - 1} changed)"
            )
        for w in unpriced_warnings(self.cfg):
            self.io.error(w)
        for w in self.cfg.mcp.warnings:
            self.io.error(w)
        self.io.print(
            "Type a request, or /help for commands. "
            "Ctrl-C interrupts a turn; Ctrl-D or /exit quits."
        )

    def submit(self, text: str) -> None:
        lim = self.cfg.tools
        exp = expand_mentions(
            text,
            self.workdir,
            max_file_chars=lim.mention_max_file_chars,
            max_total_chars=lim.mention_max_total_chars,
            max_dir_entries=lim.mention_max_dir_entries,
        )
        for note in exp.notes:
            self.io.error(note)
        if exp.attached:
            self.io.print("attached: " + ", ".join(f"@{a}" for a in exp.attached))
        self.run_turn(text, attachments=exp.text)
        self._after_turn()

    def _set_plan_mode(self, on: bool) -> None:
        self.plan_mode = on
        self.agent.ctx.plan_mode = on
        self.agent.ctx.submitted_plan = None

    def cmd_plan(self, args: list[str]) -> None:
        if args == ["off"]:
            self._set_plan_mode(False)
            self.io.print("plan mode: off")
            return
        if args:
            raise ConfigError("usage: /plan [off]")
        if self.plan_mode:
            self.io.print("plan mode: on (/plan off to leave)")
            return
        self._set_plan_mode(True)
        self.io.print(
            "plan mode: on. Only read-only tools run; ask for a plan and approve it. "
            "/plan off leaves."
        )
        if "plan-todo" in self.agent.ctx.disabled_groups:
            self.group_overrides["plan-todo"] = True
            self._apply_groups()
            self.io.print("tool group plan-todo: on (needed for submit_plan in plan mode)")

    def _after_turn(self) -> None:
        plan = self.agent.ctx.submitted_plan
        if plan is None or not self.plan_mode:
            return
        self.agent.ctx.submitted_plan = None
        self._review_plan(plan)

    def _review_plan(self, plan: str) -> None:
        self.io.print("● Proposed plan:")
        self.io.markdown(plan)
        ans = (self._ask("Plan: [a]pprove / [r]eject with changes / [c]ancel: ") or "").lower()
        if ans in ("a", "approve", "y", "yes"):
            self._set_plan_mode(False)
            self.io.print(
                f"Plan approved. plan mode: off (approval: {self.policy.mode}). Executing the plan."
            )
            self.run_turn(EXECUTE_PLAN_TASK, attachments=f"\n\nApproved plan (follow it):\n{plan}")
            return
        if ans in ("c", "cancel"):
            self._set_plan_mode(False)
            self.io.print("Plan cancelled. plan mode: off.")
            return
        feedback = self._ask("What should change? (empty = keep planning later): ")
        self.io.print("Plan rejected. plan mode: on.")
        if feedback:
            self.run_turn(f"The user rejected the plan. Requested changes: {feedback}")
            self._after_turn()

    def run_turn(self, text: str, attachments: str = "") -> None:
        self.turns += 1
        before = len(self.session.meter) if self.session else 0
        self._streamed = False
        started = time.monotonic()
        self.agent.ctx.submitted_plan = None
        self.io.status_start("Thinking")
        try:
            r = run_interruptible(
                self.agent.run(
                    text,
                    session=self.session,
                    attachments=attachments,
                    check_command=self.check_command,
                    sensor=True,
                ),
                getattr(self.io, "cancel_scope", None),
            )
        except KeyboardInterrupt:
            self._end_output()
            self.session = self.agent.current or self.session
            self._sync_ui()
            self.io.print("Interrupted. Session state was saved; type a new request to continue.")
            return
        except Exception as e:
            self._end_output()
            self.session = self.agent.current or self.session
            self._sync_ui()
            self.io.error(f"error: {describe_provider_error(e)}")
            return
        self._end_output()
        self.session = r.session
        if r.answer is not None:
            self.last_answer = r.answer
        self._sync_ui()
        if not self._streamed and r.answer is not None:
            self.io.markdown(r.answer)
        if r.stop_reason != StopReason.FINAL_ANSWER:
            self.io.print(f"stopped: {r.stop_reason.value}")
        if r.stop_reason == StopReason.CHECK_FAILED and r.session.last_failure:
            self.io.print("last check failure:\n" + r.session.last_failure[-1500:])
        if r.stop_reason == StopReason.TRIPWIRE:
            self.io.print(r.session.last_failure)
        self.io.print(
            self._turn_summary(r.session.meter[before:], time.monotonic() - started)
        )
        if "sensor" in r.summary:
            sg = r.summary["sensor"]
            line = (
                f"⎿ sensor: {sg['checks']} checks, {sg['retries']} retries, "
                f"+{sg['extra_calls']} LLM calls, +${sg['extra_cost_usd']:.4f}"
            )
            if sg["escalated"]:
                line += ", escalated to strong"
            self.io.print(line)

    def _end_output(self) -> None:
        self.io.status_stop()
        if self._streamed:
            self.io.stream_end()

    def _turn_summary(self, records: list[dict], elapsed: float) -> str:
        calls = len(records)
        inp = sum(r["input_tokens"] for r in records)
        out = sum(r["output_tokens"] for r in records)
        cost = sum(r["cost_usd"] for r in records)
        unknown = any(not r.get("price_known", True) for r in records)
        total = CostMeter.from_list(self.session.meter).total_cost_usd
        tier, model = self._route
        suffix = " +unknown" if unknown else ""
        return (
            f"⎿ {tier}:{model} · {elapsed:.1f}s · {calls} calls · "
            f"{inp} in / {out} out tokens · ${cost:.4f}{suffix} (session ${total:.4f})"
        )

    def _on_event(self, event: dict) -> None:
        if event["type"] == "decision":
            self._decisions.append(event)
        if event["type"] == "route":
            self._route = (event["tier"], event["model"])
            self._last_route = event
            self.io.status_start(f"Thinking ({event['tier']}: {event['model']})")
        if event["type"] == "tool_call":
            output = self._tool_output
            if output is None:
                output = event.get("output_head") or ""
            self._tool_output = None
            self.io.status_stop()
            if self.fancy:
                self._render_tool(event, output)
            else:
                self.io.print(tool_line(event))
            self.io.status_start("Thinking")
        if self.opts.verbose:
            self.io.print(json.dumps(event, ensure_ascii=False))

    def _on_tool_output(self, output: str) -> None:
        self._tool_output = output

    def _render_tool(self, event: dict, output: str) -> None:
        ui = self.ui
        name = event["tool"]
        args = args_summary(event.get("target") or "", event.get("args") or "")
        if name == "todo_write" and event["ok"] and ui.show_todos:
            self.io.render(ToolCallView(name, args, True, "", ui.theme, ui.glyphs, head_only=True))
            self.io.render(todo_text(self.todos.items, ui.theme, ui.glyphs))
            return
        if event["ok"] and collapse(output)[1] > 0:
            ui.last_collapsed = output
        self.io.render(ToolCallView(name, args, event["ok"], output, ui.theme, ui.glyphs))

    def _on_delta(self, text: str) -> None:
        if not self._streamed:
            self.io.status_stop()
            self.io.stream_start()
            self._streamed = True
        self.io.stream_delta(text)

    def _review(self, req: ApprovalRequest) -> str:
        self.io.status_stop()
        approve = getattr(self.io, "approve", None)
        if approve is not None:
            ans = approve(req.tool, req.summary, req.detail,
                          req.tool in ("edit_file", "write_file", "delete_file"))
            self.io.status_start("Working")
            return normalize_answer(ans)
        self.io.print(f"● {req.tool} needs approval")
        if req.detail:
            if req.tool in ("edit_file", "write_file", "delete_file"):
                self.io.show_diff(req.detail)
            else:
                self.io.print(req.detail)
        try:
            ans = self.io.ask("Allow? [y]es / [n]o / [a]lways this session: ")
        except EOFError:
            ans = "n"
        self.io.status_start("Working")
        return normalize_answer(ans)

    def _ask(self, prompt: str) -> str | None:
        try:
            return self.io.ask(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None

    def _print_models(self) -> None:
        for i, m in enumerate(self._sorted_models(), 1):
            self.io.print(
                f"  {i}) {m.tier:<6} {m.id}  "
                f"in={fmt_price(m.input_usd_per_mtok)} out={fmt_price(m.output_usd_per_mtok)}  "
                f"({m.source})"
            )

    def cmd_help(self, args: list[str]) -> None:
        self.io.print("Commands:")
        for name, desc in COMMANDS.items():
            self.io.print(f"  {name:<10} {desc}")
        self.io.print(
            "Input: end a line with \\ to continue on the next line "
            "(Esc+Enter inserts a newline; paste works). Tab completes commands. "
            "Ctrl-C interrupts a running turn. "
            "@path attaches a file or a directory listing (Tab completes paths after @)."
        )

    def cmd_model(self, args: list[str]) -> None:
        if not args:
            self._model_interactive()
            return
        if args[0] == "pin":
            if len(args) == 1:
                self.io.print(
                    f"pinned: {self.pin[0]}"
                    if self.pin
                    else "No model pinned; routing picks the model per request."
                )
                return
            if len(args) > 3:
                raise ConfigError("usage: /model pin <model-id> [IN,OUT]")
            price = parse_price(args[2]) if len(args) == 3 else None
            apply_pin(self.cfg, args[1], price)
            self.pin = (args[1], price)
            self._reload()
            self.io.print(
                f"pinned {args[1]} for this session "
                "(every request uses it; /model unpin restores routing)"
            )
            for w in unpriced_warnings(self.cfg):
                if f"'{args[1]}'" in w:
                    self.io.error(w)
            return
        if args[0] == "unpin":
            if len(args) != 1:
                raise ConfigError("usage: /model unpin")
            self.pin = None
            self._reload()
            self.io.print("unpinned; routing picks the model per request")
            return
        if args[0] == "reset":
            if len(args) > 2:
                raise ConfigError("usage: /model reset [cheap|strong]")
            tier = args[1] if len(args) == 2 else None
            if tier is not None and tier not in TIERS:
                raise ConfigError(f"invalid tier '{tier}'; expected one of {list(TIERS)}")
            path = user_models_path(self.workdir)
            ov = load_user_overrides(path)
            if tier is None:
                ov = {}
            else:
                ov.pop(tier, None)
            save_user_overrides(path, ov)
            self._reload()
            self.io.print(f"reset {tier or 'all tiers'} to config defaults")
            self._print_models()
            return
        if len(args) not in (2, 3):
            raise ConfigError(
                "usage: /model <cheap|strong> <model-id> [IN,OUT] | /model reset [tier]"
            )
        self._set_model(args[0], args[1], parse_price(args[2]) if len(args) == 3 else None)

    def _set_model(self, tier: str, model_id: str, price: tuple[float, float] | None) -> None:
        inp, out = price or (None, None)
        ov = ModelOverride(tier, model_id, None, inp, out)
        apply_model_override(self.base_cfg, ov, "user")
        path = user_models_path(self.workdir)
        overrides = load_user_overrides(path)
        overrides[tier] = ov
        save_user_overrides(path, overrides)
        self._reload()
        self.io.print(f"{tier} -> {model_id} (saved to {path})")
        for w in unpriced_warnings(self.cfg):
            if f"'{model_id}'" in w:
                self.io.error(w)

    def _model_interactive(self) -> None:
        self.io.print("Current models:")
        self._print_models()
        t = self._ask("Tier to change [number or cheap/strong, empty = cancel]: ")
        if not t:
            self.io.print("cancelled")
            return
        tiers = [m.tier for m in self._sorted_models()]
        tier = tiers[int(t) - 1] if t.isdigit() and 1 <= int(t) <= len(tiers) else t
        if tier not in TIERS:
            raise ConfigError(f"invalid tier '{tier}'; expected one of {list(TIERS)}")
        candidates = list(
            dict.fromkeys([m.id for m in self.base_cfg.models] + [m.id for m in self.cfg.models])
        )
        self.io.print("Known models:")
        for i, mid in enumerate(candidates, 1):
            self.io.print(f"  {i}) {mid}")
        mi = self._ask("Model id (number from the list or any model id, empty = cancel): ")
        if not mi:
            self.io.print("cancelled")
            return
        model_id = (
            candidates[int(mi) - 1] if mi.isdigit() and 1 <= int(mi) <= len(candidates) else mi
        )
        p = self._ask("Price IN,OUT in USD per 1M tokens (empty = catalog price or unknown): ")
        if p is None:
            self.io.print("cancelled")
            return
        self._set_model(tier, model_id, parse_price(p) if p else None)

    def cmd_cost(self, args: list[str]) -> None:
        if self.session is None or not self.session.meter:
            self.io.print("No model calls yet in this session ($0.00).")
            return
        self.io.print(
            format_summary(
                CostMeter.from_list(self.session.meter).summary(self.session.delegation_stats)
            )
        )

    def cmd_decider(self, args: list[str]) -> None:
        if args:
            raise ConfigError(DECIDER_USAGE)
        ds = self.cfg.decider
        d = self.agent.decider
        uses = " ".join(f"{u}={'on' if getattr(ds, u) else 'off'}" for u in DECIDER_USES)
        self.io.print(
            f"decider: {d.kind} (model: {d.model or '-'}); uses: {uses}; "
            f"min_confidence {ds.min_confidence:g}"
        )
        if not self._decisions:
            hint = ""
            if not any(getattr(ds, u) for u in DECIDER_USES):
                hint = " (all uses are off; turn them on in [decider] in cora.toml)"
            self.io.print(f"No decisions yet in this REPL.{hint}")
            return
        self.io.print(
            f"recent decisions (last {len(self._decisions)}; input text is never shown):"
        )
        for e in self._decisions:
            fallback = f" fallback={e['reason'] or 'yes'}" if e["fallback_used"] else ""
            self.io.print(
                f"  {e['kind']} {e['question']} -> {e['output']} conf={e['confidence']:.2f} "
                f"cost=${e['cost_usd']:.6f} {e['latency_ms']:.0f}ms {e['decider']}"
                f"{fallback} #{e['input_hash'][:8]}"
            )

    def cmd_clear(self, args: list[str]) -> None:
        self.session = None
        self.todos.clear()
        self.io.print("Context cleared. The next request starts a new session.")

    def cmd_reset(self, args: list[str]) -> None:
        if args not in ([], ["--all"]):
            raise ConfigError(RESET_USAGE)
        wipe = args == ["--all"]
        path = user_models_path(self.workdir)
        if wipe:
            ans = self._ask(
                f"/reset --all also deletes the saved model overrides ({path}). Continue? [y/N]: "
            )
            if (ans or "").lower() not in ("y", "yes"):
                self.io.print("reset cancelled; nothing changed")
                return
        load_resolved(self._start_opts.config_path, self.workdir)
        before = self.snapshot()
        removed = wipe and path.exists()
        if removed:
            save_user_overrides(path, {})
        self.opts = dataclasses.replace(self._start_opts)
        self._init_session_state()
        self.policy.mode = self._start_approval
        changes = reset_changes(before, self.snapshot())
        if removed:
            changes.append(f"saved model overrides: deleted {path}")
        if not changes:
            self.io.print("reset: nothing changed (already at the REPL start state)")
            return
        self.io.print("reset to the REPL start state:")
        for line in changes:
            self.io.print(f"  {line}")

    def cmd_todo(self, args: list[str]) -> None:
        self.io.print(self.todos.render())

    def cmd_tools(self, args: list[str]) -> None:
        if not args:
            self._print_tools()
            return
        if args == ["report"]:
            self.io.print(format_size_report(size_report()))
            return
        if len(args) != 2 or args[1] not in ("on", "off"):
            raise ConfigError("usage: /tools [report | <group> on|off]")
        g = args[0]
        if is_mcp_group(g) and g in self._mcp_groups():
            self.group_overrides[g] = args[1] == "on"
            self._apply_groups()
            self.io.print(f"tool group {g}: {args[1]} (this session only; config file unchanged)")
            return
        if g not in GROUPS:
            raise ConfigError(
                f"unknown tool group '{g}'; expected one of {list(GROUPS) + self._mcp_groups()}"
            )
        if g == "core":
            if args[1] == "off":
                raise ConfigError("the core group is always on and cannot be disabled")
            self.io.print("tool group core: on (always)")
            return
        self.group_overrides[g] = args[1] == "on"
        self._apply_groups()
        self.io.print(f"tool group {g}: {args[1]} (this session only; config file unchanged)")

    def _mcp_groups(self) -> list[str]:
        return [mcp_group(n) for n in self.mcp.usable_servers()] if self.mcp else []

    def cmd_mcp(self, args: list[str]) -> None:
        if args:
            raise ConfigError("usage: /mcp")
        if self.mcp is None or not self.mcp.has_servers():
            self.io.print(MCP_NONE)
            return
        self.io.print(
            "MCP servers (state only; /mcp never starts a server, tools load on first use):"
        )
        off = self.agent.ctx.disabled_groups
        for st in self.mcp.statuses():
            if st.tools:
                tools = f"{len(st.tools)} tools: {mcp_tool_list([t.tool for t in st.tools])}"
            elif st.state == "not started":
                tools = "tools unknown until first use"
            else:
                tools = "0 tools"
            line = f"  {st.name:<12} {st.state:<12} {tools}"
            if st.state != "disabled" and mcp_group(st.name) in off:
                line += f"  [group off: /tools {mcp_group(st.name)} on]"
            if st.restarts:
                line += f"  (restarts: {st.restarts})"
            self.io.print(line)
            for note in st.notes:
                self.io.print(f"    note: {note}")
            if st.last_error:
                self.io.print(f"    last error: {st.last_error}")

    def _print_tools(self) -> None:
        reg = self.agent.registry_for()
        if self.mcp is not None:
            reg = reg.extended(
                [t for t in self.mcp.cached_tools() if t.name not in set(reg.names())]
            )
        mcp_groups = self._mcp_groups()
        groups = [*GROUPS, *mcp_groups]
        sizes = group_sizes(reg, groups)
        self.io.print("Tool groups (this session; /tools <group> on|off, /tools report):")
        for g in groups:
            members, s = sizes[g]
            if g == "core":
                state = "on (always)"
            elif g in self.agent.ctx.disabled_groups:
                state = "off"
            else:
                state = "on"
            if members:
                names = ", ".join(members)
            elif g == "delegate":
                names = "(no tools: delegation is off)"
            elif g in mcp_groups:
                names = "(no tools loaded yet: they load on first use; see /mcp)"
            else:
                names = "(no tools)"
            self.io.print(
                f"  {g:<10} {state:<11} {s.describe_chars:>5} chars react / "
                f"{s.schema_chars:>5} chars schema  {names}"
            )
        self.io.print(
            f"auto rule: {'on' if self.cfg.tool_groups.auto_simple else 'off'} "
            "('simple' requests load only core tools unless a signal needs more)"
        )
        t = measure(reg, excluded_tools(reg.names(), self.agent.ctx.disabled_groups))
        self.io.print(
            f"enabled total: react {t.describe_chars} chars (~{t.describe_tokens} tok) / "
            f"schema {t.schema_chars} chars (~{t.schema_tokens} tok)"
        )

    def cmd_compact(self, args: list[str]) -> None:
        if self.session is None:
            self.io.print("Nothing to compact.")
            return
        n = self.agent.compact(self.session)
        self.io.print(f"Compacted {n} messages into the memory summary.")

    def cmd_sessions(self, args: list[str]) -> None:
        ids = self.agent.sessions.list_ids()
        if not ids:
            self.io.print("No saved sessions.")
            return
        for sid in ids[-20:]:
            s = self.agent.sessions.load(sid)
            mark = "*" if self.session and self.session.id == sid else " "
            self.io.print(
                f"{mark} {sid}  {s.state.value:<10} {s.task.replace(chr(10), ' ')[:60]}"
            )

    def cmd_resume(self, args: list[str]) -> None:
        if len(args) > 1:
            raise ConfigError("usage: /resume [id]")
        if args:
            sid = args[0]
        else:
            ids = self.agent.sessions.list_ids()[-10:]
            if not ids:
                self.io.print("No saved sessions.")
                return
            for i, cand in enumerate(ids, 1):
                self.io.print(f"  {i}) {cand}  {self.agent.sessions.load(cand).task[:60]}")
            a = self._ask("Session number or id (empty = cancel): ")
            if not a:
                self.io.print("cancelled")
                return
            sid = ids[int(a) - 1] if a.isdigit() and 1 <= int(a) <= len(ids) else a
        self.session = self.agent.sessions.load(sid)
        self.io.print(
            f"Resumed session {sid} (state: {self.session.state.value}; "
            f"task: {self.session.task[:60]}). Type a request to continue."
        )
        if self.session.task:
            self.io.print(f"{PROMPT}{self.session.task}")
        if self.session.final_answer:
            self.io.markdown(self.session.final_answer)

    def _set_approval(self, mode: str) -> None:
        self.policy.mode = mode
        self.opts.approval = mode

    def cycle_approval(self) -> str:
        mode = next_approval(self.policy.mode)
        self._set_approval(mode)
        self._sync_ui()
        return f"approval mode: {mode} (Shift+Tab cycles ask -> auto -> deny)"

    def toggle_todos(self) -> str:
        self.ui.show_todos = not self.ui.show_todos
        return f"TODO view: {'on' if self.ui.show_todos else 'off'} (Ctrl+T toggles)"

    def cmd_approval(self, args: list[str]) -> None:
        if not args:
            self.io.print(f"approval mode: {self.policy.mode} "
                          f"(options: {', '.join(APPROVAL_MODES)})")
            return
        if args[0] not in APPROVAL_MODES:
            raise ConfigError(
                f"invalid approval mode '{args[0]}'; expected one of {list(APPROVAL_MODES)}"
            )
        self._set_approval(args[0])
        self._sync_ui()
        self.io.print(f"approval mode: {args[0]}")
        if args[0] == "policy":
            self.io.print(POLICY_MODE_NOTICE)

    def cmd_theme(self, args: list[str]) -> None:
        if not args:
            self.io.print(f"theme: {self.ui.theme.name} (available: {', '.join(THEMES)})")
            return
        if len(args) != 1:
            raise ConfigError(THEME_USAGE)
        if args[0] not in THEMES:
            raise ConfigError(f"unknown theme '{args[0]}'; expected one of {list(THEMES)}")
        self.ui.theme = THEMES[args[0]]
        self.io.print(
            f"theme: {args[0]} (this session only; set [ui] theme in cora.toml to keep it)"
        )

    def cmd_expand(self, args: list[str]) -> None:
        if args:
            raise ConfigError(EXPAND_USAGE)
        if self.ui.last_collapsed is None:
            self.io.print(
                "No collapsed tool result to expand (results over 10 lines are collapsed "
                "in the terminal UI)."
            )
            return
        self.io.print(self.ui.last_collapsed.rstrip("\n"))

    def cmd_diff(self, args: list[str]) -> None:
        if is_git_repo(self.workdir):
            d = git_output(self.workdir, ["diff"]) or ""
            status = git_output(self.workdir, ["status", "--porcelain"]) or ""
            untracked = [ln[3:] for ln in status.splitlines() if ln.startswith("??")]
            if not d and not untracked:
                self.io.print("No changes (git diff is empty).")
                return
            if d:
                self.io.show_diff(d)
            if untracked:
                self.io.print("Untracked files:")
                for u in untracked:
                    self.io.print(f"  {u}")
            return
        if not self.originals:
            self.io.print("No files changed in this session.")
            return
        for rel, before in self.originals.items():
            p = self.workdir / rel
            after = p.read_text(encoding="utf-8") if p.exists() else ""
            d = unified_diff(rel, before or "", after)
            if d:
                self.io.show_diff(d)

    def cmd_init(self, args: list[str]) -> None:
        target = self.workdir / "CORA.md"
        if target.exists():
            self.io.print("CORA.md already exists; not overwriting.")
            return
        target.write_text(draft_guide(self.workdir), encoding="utf-8")
        self.project = load_project_context(self.workdir)
        self._reload()
        self.io.print(
            "Created CORA.md (draft). Review and edit it; it is loaded into the system prompt."
        )

    def cmd_route(self, args: list[str]) -> None:
        ev = self._last_route
        if ev is None:
            self.io.print("No routing decision yet. Send a request first.")
            return
        self.io.print(
            f"route: grade={ev.get('grade', 'unknown')} tier={ev['tier']} "
            f"model={ev['model']} score={ev['score']}"
        )
        self.io.print(f"reason: {ev.get('reason', '')}")
        if self.cfg.router.pin:
            self.io.print(f"pinned: {self.cfg.router.pin} (/model unpin to restore routing)")

    def cmd_check(self, args: list[str]) -> None:
        if not self._rest:
            if self.check_command:
                self.io.print(f"check: {self.check_command}")
            else:
                self.io.print("check: off (/check <command> to set)")
            return
        if self._rest == "off":
            self.check_command = None
            self.io.print("check: off")
            return
        self.check_command = self._rest
        self.io.print(
            f"check: {self._rest} (runs before each final answer this session, up to "
            f"{self.cfg.agent.sensor_max_retries} retries; /check off to stop)"
        )

    def cmd_delegate(self, args: list[str]) -> None:
        if not args:
            d = self.cfg.delegation
            if self.delegate_override is not None:
                src = "/delegate"
            elif self.opts.delegate:
                src = "--delegate"
            elif self.base_cfg.delegation.enabled:
                src = "config"
            else:
                src = "default"
            e = self.session.explore_calls if self.session else 0
            g = self.session.delegations if self.session else 0
            self.io.print(
                f"delegation: {'on' if d.enabled else 'off'} (source: {src}); explore: parallel "
                f"{'on' if d.parallel_explore else 'off'}, concurrency {d.explore_concurrency}, "
                f"calls {e}/{d.explore_max_calls}; general calls {g}/{d.max_per_session} "
                "this session"
            )
            return
        if args not in (["on"], ["off"]):
            raise ConfigError(DELEGATE_USAGE)
        self.delegate_override = args[0] == "on"
        self._reload()
        if self.delegate_override and "delegate" in self.agent.ctx.disabled_groups:
            self.group_overrides["delegate"] = True
            self._apply_groups()
            self.io.print("tool group delegate: on (needed for delegation)")
        self.io.print(f"delegation: {args[0]} for this session (/reset restores the start value)")

    def cmd_mouse(self, args: list[str]) -> None:
        if args not in ([], ["on"], ["off"]):
            raise ConfigError(MOUSE_USAGE)
        self.io.print("Mouse capture is a TUI feature (full-screen mode); this session does not "
                      "capture the mouse.")

    def cmd_copy(self, args: list[str]) -> None:
        if args:
            raise ConfigError(COPY_USAGE)
        if self.last_answer is None:
            self.io.print("Nothing to copy yet: no answer in this session.")
            return
        copy = getattr(self.io, "copy_text", None)
        if copy is None:
            self.io.print("Copy works in the TUI only (OSC 52); select the text with your "
                          "terminal instead.")
            return
        self.io.print(copy(self.last_answer))

    def cmd_status(self, args: list[str]) -> None:
        summary = CostMeter.from_list(self.session.meter if self.session else []).summary()
        approval = f"approval: {self.policy.mode}"
        if self.policy.always_allowed:
            approval += (
                f" (always allowed this session: {', '.join(sorted(self.policy.always_allowed))})"
            )
        name = self.project.guide_path.name if self.project.guide_path is not None else None
        self.io.print(f"workdir:  {self.workdir}")
        self.io.print(f"config:   {self.opts.config_path}")
        self.io.print("models:")
        self._print_models()
        self.io.print(approval)
        self.io.print(f"plan mode: {'on' if self.plan_mode else 'off'}")
        self.io.print(f"check:    {self.check_command or 'off'}")
        if pin := self.cfg.router.pin:
            self.io.print(f"routing:  pinned to {pin} (/model unpin to restore)")
        else:
            grades = " ".join(f"{g}={self.cfg.router.grades[g]}" for g in GRADES)
            self.io.print(f"routing:  auto ({grades})")
        d = self.cfg.delegation
        if d.enabled:
            used = self.session.delegations if self.session else 0
            self.io.print(f"delegation: on (used {used}/{d.max_per_session} this session)")
        else:
            self.io.print("delegation: off")
        self.io.print(f"session:  {self.session.id if self.session else '(new)'}")
        self.io.print(
            f"cost:     ${summary['total_cost_usd']:.6f} ({summary['calls']} calls, "
            f"{summary['unknown_cost_calls']} with unknown price)"
        )
        self.io.print(f"guide:    {name or 'none'}")

    def _farewell(self) -> None:
        if self.session and self.session.meter:
            self.io.print(
                format_summary(
                    CostMeter.from_list(self.session.meter).summary(self.session.delegation_stats)
                )
            )
            self.io.print(f"session: {self.session.id} (resume with /resume {self.session.id})")
