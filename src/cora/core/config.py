from __future__ import annotations

import dataclasses
import json
import math
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from cora.core.errors import ConfigError
from cora.core.policy import PolicySettings, parse_policy
from cora.core.toolgroups import OPTIONAL_GROUPS, is_mcp_group, valid_mcp_server_name
from cora.core.types import DEFAULT_REACT_MAX_TOKENS

TIERS = ("cheap", "strong")
GRADES = ("simple", "medium", "complex")
DEFAULT_GRADES = {"simple": "cheap", "medium": "cheap", "complex": "strong"}
APPROVAL_MODES = ("ask", "auto", "deny", "policy")
CYCLE_APPROVAL_MODES = ("ask", "auto", "deny")
DEFAULT_PROVIDER = "openrouter"
SOURCES = ("default", "user", "flag", "pin")
_MODEL_REQUIRED_KEYS = ("id", "provider", "tier", "input_usd_per_mtok", "output_usd_per_mtok")
COST_MODELS = ("catalog", "self_hosted")
TOOL_PROTOCOLS = ("react", "native", "auto")
GATE_KEYS = ("verify_before_final", "compile_check", "edge_case_prompt", "stub_check")
FIX_KEYS = ("json_string_repair", "overwrite_guard")
WRITE_KEYS = ("raw_file_body", "repeat_breaker", "located_errors")
BENCH_PROTOCOLS = ("react", "native")
PROVIDER_SORTS = ("throughput", "latency", "price")
PROVIDER_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9._/-]*")
DECIDER_KINDS = ("heuristic", "llm")
DECIDER_USES = ("tier_routing", "toolgroup", "sensor_hint")
UI_THEMES = ("default", "dark", "light", "mono")
TOOL_DESCRIPTION_MODES = ("full", "terse")
UI_COLORS = ("auto", "always", "never")
SALE_BIDS = ("heuristic", "llm")
MCP_DEFAULT_TIMEOUT_S = 30.0
RECORD_MODES = ("off", "record", "replay")
ROUTER_MODES = ("heuristic", "cheap_first")
RECORD_MODE_ENV = "CORA_RECORD_MODE"
SUMMARIZE_MODES = ("off", "llm")
RECORD_DIR_ENV = "CORA_RECORD_DIR"
OPENAI_COMPAT = "openai_compat"
_MCP_SERVER_KEYS = frozenset({"command", "args", "env", "enabled", "timeout_s"})


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    tier: str
    input_usd_per_mtok: float | None
    output_usd_per_mtok: float | None
    context_tokens: int = 128000
    source: str = "default"
    tool_protocol: str | None = None
    supports_tools: bool | None = None
    cache: bool = False
    cache_read_usd_per_mtok: float | None = None
    cost_model: str = "catalog"
    free_tier: bool = False

    @property
    def price_known(self) -> bool:
        return self.input_usd_per_mtok is not None and self.output_usd_per_mtok is not None

    @property
    def self_hosted(self) -> bool:
        return self.cost_model == "self_hosted"


@dataclass(frozen=True)
class RouterSettings:
    threshold: int = 3
    escalate_on_retry: bool = True
    medium_threshold: int = 1
    default: str = "cheap"
    grades: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_GRADES))
    pin: str | None = None
    mode: str = "heuristic"


@dataclass(frozen=True)
class AgentSettings:
    max_iterations: int = 30
    max_cost_usd: float = 0.5
    max_attempts: int = 2
    approval: str = "ask"
    shell_timeout_s: int = 60
    max_parallel_tools: int = 4
    tool_protocol: str = "react"
    sensor_max_retries: int = 3
    sensor_feedback_chars: int = 2000
    tripwire: bool = False
    max_wall_s: float = 0
    max_tool_calls: int = 0
    budget_warn_fraction: float = 0.8
    lenient_parse: bool = True
    react_max_tokens: int = DEFAULT_REACT_MAX_TOKENS
    auto_check: bool = False
    tamper_guard: bool = False
    selftest: bool = False
    ladder: bool = False
    call_timeout_s: int = 300
    verify_before_final: bool = True
    compile_check: bool = True
    edge_case_prompt: bool = True
    stub_check: bool = True
    json_string_repair: bool = True
    overwrite_guard: bool = True
    raw_file_body: bool = False
    repeat_breaker: bool = False
    located_errors: bool = False


@dataclass(frozen=True)
class EscalationSettings:
    enabled: bool = False
    on_stuck_iterations: int = 4
    on_tripwire: bool = True
    on_budget_fraction: float = 0.0
    strong_model: str = ""


@dataclass(frozen=True)
class HeadlessSettings:
    max_wall_s: float = 900
    max_tool_calls: int = 200


@dataclass(frozen=True)
class ProjectSettings:
    gate_retries: int = 1
    max_milestones: int = 8
    condition_timeout_s: int = 60
    condition_output_chars: int = 2000


@dataclass(frozen=True)
class BenchSettings:
    models: tuple[str, ...] = ()
    protocols: tuple[str, ...] = ("react", "native")
    max_cost_usd: float = 0.30
    max_task_cost_usd: float | None = None
    max_iterations: int = 12
    stall_threshold_s: float = 60.0


@dataclass(frozen=True)
class MemorySettings:
    context_budget_tokens: int = 12000
    keep_last_messages: int = 8
    max_observation_chars: int = 4000
    ledger: bool = False
    ledger_max_chars: int = 1500
    summarize: str = "off"


@dataclass(frozen=True)
class ContextSettings:
    repo_map: bool = False
    repo_map_max_chars: int = 4000
    max_files: int = 500
    dedupe_reads: bool = False


@dataclass(frozen=True)
class CacheSettings:
    prompt_cache: bool = False
    tool_descriptions: str = "full"
    compress_observations: bool = False
    compress_chars: int = 800


@dataclass(frozen=True)
class RecordSettings:
    mode: str = "off"
    dir: str = ".cora/recordings"


@dataclass(frozen=True)
class DelegationSettings:
    enabled: bool = False
    max_per_session: int = 2
    max_steps: int = 6
    max_tokens: int = 20000
    timeout_s: float = 60.0
    model: str = "cheap"
    parallel_explore: bool = True
    explore_concurrency: int = 3
    explore_max_calls: int = 6
    max_total_tokens: int = 120000
    max_total_cost_usd: float = 0.05
    summary_max_chars: int = 1200
    nudge: bool = False


@dataclass(frozen=True)
class ToolSettings:
    mention_max_file_chars: int = 8000
    mention_max_total_chars: int = 20000
    mention_max_dir_entries: int = 100
    git_max_output_chars: int = 3500
    git_log_max_count: int = 50
    git_timeout_s: float = 15.0
    web_max_download_bytes: int = 200000
    web_max_output_chars: int = 3500
    web_timeout_s: float = 15.0
    web_max_redirects: int = 5


@dataclass(frozen=True)
class ToolGroupSettings:
    disabled: tuple[str, ...] = ()
    auto_simple: bool = False


@dataclass(frozen=True)
class DeciderSettings:
    kind: str = "heuristic"
    model: str = "cheap"
    timeout_s: float = 5.0
    max_cost_per_decision: float = 0.001
    min_confidence: float = 0.7
    tier_routing: bool = False
    toolgroup: bool = False
    sensor_hint: bool = False


@dataclass(frozen=True)
class UiSettings:
    theme: str = "default"
    ascii: bool = False
    color: str = "auto"
    tui: bool = True
    mouse: bool = True
    exit_summary: bool = True
    scrollback_blocks: int = 5000


@dataclass(frozen=True)
class SaleSettings:
    enabled: bool = False
    bids: str = "heuristic"
    reward: float = 20.0
    budget_cap: float = 20.0
    max_escalations: int = 1
    tiers_file: str = ""


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    enabled: bool = True
    timeout_s: float = MCP_DEFAULT_TIMEOUT_S
    error: str | None = None


MCP_SERVE_APPROVALS = ("policy", "deny")
MCP_OUTPUT_CHARS_MIN = 1000
MCP_OUTPUT_CHARS_LIMIT = 50000


@dataclass(frozen=True)
class McpServeSettings:
    max_cost_usd: float = 0.5
    max_iterations: int = 30
    max_wall_s: float = 600.0
    max_tool_calls: int = 200
    max_depth: int = 1
    max_output_chars: int = 20000
    approval: str = "policy"


MCP_SERVE_KEYS = frozenset(f.name for f in dataclasses.fields(McpServeSettings))


@dataclass(frozen=True)
class McpSettings:
    servers: tuple[McpServerConfig, ...] = ()
    warnings: tuple[str, ...] = ()
    serve: McpServeSettings = field(default_factory=McpServeSettings)


@dataclass(frozen=True)
class CoraConfig:
    models: tuple[ModelSpec, ...]
    providers: dict[str, dict]
    router: RouterSettings
    agent: AgentSettings
    memory: MemorySettings
    delegation: DelegationSettings = field(default_factory=DelegationSettings)
    bench: BenchSettings = field(default_factory=BenchSettings)
    tools: ToolSettings = field(default_factory=ToolSettings)
    tool_groups: ToolGroupSettings = field(default_factory=ToolGroupSettings)
    decider: DeciderSettings = field(default_factory=DeciderSettings)
    ui: UiSettings = field(default_factory=UiSettings)
    mcp: McpSettings = field(default_factory=McpSettings)
    sale: SaleSettings = field(default_factory=SaleSettings)
    policy: PolicySettings = field(default_factory=PolicySettings)
    headless: HeadlessSettings = field(default_factory=HeadlessSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    project: ProjectSettings = field(default_factory=ProjectSettings)
    record: RecordSettings = field(default_factory=RecordSettings)
    escalation: EscalationSettings = field(default_factory=EscalationSettings)


@dataclass(frozen=True)
class ModelOverride:
    tier: str
    id: str
    provider: str | None = None
    input_usd_per_mtok: float | None = None
    output_usd_per_mtok: float | None = None


def _positive_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def _nonneg_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


def _nonneg_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _positive_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def validate_openrouter_settings(settings: Mapping[str, Any]) -> None:
    for key in ("request_deadline_s", "stream_stall_timeout_s"):
        if key in settings and not _positive_number(settings[key]):
            raise ConfigError(f"invalid [providers.openrouter].{key}: must be a number > 0")
    sort = settings.get("provider_sort")
    if sort is not None and sort not in PROVIDER_SORTS:
        raise ConfigError(
            f"invalid [providers.openrouter].provider_sort {sort!r}; expected one of "
            f"{list(PROVIDER_SORTS)} or unset"
        )
    rp = settings.get("require_parameters")
    if rp is not None and not isinstance(rp, bool):
        raise ConfigError(
            "invalid [providers.openrouter].require_parameters: must be true or false"
        )
    ignore = settings.get("provider_ignore")
    if ignore is not None and not (
        isinstance(ignore, (list, tuple))
        and len(ignore) > 0
        and all(isinstance(s, str) and PROVIDER_SLUG_RE.fullmatch(s) for s in ignore)
        and len(set(ignore)) == len(ignore)
    ):
        raise ConfigError(
            "invalid [providers.openrouter].provider_ignore: must be a non-empty list of "
            'distinct lowercase provider slugs, e.g. ["amazon-bedrock"]'
        )


def validate_openai_compat_settings(
    settings: Mapping[str, Any], section: str = "providers.<name>"
) -> None:
    prefix = f"invalid [{section}]"
    for key in ("base_url", "api_key_env"):
        value = settings.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f'{prefix}: {key} is required (type = "{OPENAI_COMPAT}")')
    for key in ("timeout_s", "request_deadline_s", "stream_stall_timeout_s"):
        if key in settings and not _positive_number(settings[key]):
            raise ConfigError(f"{prefix}.{key}: must be a number > 0")
    if "rpm_limit" in settings and not _positive_int(settings["rpm_limit"]):
        raise ConfigError(
            f"{prefix}: rpm_limit must be an integer > 0 (omit it to disable the throttle)"
        )
    if "max_429_retries" in settings and not _nonneg_int(settings["max_429_retries"]):
        raise ConfigError(f"{prefix}: max_429_retries must be an integer >= 0")


def split_model_ref(ref: str) -> tuple[str, str | None]:
    mid, sep, prov = ref.rpartition("@")
    if not sep or not mid or not prov:
        return ref, None
    return mid, prov


def find_model(models: Sequence[ModelSpec], ref: str | None) -> ModelSpec | None:
    if not ref:
        return None
    exact = next((m for m in models if m.id == ref), None)
    if exact is not None:
        return exact
    mid, prov = split_model_ref(ref)
    if prov is None:
        return None
    return next((m for m in models if m.id == mid and m.provider == prov), None)


def model_ref(spec: ModelSpec, models: Sequence[ModelSpec]) -> str:
    first = next((m for m in models if m.id == spec.id), None)
    if first is None or first.provider == spec.provider:
        return spec.id
    return f"{spec.id}@{spec.provider}"


def check_decider_model(model: object, models: Sequence[ModelSpec]) -> None:
    if (
        isinstance(model, str)
        and model
        and (model in TIERS or find_model(models, model) is not None)
    ):
        return
    raise ConfigError(
        f"invalid [decider].model {model!r}: expected a tier name {list(TIERS)} "
        "or a [[models]] id (optionally id@provider)"
    )


def _parse_mcp_server(name: str, table: Any) -> McpServerConfig:
    label = f"[mcp.servers.{name}]"
    if not valid_mcp_server_name(name):
        raise ConfigError(
            f"invalid MCP server name {name!r}: use 1-32 characters from A-Z a-z 0-9 _ - "
            "with no leading, trailing or doubled '_'"
        )
    if not isinstance(table, dict):
        raise ConfigError(f"invalid {label}: must be a table")
    unknown = sorted(set(table) - _MCP_SERVER_KEYS)
    if unknown:
        raise ConfigError(f"invalid {label}: unknown keys {unknown}")
    if "command" not in table:
        raise ConfigError(f"invalid {label}: 'command' is required")
    command = table["command"]
    if not isinstance(command, str) or not command.strip():
        raise ConfigError(f"invalid {label}.command: must be a non-empty string")
    args = table.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ConfigError(f"invalid {label}.args: must be a list of strings")
    env = table.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and k and "=" not in k and isinstance(v, str) for k, v in env.items()
    ):
        raise ConfigError(f'invalid {label}.env: must be a table of NAME = "string" values')
    enabled = table.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"invalid {label}.enabled: must be true or false")
    timeout = table.get("timeout_s", MCP_DEFAULT_TIMEOUT_S)
    if not _positive_number(timeout):
        raise ConfigError(f"invalid {label}.timeout_s: must be a number > 0")
    return McpServerConfig(
        name, command, tuple(args), tuple(sorted(env.items())), enabled, float(timeout)
    )


def _parse_mcp_serve(raw: dict[str, Any]) -> McpServeSettings:
    values: dict[str, Any] = {}
    for key in MCP_SERVE_KEYS & set(raw):
        v = raw[key]
        if key in ("max_cost_usd", "max_wall_s"):
            if not _positive_number(v) or not math.isfinite(v):
                raise ConfigError(
                    f"invalid [mcp].{key}: must be a number > 0 "
                    "(server ceilings cannot be unlimited)"
                )
            values[key] = float(v)
        elif key in ("max_iterations", "max_tool_calls", "max_depth"):
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ConfigError(
                    f"invalid [mcp].{key}: must be an integer >= 1 "
                    "(server ceilings cannot be unlimited)"
                )
            values[key] = v
        elif key == "max_output_chars":
            if (
                isinstance(v, bool)
                or not isinstance(v, int)
                or not MCP_OUTPUT_CHARS_MIN <= v < MCP_OUTPUT_CHARS_LIMIT
            ):
                raise ConfigError(
                    "invalid [mcp].max_output_chars: must be an integer from 1000 to 49999 "
                    "(below the 50000-char client spill limit)"
                )
            values[key] = v
        elif key == "approval":
            if v not in MCP_SERVE_APPROVALS:
                raise ConfigError(
                    'invalid [mcp].approval: must be "policy" or "deny" '
                    "(cora mcp serve never prompts and never auto-approves)"
                )
            values[key] = v
    return McpServeSettings(**values)


def parse_mcp(raw: Any) -> McpSettings:
    if raw is None:
        return McpSettings()
    if not isinstance(raw, dict):
        return McpSettings(
            warnings=("warning: invalid [mcp] section (must be a table); MCP servers are disabled",)
        )
    serve = _parse_mcp_serve(raw)
    warnings = [
        f"warning: unknown key [mcp].{k} ignored"
        for k in sorted(raw)
        if k not in MCP_SERVE_KEYS | {"servers"}
    ]
    servers_raw = raw.get("servers", {})
    if not isinstance(servers_raw, dict):
        warnings.append(
            "warning: invalid [mcp.servers] (must be a table of servers); MCP servers are disabled"
        )
        return McpSettings((), tuple(warnings), serve)
    servers: list[McpServerConfig] = []
    for name, table in servers_raw.items():
        try:
            servers.append(_parse_mcp_server(str(name), table))
        except ConfigError as e:
            servers.append(McpServerConfig(name=str(name), enabled=False, error=str(e)))
            warnings.append(f"warning: {e}; MCP server '{name}' is disabled")
    return McpSettings(tuple(servers), tuple(warnings), serve)


def parse_config(data: dict[str, Any]) -> CoraConfig:
    raw_models = data.get("models")
    if not raw_models:
        raise ConfigError("config must define at least one [[models]] entry")
    models: list[ModelSpec] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_models:
        missing = [k for k in _MODEL_REQUIRED_KEYS if k not in raw]
        if missing:
            raise ConfigError(f"model entry missing keys {missing}: {raw}")
        if raw["tier"] not in TIERS:
            raise ConfigError(
                f"invalid tier '{raw['tier']}' for model '{raw['id']}'; "
                f"expected one of {list(TIERS)}"
            )
        tp = raw.get("tool_protocol")
        if tp is not None and tp not in TOOL_PROTOCOLS:
            raise ConfigError(
                f"invalid tool_protocol '{tp}' for model '{raw['id']}'; "
                f"expected one of {list(TOOL_PROTOCOLS)}"
            )
        st = raw.get("supports_tools")
        if st is not None and not isinstance(st, bool):
            raise ConfigError(f"supports_tools for model '{raw['id']}' must be true or false")
        ca = raw.get("cache", False)
        if not isinstance(ca, bool):
            raise ConfigError(f"cache for model '{raw['id']}' must be true or false")
        cr = raw.get("cache_read_usd_per_mtok")
        if cr is not None and not _nonneg_number(cr):
            raise ConfigError(
                f"cache_read_usd_per_mtok for model '{raw['id']}' must be a number >= 0"
            )
        cm = raw.get("cost_model", "catalog")
        if cm not in COST_MODELS:
            raise ConfigError(
                f"invalid cost_model {cm!r} for model '{raw['id']}'; "
                f"expected one of {list(COST_MODELS)}"
            )
        ft = raw.get("free_tier", False)
        if not isinstance(ft, bool):
            raise ConfigError(f"free_tier for model '{raw['id']}' must be true or false")
        key =(str(raw["id"]), str(raw["provider"]))
        if key in seen:
            raise ConfigError(
                f"duplicate [[models]] entry for model '{raw['id']}' with provider "
                f"'{raw['provider']}'; each (id, provider) pair must be unique"
            )
        seen.add(key)
        models.append(
            ModelSpec(
                id=raw["id"],
                provider=raw["provider"],
                tier=raw["tier"],
                input_usd_per_mtok=float(raw["input_usd_per_mtok"]),
                output_usd_per_mtok=float(raw["output_usd_per_mtok"]),
                context_tokens=int(raw.get("context_tokens", 128000)),
                tool_protocol=tp,
                supports_tools=st,
                cache=ca,
                cache_read_usd_per_mtok=float(cr) if cr is not None else None,
                cost_model=cm,
                free_tier=ft,
            )
        )
    try:
        agent = AgentSettings(**data.get("agent", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [agent] section: {e}") from e
    if agent.approval not in APPROVAL_MODES:
        raise ConfigError(
            f"invalid agent.approval '{agent.approval}'; expected one of {list(APPROVAL_MODES)}"
        )
    if agent.tool_protocol not in TOOL_PROTOCOLS:
        raise ConfigError(
            f"invalid agent.tool_protocol '{agent.tool_protocol}'; "
            f"expected one of {list(TOOL_PROTOCOLS)}"
        )
    raw_router = dict(data.get("router", {}))
    grades_raw = raw_router.pop("grades", {})
    if not isinstance(grades_raw, dict) or set(grades_raw) - set(GRADES):
        bad = sorted(set(grades_raw) - set(GRADES)) if isinstance(grades_raw, dict) else grades_raw
        raise ConfigError(f"invalid [router.grades] keys {bad}; expected {list(GRADES)}")
    try:
        router = RouterSettings(
            **raw_router,
            grades={**DEFAULT_GRADES, **{k: str(v) for k, v in grades_raw.items()}},
        )
    except TypeError as e:
        raise ConfigError(f"invalid [router] section: {e}") from e
    if router.mode not in ROUTER_MODES:
        raise ConfigError(
            f"invalid [router].mode {router.mode!r}; expected one of {list(ROUTER_MODES)}"
        )
    if router.medium_threshold > router.threshold:
        raise ConfigError("router.medium_threshold must be <= router.threshold")
    if agent.max_parallel_tools < 1:
        raise ConfigError("agent.max_parallel_tools must be >= 1")
    if (
        not isinstance(agent.sensor_max_retries, int)
        or isinstance(agent.sensor_max_retries, bool)
        or agent.sensor_max_retries < 0
    ):
        raise ConfigError("agent.sensor_max_retries must be an integer >= 0")
    if not isinstance(agent.sensor_feedback_chars, int) or agent.sensor_feedback_chars < 200:
        raise ConfigError("agent.sensor_feedback_chars must be an integer >= 200")
    if not isinstance(agent.tripwire, bool):
        raise ConfigError("agent.tripwire must be true or false")
    if not _nonneg_number(agent.max_cost_usd):
        raise ConfigError("invalid [agent].max_cost_usd: must be a number >= 0")
    if not _nonneg_int(agent.max_iterations):
        raise ConfigError("invalid [agent].max_iterations: must be an integer >= 0")
    if not _nonneg_number(agent.max_wall_s):
        raise ConfigError("invalid [agent].max_wall_s: must be a number >= 0 (0 = unlimited)")
    if not _nonneg_int(agent.max_tool_calls):
        raise ConfigError("invalid [agent].max_tool_calls: must be an integer >= 0 (0 = unlimited)")
    bwf = agent.budget_warn_fraction
    if isinstance(bwf, bool) or not isinstance(bwf, (int, float)) or not 0 < bwf <= 1:
        raise ConfigError("invalid [agent].budget_warn_fraction: must be a number > 0 and <= 1")
    if not isinstance(agent.lenient_parse, bool):
        raise ConfigError("invalid [agent].lenient_parse: must be true or false")
    rmt = agent.react_max_tokens
    if isinstance(rmt, bool) or not isinstance(rmt, int) or not 256 <= rmt <= 32768:
        raise ConfigError("invalid [agent].react_max_tokens: must be an integer from 256 to 32768")
    cts = agent.call_timeout_s
    if isinstance(cts, bool) or not isinstance(cts, int) or not 10 <= cts <= 3600:
        raise ConfigError(
            "invalid [agent].call_timeout_s: must be an integer from 10 to 3600 "
            "(seconds per model call)"
        )
    for key in (
        "auto_check", "tamper_guard", "selftest", "ladder", *GATE_KEYS, *FIX_KEYS, *WRITE_KEYS
    ):
        if not isinstance(getattr(agent, key), bool):
            raise ConfigError(f"invalid [agent].{key}: must be true or false")
    try:
        headless = HeadlessSettings(**data.get("headless", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [headless] section: {e}") from e
    if not _nonneg_number(headless.max_wall_s):
        raise ConfigError("invalid [headless].max_wall_s: must be a number >= 0 (0 = unlimited)")
    if not _nonneg_int(headless.max_tool_calls):
        raise ConfigError(
            "invalid [headless].max_tool_calls: must be an integer >= 0 (0 = unlimited)"
        )
    if "project" in data and not isinstance(data["project"], dict):
        raise ConfigError("invalid [project] section: must be a table")
    try:
        project = ProjectSettings(**data.get("project", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [project] section: {e}") from e
    if not _nonneg_int(project.gate_retries):
        raise ConfigError("invalid [project].gate_retries: must be an integer >= 0 (0 = no retry)")
    for key in ("max_milestones", "condition_timeout_s", "condition_output_chars"):
        if not _positive_int(getattr(project, key)):
            raise ConfigError(f"invalid [project].{key}: must be an integer > 0")
    if "context" in data and not isinstance(data["context"], dict):
        raise ConfigError("invalid [context] section: must be a table")
    try:
        context = ContextSettings(**data.get("context", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [context] section: {e}") from e
    for key in ("repo_map", "dedupe_reads"):
        if not isinstance(getattr(context, key), bool):
            raise ConfigError(f"invalid [context].{key}: must be true or false")
    for key in ("repo_map_max_chars", "max_files"):
        if not _positive_int(getattr(context, key)):
            raise ConfigError(f"invalid [context].{key}: must be an integer > 0")
    if "cache" in data and not isinstance(data["cache"], dict):
        raise ConfigError("invalid [cache] section: must be a table")
    try:
        cache = CacheSettings(**data.get("cache", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [cache] section: {e}") from e
    for key in ("prompt_cache", "compress_observations"):
        if not isinstance(getattr(cache, key), bool):
            raise ConfigError(f"invalid [cache].{key}: must be true or false")
    if cache.tool_descriptions not in TOOL_DESCRIPTION_MODES:
        raise ConfigError(
            f"invalid [cache].tool_descriptions: expected one of {list(TOOL_DESCRIPTION_MODES)}"
        )
    if not _positive_int(cache.compress_chars):
        raise ConfigError("invalid [cache].compress_chars: must be an integer > 0")
    if "record" in data and not isinstance(data["record"], dict):
        raise ConfigError("invalid [record] section: must be a table")
    try:
        record = RecordSettings(**data.get("record", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [record] section: {e}") from e
    if record.mode not in RECORD_MODES:
        raise ConfigError(f"invalid [record].mode: expected one of {list(RECORD_MODES)}")
    if not isinstance(record.dir, str) or not record.dir:
        raise ConfigError("invalid [record].dir: must be a non-empty string path")
    try:
        delegation = DelegationSettings(**data.get("delegation", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [delegation] section: {e}") from e
    if (
        delegation.max_per_session < 0
        or delegation.max_steps < 1
        or delegation.max_tokens < 1
        or delegation.timeout_s <= 0
    ):
        raise ConfigError(
            "invalid [delegation] limits: "
            "max_per_session>=0, max_steps>=1, max_tokens>=1, timeout_s>0"
        )
    if (
        not isinstance(delegation.parallel_explore, bool)
        or delegation.explore_concurrency < 1
        or delegation.explore_max_calls < 0
        or delegation.max_total_tokens < 1
        or delegation.max_total_cost_usd <= 0
        or delegation.summary_max_chars < 100
    ):
        raise ConfigError(
            "invalid [delegation] limits: parallel_explore true/false, explore_concurrency>=1, "
            "explore_max_calls>=0, max_total_tokens>=1, max_total_cost_usd>0, "
            "summary_max_chars>=100"
        )
    if not isinstance(delegation.nudge, bool):
        raise ConfigError("invalid [delegation].nudge: must be true or false")
    raw_bench = dict(data.get("bench", {}))
    for key in ("models", "protocols"):
        if key in raw_bench:
            raw_bench[key] = tuple(str(x) for x in raw_bench[key])
    try:
        bench = BenchSettings(**raw_bench)
    except TypeError as e:
        raise ConfigError(f"invalid [bench] section: {e}") from e
    bad_protocols = [p for p in bench.protocols if p not in BENCH_PROTOCOLS]
    if bad_protocols:
        raise ConfigError(
            f"invalid [bench].protocols {bad_protocols}; "
            f"expected values from {list(BENCH_PROTOCOLS)}"
        )
    st = bench.stall_threshold_s
    if (
        bench.max_cost_usd <= 0
        or (bench.max_task_cost_usd is not None and bench.max_task_cost_usd <= 0)
        or bench.max_iterations < 1
        or isinstance(st, bool)
        or not isinstance(st, (int, float))
        or st <= 0
    ):
        raise ConfigError(
            "invalid [bench] limits: "
            "max_cost_usd>0, max_task_cost_usd>0 or unset, max_iterations>=1, stall_threshold_s>0"
        )
    try:
        tools = ToolSettings(**data.get("tools", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [tools] section: {e}") from e
    sizes = (
        tools.mention_max_file_chars,
        tools.mention_max_total_chars,
        tools.mention_max_dir_entries,
        tools.git_max_output_chars,
        tools.git_log_max_count,
        tools.web_max_download_bytes,
        tools.web_max_output_chars,
    )
    if (
        any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in sizes)
        or not isinstance(tools.web_max_redirects, int)
        or tools.web_max_redirects < 0
        or tools.git_timeout_s <= 0
        or tools.web_timeout_s <= 0
        or tools.mention_max_total_chars < tools.mention_max_file_chars
    ):
        raise ConfigError(
            "invalid [tools] limits: "
            "sizes and counts >= 1, timeouts > 0, web_max_redirects >= 0, "
            "mention_max_total_chars >= mention_max_file_chars"
        )
    raw_tg = dict(data.get("tool_groups", {}))
    if "disabled" in raw_tg:
        if not isinstance(raw_tg["disabled"], list) or not all(
            isinstance(x, str) for x in raw_tg["disabled"]
        ):
            raise ConfigError("invalid [tool_groups].disabled: must be a list of group names")
        raw_tg["disabled"] = tuple(raw_tg["disabled"])
    try:
        tool_groups = ToolGroupSettings(**raw_tg)
    except TypeError as e:
        raise ConfigError(f"invalid [tool_groups] section: {e}") from e
    if "core" in tool_groups.disabled:
        raise ConfigError("invalid [tool_groups].disabled: the core group cannot be disabled")
    bad_groups = [
        g for g in tool_groups.disabled if g not in OPTIONAL_GROUPS and not is_mcp_group(g)
    ]
    if bad_groups:
        raise ConfigError(
            f"invalid [tool_groups].disabled {bad_groups}; expected values from "
            f'{list(OPTIONAL_GROUPS)} or "mcp:<server>"'
        )
    if not isinstance(tool_groups.auto_simple, bool):
        raise ConfigError("invalid [tool_groups].auto_simple: must be true or false")
    try:
        decider = DeciderSettings(**dict(data.get("decider", {})))
    except TypeError as e:
        raise ConfigError(f"invalid [decider] section: {e}") from e
    if decider.kind not in DECIDER_KINDS:
        raise ConfigError(
            f"invalid [decider].kind {decider.kind!r}; expected one of {list(DECIDER_KINDS)}"
        )
    check_decider_model(decider.model, models)
    for key in ("timeout_s", "max_cost_per_decision"):
        if not _positive_number(getattr(decider, key)):
            raise ConfigError(f"invalid [decider].{key}: must be a number > 0")
    mc = decider.min_confidence
    if isinstance(mc, bool) or not isinstance(mc, (int, float)) or not 0 <= mc <= 1:
        raise ConfigError("invalid [decider].min_confidence: must be a number from 0 to 1")
    for key in DECIDER_USES:
        if not isinstance(getattr(decider, key), bool):
            raise ConfigError(f"invalid [decider].{key}: must be true or false")
    try:
        ui = UiSettings(**dict(data.get("ui", {})))
    except TypeError as e:
        raise ConfigError(f"invalid [ui] section: {e}") from e
    if ui.theme not in UI_THEMES:
        raise ConfigError(f"invalid [ui].theme {ui.theme!r}; expected one of {list(UI_THEMES)}")
    if not isinstance(ui.ascii, bool):
        raise ConfigError("invalid [ui].ascii: must be true or false")
    if ui.color not in UI_COLORS:
        raise ConfigError(f"invalid [ui].color {ui.color!r}; expected one of {list(UI_COLORS)}")
    for key in ("tui", "mouse", "exit_summary"):
        if not isinstance(getattr(ui, key), bool):
            raise ConfigError(f"invalid [ui].{key}: must be true or false")
    sb = ui.scrollback_blocks
    if isinstance(sb, bool) or not isinstance(sb, int) or sb < 100:
        raise ConfigError("invalid [ui].scrollback_blocks: must be an integer >= 100")
    if "memory" in data and not isinstance(data["memory"], dict):
        raise ConfigError("invalid [memory] section: must be a table")
    try:
        memory = MemorySettings(**data.get("memory", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [memory] section: {e}") from e
    if not isinstance(memory.ledger, bool):
        raise ConfigError("invalid [memory].ledger: must be true or false")
    if not _positive_int(memory.ledger_max_chars) or not 200 <= memory.ledger_max_chars <= 20000:
        raise ConfigError("invalid [memory].ledger_max_chars: must be an integer from 200 to 20000")
    if memory.summarize not in SUMMARIZE_MODES:
        raise ConfigError(f"invalid [memory].summarize: expected one of {list(SUMMARIZE_MODES)}")
    try:
        sale =SaleSettings(**dict(data.get("sale", {})))
    except (TypeError, ValueError) as e:
        raise ConfigError(f"invalid [sale] section: {e}") from e
    if not isinstance(sale.enabled, bool):
        raise ConfigError("invalid [sale].enabled: must be true or false")
    if sale.bids not in SALE_BIDS:
        raise ConfigError(f"invalid [sale].bids {sale.bids!r}; expected one of {list(SALE_BIDS)}")
    for key in ("reward", "budget_cap"):
        if not _positive_number(getattr(sale, key)):
            raise ConfigError(f"invalid [sale].{key}: must be a number > 0")
    me = sale.max_escalations
    if not isinstance(me, int) or isinstance(me, bool) or me < 0:
        raise ConfigError("invalid [sale].max_escalations: must be an integer >= 0")
    if not isinstance(sale.tiers_file, str):
        raise ConfigError("invalid [sale].tiers_file: must be a string path")
    sale = dataclasses.replace(sale, reward=float(sale.reward), budget_cap=float(sale.budget_cap))
    providers = dict(data.get("providers", {}))
    for pname, sect in providers.items():
        if isinstance(sect, dict) and "type" in sect and not isinstance(sect["type"], str):
            raise ConfigError(f"invalid [providers.{pname}].type: must be a string")
        if isinstance(sect, dict) and sect.get("type") == OPENAI_COMPAT:
            validate_openai_compat_settings(sect, f"providers.{pname}")
    if isinstance(providers.get("openrouter"), dict):
        validate_openrouter_settings(providers["openrouter"])
    if "escalation" in data and not isinstance(data["escalation"], dict):
        raise ConfigError("invalid [escalation] section: must be a table")
    try:
        escalation = EscalationSettings(**data.get("escalation", {}))
    except TypeError as e:
        raise ConfigError(f"invalid [escalation] section: {e}") from e
    for key in ("enabled", "on_tripwire"):
        if not isinstance(getattr(escalation, key), bool):
            raise ConfigError(f"invalid [escalation].{key}: must be true or false")
    if not _nonneg_int(escalation.on_stuck_iterations):
        raise ConfigError(
            "invalid [escalation].on_stuck_iterations: must be an integer >= 0 (0 = off)"
        )
    frac = escalation.on_budget_fraction
    if not _nonneg_number(frac) or frac > 1:
        raise ConfigError(
            "invalid [escalation].on_budget_fraction: must be a number from 0 to 1 (0 = off)"
        )
    if not isinstance(escalation.strong_model, str):
        raise ConfigError("invalid [escalation].strong_model: must be a string")
    if escalation.strong_model and find_model(models, escalation.strong_model) is None:
        raise ConfigError(
            f"[escalation].strong_model '{escalation.strong_model}' is not in [[models]]"
        )
    return CoraConfig(
        models=tuple(models),
        providers=providers,
        router=router,
        agent=agent,
        memory=memory,
        delegation=delegation,
        bench=bench,
        tools=tools,
        tool_groups=tool_groups,
        decider=decider,
        ui=ui,
        mcp=parse_mcp(data.get("mcp")),
        sale=sale,
        policy=parse_policy(data.get("policy"), "cora.toml [policy]"),
        headless=headless,
        context=context,
        cache=cache,
        project=project,
        record=record,
        escalation=escalation,
    )


def effective_record_settings(
    settings: RecordSettings, environ: Mapping[str, str] | None = None
) -> RecordSettings:
    env = os.environ if environ is None else environ
    mode = settings.mode
    directory = settings.dir
    raw_mode = env.get(RECORD_MODE_ENV, "").strip()
    if raw_mode:
        if raw_mode not in RECORD_MODES:
            raise ConfigError(f"invalid {RECORD_MODE_ENV}: expected one of {list(RECORD_MODES)}")
        mode = raw_mode
    raw_dir = env.get(RECORD_DIR_ENV, "").strip()
    if raw_dir:
        directory = raw_dir
    return RecordSettings(mode=mode, dir=directory)


def load_config(path: Path) -> CoraConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with path.open("rb") as f:
        data = tomllib.load(f)
    return parse_config(data)


def find_config(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise ConfigError(f"config file not found: {explicit}")
        return explicit
    candidates = [Path.cwd() / "cora.toml", Path.home() / ".config" / "cora" / "cora.toml"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(str(resources.files("cora") / "data" / "cora.toml"))


def apply_model_override(config: CoraConfig, ov: ModelOverride, source: str) -> CoraConfig:
    if ov.tier not in TIERS:
        raise ConfigError(f"invalid tier '{ov.tier}'; expected one of {list(TIERS)}")
    if not ov.id.strip():
        raise ConfigError("model id must not be empty")
    if (ov.input_usd_per_mtok is None) != (ov.output_usd_per_mtok is None):
        raise ConfigError("input and output price must be given together")
    for price in (ov.input_usd_per_mtok, ov.output_usd_per_mtok):
        if price is not None and not (math.isfinite(price) and price >= 0):
            raise ConfigError(f"invalid price {price}; must be a finite number >= 0")
    base = find_model(config.models, ov.id)
    if base is None and split_model_ref(ov.id)[1] is not None:
        raise ConfigError(f"model '{ov.id}' is not in the current model configuration")
    model_id = base.id if base is not None else ov.id
    tier_base = next((m for m in config.models if m.tier == ov.tier), None)
    provider = ov.provider or (
        base.provider if base else tier_base.provider if tier_base else DEFAULT_PROVIDER
    )
    if ov.input_usd_per_mtok is not None:
        inp, out = ov.input_usd_per_mtok, ov.output_usd_per_mtok
    elif base:
        inp, out = base.input_usd_per_mtok, base.output_usd_per_mtok
    else:
        inp = out = None
    new = ModelSpec(
        model_id,
        provider,
        ov.tier,
        inp,
        out,
        base.context_tokens if base else 128000,
        source,
        tool_protocol=base.tool_protocol if base else None,
        supports_tools=base.supports_tools if base else None,
        cache=base.cache if base else False,
        cache_read_usd_per_mtok=(
            base.cache_read_usd_per_mtok if (base and ov.input_usd_per_mtok is None) else None
        ),
        cost_model=base.cost_model if base else "catalog",
    )
    return dataclasses.replace(
        config,
        models=(new,) + tuple(m for m in config.models if m.tier != ov.tier),
    )


def resolve_config(
    config: CoraConfig,
    user: Mapping[str, ModelOverride],
    flags: Sequence[ModelOverride],
) -> CoraConfig:
    for tier in TIERS:
        if tier in user:
            config = apply_model_override(config, user[tier], "user")
    for ov in flags:
        config = apply_model_override(config, ov, "flag")
    return config


def apply_pin(
    config: CoraConfig, model_id: str, price: tuple[float, float] | None = None
) -> CoraConfig:
    if not model_id.strip():
        raise ConfigError("model id must not be empty")
    if price is not None:
        for p in price:
            if not (math.isfinite(p) and p >= 0):
                raise ConfigError(f"invalid price {p}; must be a finite number >= 0")
    models = tuple(m for m in config.models if m.source != "pin")
    base = find_model(models, model_id)
    if base is None:
        if split_model_ref(model_id)[1] is not None:
            raise ConfigError(f"model '{model_id}' is not in the current model configuration")
        provider = next((m.provider for m in models if m.tier == "strong"), models[0].provider)
        inp, out = price if price is not None else (None, None)
        models = models + (ModelSpec(model_id, provider, "strong", inp, out, 128000, "pin"),)
    return dataclasses.replace(
        config,
        models=models,
        router=dataclasses.replace(config.router, pin=model_id),
    )


def unpriced_models(config: CoraConfig) -> list[ModelSpec]:
    return [m for m in config.models if not m.price_known]


def effective_protocol(config: CoraConfig, spec: ModelSpec) -> str:
    p = spec.tool_protocol or config.agent.tool_protocol
    if p == "auto":
        return "native" if spec.supports_tools else "react"
    return p


def secret_env_names(config: CoraConfig) -> frozenset[str]:
    names = {"OPENROUTER_API_KEY"}
    for p in config.providers.values():
        if isinstance(p, dict) and p.get("api_key_env"):
            names.add(str(p["api_key_env"]))
    return frozenset(names)


def user_models_path(workdir: Path) -> Path:
    return workdir / ".cora" / "models.toml"


def load_user_overrides(path: Path) -> dict[str, ModelOverride]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid user model file {path}: {e}") from e
    overrides: dict[str, ModelOverride] = {}
    for tier, raw in data.get("tiers", {}).items():
        if tier not in TIERS:
            raise ConfigError(f"{path}: invalid tier '{tier}'; expected one of {list(TIERS)}")
        if not isinstance(raw, dict) or "id" not in raw:
            raise ConfigError(f"{path}: [tiers.{tier}] requires 'id'")
        overrides[tier] = ModelOverride(
            tier,
            str(raw["id"]),
            raw.get("provider"),
            float(raw["input_usd_per_mtok"]) if "input_usd_per_mtok" in raw else None,
            float(raw["output_usd_per_mtok"]) if "output_usd_per_mtok" in raw else None,
        )
    return overrides


def save_user_overrides(path: Path, overrides: Mapping[str, ModelOverride]) -> None:
    if not overrides:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# CORA user model overrides (managed by the /model command). Do not commit."]
    for tier in TIERS:
        ov = overrides.get(tier)
        if ov is None:
            continue
        lines += ["", f"[tiers.{tier}]", f"id = {json.dumps(ov.id)}"]
        if ov.provider:
            lines.append(f"provider = {json.dumps(ov.provider)}")
        if ov.input_usd_per_mtok is not None:
            lines.append(f"input_usd_per_mtok = {float(ov.input_usd_per_mtok)!r}")
        if ov.output_usd_per_mtok is not None:
            lines.append(f"output_usd_per_mtok = {float(ov.output_usd_per_mtok)!r}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
