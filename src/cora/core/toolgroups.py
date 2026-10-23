import re
from collections.abc import Collection, Iterable

GROUPS: tuple[str, ...] = ("core", "git", "web", "plan-todo", "delegate")
OPTIONAL_GROUPS = GROUPS[1:]

MCP_TOOL_PREFIX = "mcp__"
MCP_GROUP_PREFIX = "mcp:"
MCP_SERVER_NAME_MAX = 32
MCP_SERVER_NAME_RE = re.compile(r"[A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*")


def mcp_group(server: str) -> str:
    return MCP_GROUP_PREFIX + server


def valid_mcp_server_name(name: str) -> bool:
    return len(name) <= MCP_SERVER_NAME_MAX and MCP_SERVER_NAME_RE.fullmatch(name) is not None


def is_mcp_group(group: str) -> bool:
    return group.startswith(MCP_GROUP_PREFIX) and valid_mcp_server_name(
        group[len(MCP_GROUP_PREFIX) :]
    )

TOOL_GROUPS: dict[str, str] = {
    "list_files": "core",
    "read_file": "core",
    "search": "core",
    "edit_file": "core",
    "write_file": "core",
    "delete_file": "core",
    "run_shell": "core",
    "git_status": "git",
    "git_diff": "git",
    "git_log": "git",
    "git_add": "git",
    "git_commit": "git",
    "git_branch": "git",
    "web_fetch": "web",
    "todo_write": "plan-todo",
    "submit_plan": "plan-todo",
    "delegate": "delegate",
}


def group_of(name: str) -> str | None:
    group = TOOL_GROUPS.get(name)
    if group is None and name.startswith(MCP_TOOL_PREFIX):
        server = name[len(MCP_TOOL_PREFIX) :].split("__", 1)[0]
        if server:
            return mcp_group(server)
    return group


def excluded_tools(names: Iterable[str], groups: Collection[str]) -> frozenset[str]:
    return frozenset(
        n for n in names if (g := group_of(n)) is not None and g != "core" and g in groups
    )


_GIT_WORDS = (
    r"\bgit\b|\b(?:commit|commits|committed|branch|branches|diff|stage|staged|unstaged|"
    r"merge|rebase|checkout|blame)\b|커밋|브랜치|스테이징|깃|변경\s*사항|변경\s*내역"
)
_WEB_WORDS = (
    r"https?://|\bwww\.|\b(?:url|urls|website|webpage|web page|fetch|download)\b"
    r"|웹|사이트|링크|다운로드"
)
_PLAN_WORDS = (
    r"\b(?:todo|todos|to-do|plan|checklist|step-by-step)\b|할\s*일|계획|체크리스트|단계별"
)
_DELEGATE_WORDS = r"\b(?:delegates?|subagents?|sub-agents?)\b|위임|하위\s*에이전트"

SIGNALS: dict[str, re.Pattern[str]] = {
    "git": re.compile(_GIT_WORDS, re.I),
    "web": re.compile(_WEB_WORDS, re.I),
    "plan-todo": re.compile(_PLAN_WORDS, re.I),
    "delegate": re.compile(_DELEGATE_WORDS, re.I),
}

MENTION_RE = re.compile(r"(?:^|\s)@[\w./~-]")


def request_signals(text: str, *, plan_mode: bool = False) -> frozenset[str]:
    found = {g for g, pattern in SIGNALS.items() if pattern.search(text)}
    if plan_mode:
        found.add("plan-todo")
    return frozenset(found)


def auto_rule_active(*, auto_simple: bool, grade: str, text: str, has_attachments: bool) -> bool:
    return auto_simple and grade == "simple" and not has_attachments and not MENTION_RE.search(text)


def auto_hidden_groups(
    *,
    auto_simple: bool,
    grade: str,
    text: str,
    has_attachments: bool,
    plan_mode: bool,
    keep: Collection[str],
    wanted: Collection[str] | None = None,
) -> set[str]:
    if not auto_rule_active(
        auto_simple=auto_simple, grade=grade, text=text, has_attachments=has_attachments
    ):
        return set()
    if wanted is None:
        wanted = request_signals(text, plan_mode=plan_mode)
    return {g for g in OPTIONAL_GROUPS if g not in wanted and g not in keep}
