"""Policy-level shell confinement (static analysis; not an OS sandbox)."""
from __future__ import annotations

import glob
import os
import re
import shlex
import shutil
import sys
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from importlib import resources
from pathlib import Path
from types import MappingProxyType

HARD = "hard"
SOFT = "soft"
NETWORK = "network"
MAX_COMMAND_CHARS = 10000
MAX_GLOB_MATCHES = 2000
MAX_WRAPPERS = 8
PUNCT = frozenset("();<>|&")
SEPARATORS = frozenset({";", "&&", "||", "|", "|&"})
PIPES = frozenset({"|", "|&"})
WRITE_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>", "<>"})
READ_REDIRECTS = frozenset({"<"})
DUP_REDIRECTS = frozenset({">&", "<&"})
HEREDOCS = frozenset({"<<", "<<-", "<<<"})
REDIRECT_OPS = WRITE_REDIRECTS | READ_REDIRECTS | DUP_REDIRECTS | HEREDOCS
SAFE_DEVICES = frozenset({"/dev/null", "/dev/stdout", "/dev/stderr"})
GLOB_CHARS = "*?["
SHELL_KEYWORDS = frozenset({"if", "then", "else", "elif", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "select", "function", "coproc", "{", "}", "!", "[[", "]]"})
PRIVILEGE = frozenset({"sudo", "doas", "su", "pkexec", "run0"})
NETWORK_TOOLS = frozenset({"curl", "wget", "ssh", "scp", "sftp", "rsync", "nc", "ncat", "netcat",
    "telnet", "ftp", "socat", "aria2c", "http", "https", "xh"})
GIT_NETWORK = frozenset({"clone", "fetch", "pull", "push", "ls-remote", "submodule"})
GIT_READ_SUBS = frozenset({"status", "diff", "log", "show", "branch", "blame", "grep",
    "ls-files", "rev-parse", "describe", "shortlog"})
GIT_EXEC_SUBS = frozenset({"difftool", "mergetool", "filter-branch", "filter-repo"})
INDIRECT = frozenset({"watch", "flock", "chroot", "unshare", "nsenter", "setsid", "script",
    "expect", "at", "batch", "crontab", "fakeroot", "strace", "ltrace", "gdb", "lldb",
    "valgrind", "sg", "newgrp"})
FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0",
    "-fprintf", "-fls"})
READ_ONLY_PROGRAMS = frozenset({"cat", "ls", "grep", "egrep", "fgrep", "rg", "head", "tail",
    "wc", "file", "stat", "diff", "cmp", "tree", "du", "less", "more", "echo", "printf", "pwd",
    "true", "false", "test", "[", "cut", "tr", "nl", "basename", "dirname", "realpath",
    "readlink", "which", "jq"})
TAR_EXEC_PREFIXES = ("--to-command", "--use-compress-program", "--checkpoint-action",
    "--info-script", "--new-volume-script", "--rsh-command", "-I", "-F")
FOLLOW_LINK_SHORT = {"grep": "RS", "egrep": "RS", "fgrep": "RS", "rg": "L", "ls": "LH",
    "du": "LH", "tree": "l"}
FOLLOW_LINK_LONG = frozenset({"--dereference-recursive", "--dereference", "--follow"})
FIND_FOLLOW = frozenset({"-L", "-H", "-follow"})
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.S)
ASSIGN_ALLOW = frozenset({"PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "PYTHONUTF8", "TZ",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "LC_NUMERIC", "TERM", "NO_COLOR",
    "PY_COLORS", "FORCE_COLOR", "COLUMNS", "LINES"})
_SAFE_ASSIGN_VALUE = re.compile(r"[A-Za-z0-9_.,:+@-]*")
_PWD_REF = re.compile(r"\{PWD\}|PWD(?![A-Za-z0-9_])")
_BRACE = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")
_ECHO_PATH = re.compile(r"[*?\[{/~$]|\.\.")
_LITERAL_AFTER_DOLLAR = frozenset({"", " ", "\t", "|", ")", "/", "]", ".", ",", ":", ";", "&",
    ">", "<"})
# No tool-output, cache or config variable may be added here: each one can redirect writes.
ENV_ALLOW = ("PATH", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TERM", "TZ",
    "TMPDIR", "USER", "LOGNAME", "SHELL", "VIRTUAL_ENV", "NO_COLOR", "PYTHONIOENCODING",
    "CORA_MCP_DEPTH")
_SECRET_NAME = re.compile(r"API_?KEY|TOKEN|SECRET|PASSW(?:OR)?D|CREDENTIAL|PRIVATE_KEY|"
    r"ACCESS_KEY", re.I)
CREDENTIAL_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*",
    "id_dsa*", "id_ecdsa*", "id_ed25519*", ".netrc", ".git-credentials", ".pypirc", ".npmrc",
    "credentials", "credentials.json")
CREDENTIAL_EXEMPT = frozenset({".env.example", ".env.sample", ".env.template"})
HOME_PROTECTED = (".ssh", ".config/cora", ".aws", ".gnupg", ".netrc", ".git-credentials",
    ".pypirc", ".npmrc", ".docker", ".kube")
WRITE_PROTECTED_DIRS = frozenset({".git", ".cora"})
WRITE_PROTECTED_FILES = frozenset({"cora.toml", ".envrc"})


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    reason: str


@dataclass
class Segment:
    argv: list[str]
    text: str
    piped: bool
    findings: list[Finding] = field(default_factory=list)


@dataclass
class ShellAnalysis:
    segments: list[Segment]
    findings: list[Finding]


NOVAL = (False, None)
LIT = (True, "lit")
READ = (True, "read")
WRITE = (True, "write")
DENYV = (True, "deny")
DENY0 = (False, "deny")
OptKind = tuple[bool, str | None]


@dataclass(frozen=True)
class ProgramSpec:
    longs: Mapping[str, OptKind]
    shorts: Mapping[str, OptKind]
    positional: str
    subcommands: frozenset[str] = frozenset()
    recursion_shorts: str = ""
    recursion_longs: frozenset[str] = frozenset()
    recurse_value_opts: frozenset[str] = frozenset()
    nodeid: bool = False
    numeric_count: bool = False
    strict_separator: bool = False
    allowed_values: Mapping[str, frozenset[str]] = field(default_factory=dict)


_LS = ProgramSpec(
    longs={"--recursive": NOVAL, "--all": NOVAL, "--almost-all": NOVAL, "--long": NOVAL,
           "--human-readable": NOVAL, "--classify": NOVAL, "--color": LIT, "--sort": LIT,
           "--time": LIT, "--reverse": NOVAL, "--ignore": LIT, "--format": LIT,
           "--group-directories-first": NOVAL, "--directory": NOVAL},
    shorts={**{c: NOVAL for c in "alhFGgontrSdq1iscupkxCmA"},
            "I": LIT, "w": LIT, "T": LIT, "R": NOVAL},
    positional="read", recursion_shorts="R", recursion_longs=frozenset({"--recursive"}))
_CAT = ProgramSpec(
    longs={"--number": NOVAL, "--number-nonblank": NOVAL, "--show-ends": NOVAL,
           "--show-tabs": NOVAL, "--squeeze-blank": NOVAL, "--show-all": NOVAL,
           "--show-nonprinting": NOVAL},
    shorts={c: NOVAL for c in "nbeEstTuvA"}, positional="read")
_GREP = ProgramSpec(
    longs={"--ignore-case": NOVAL, "--invert-match": NOVAL, "--line-number": NOVAL,
           "--count": NOVAL, "--files-with-matches": NOVAL, "--files-without-match": NOVAL,
           "--word-regexp": NOVAL, "--line-regexp": NOVAL, "--only-matching": NOVAL,
           "--extended-regexp": NOVAL, "--fixed-strings": NOVAL, "--basic-regexp": NOVAL,
           "--perl-regexp": NOVAL, "--with-filename": NOVAL, "--no-filename": NOVAL,
           "--no-messages": NOVAL, "--quiet": NOVAL, "--silent": NOVAL, "--text": NOVAL,
           "--null": NOVAL, "--byte-offset": NOVAL, "--color": LIT, "--colour": LIT,
           "--max-count": LIT, "--after-context": LIT, "--before-context": LIT,
           "--context": LIT, "--regexp": LIT, "--file": READ, "--include": LIT,
           "--exclude": LIT, "--exclude-dir": LIT, "--binary-files": LIT, "--devices": LIT,
           "--recursive": NOVAL, "--dereference-recursive": NOVAL, "--directories": LIT},
    shorts={**{c: NOVAL for c in "invclLwxoEFGPHhsqazb"},
            "m": LIT, "A": LIT, "B": LIT, "C": LIT, "e": LIT, "f": READ, "d": LIT,
            "r": NOVAL, "R": NOVAL},
    positional="read", recursion_shorts="rR",
    recursion_longs=frozenset({"--recursive", "--dereference-recursive"}),
    recurse_value_opts=frozenset({"-d", "--directories"}))
_HEAD = ProgramSpec(
    longs={"--bytes": LIT, "--lines": LIT, "--quiet": NOVAL, "--silent": NOVAL,
           "--verbose": NOVAL, "--zero-terminated": NOVAL},
    shorts={"c": LIT, "n": LIT, "q": NOVAL, "v": NOVAL, "z": NOVAL}, positional="read",
    numeric_count=True)
_TAIL = ProgramSpec(
    longs={"--bytes": LIT, "--lines": LIT, "--quiet": NOVAL, "--silent": NOVAL,
           "--verbose": NOVAL, "--zero-terminated": NOVAL, "--follow": NOVAL,
           "--retry": NOVAL, "--pid": LIT, "--sleep-interval": LIT,
           "--max-unchanged-stats": LIT},
    shorts={"c": LIT, "n": LIT, "q": NOVAL, "v": NOVAL, "z": NOVAL, "f": NOVAL, "F": NOVAL},
    positional="read", numeric_count=True)
_WC = ProgramSpec(
    longs={"--bytes": NOVAL, "--chars": NOVAL, "--lines": NOVAL, "--words": NOVAL,
           "--max-line-length": NOVAL, "--files0-from": READ},
    shorts={c: NOVAL for c in "cmlwL"}, positional="read")
_PWD = ProgramSpec(longs={"--logical": NOVAL, "--physical": NOVAL},
                   shorts={"L": NOVAL, "P": NOVAL}, positional="none")
_ECHO = ProgramSpec(longs={}, shorts={"n": NOVAL, "e": NOVAL, "E": NOVAL}, positional="echo")
_PYTEST = ProgramSpec(
    longs={"--override-ini": DENYV, "--config-file": DENYV, "--plugin": DENYV, "--pdb": DENY0,
           "--pdbcls": DENYV, "--no-header": NOVAL, "--no-summary": NOVAL,
           "--collect-only": NOVAL, "--co": NOVAL, "--quiet": NOVAL, "--verbose": NOVAL,
           "--exitfirst": NOVAL, "--maxfail": LIT, "--last-failed": NOVAL,
           "--failed-first": NOVAL, "--new-first": NOVAL, "--lf": NOVAL, "--ff": NOVAL,
           "--nf": NOVAL, "--stepwise": NOVAL, "--sw": NOVAL, "--stepwise-skip": NOVAL,
           "--strict-markers": NOVAL, "--strict-config": NOVAL, "--tb": LIT,
           "--showlocals": NOVAL, "--no-showlocals": NOVAL, "--full-trace": NOVAL,
           "--durations": LIT, "--durations-min": LIT, "--capture": LIT,
           "--show-capture": LIT, "--disable-warnings": NOVAL, "--pythonwarnings": LIT,
           "--runxfail": NOVAL, "--markers": NOVAL, "--fixtures": NOVAL, "--keyword": LIT,
           "--deselect": LIT, "--ignore": READ, "--ignore-glob": LIT, "--pyargs": NOVAL,
           "--import-mode": LIT, "--confcutdir": WRITE, "--rootdir": WRITE,
           "--cache-clear": NOVAL, "--cache-show": LIT, "--version": NOVAL,
           "--basetemp": WRITE, "--junitxml": WRITE, "--junitprefix": LIT,
           "--log-file": WRITE, "--log-level": LIT, "--log-cli-level": LIT, "--color": LIT,
           "--numprocesses": LIT, "--dist": LIT},
    shorts={"x": NOVAL, "q": NOVAL, "v": NOVAL, "s": NOVAL, "l": NOVAL, "k": LIT, "m": LIT,
            "r": LIT, "W": LIT, "n": LIT, "p": DENYV, "c": DENYV, "o": DENYV},
    positional="read", nodeid=True, strict_separator=True,
    allowed_values={"-p": frozenset({"no:cacheprovider", "no:randomly"})})
_RUFF = ProgramSpec(
    longs={"--config": DENYV, "--fix": NOVAL, "--no-fix": NOVAL, "--unsafe-fixes": NOVAL,
           "--no-unsafe-fixes": NOVAL, "--show-fixes": NOVAL, "--no-show-fixes": NOVAL,
           "--diff": NOVAL, "--fix-only": NOVAL, "--no-fix-only": NOVAL,
           "--ignore-noqa": NOVAL, "--output-format": LIT, "--output-file": WRITE,
           "--target-version": LIT, "--preview": NOVAL, "--no-preview": NOVAL,
           "--extension": LIT, "--statistics": NOVAL, "--add-noqa": NOVAL, "--select": LIT,
           "--ignore": LIT, "--extend-select": LIT, "--per-file-ignores": LIT,
           "--extend-per-file-ignores": LIT, "--fixable": LIT, "--unfixable": LIT,
           "--extend-fixable": LIT, "--exclude": LIT, "--extend-exclude": LIT,
           "--respect-gitignore": NOVAL, "--no-respect-gitignore": NOVAL,
           "--force-exclude": NOVAL, "--no-force-exclude": NOVAL, "--no-cache": NOVAL,
           "--cache-dir": WRITE, "--stdin-filename": LIT, "--exit-zero": NOVAL,
           "--exit-non-zero-on-fix": NOVAL, "--exit-non-zero-on-format": NOVAL,
           "--check": NOVAL, "--line-length": LIT, "--range": LIT, "--isolated": NOVAL,
           "--color": LIT, "--verbose": NOVAL, "--quiet": NOVAL, "--silent": NOVAL,
           "--watch": NOVAL, "--version": NOVAL},
    shorts={"n": NOVAL, "e": NOVAL, "w": NOVAL, "v": NOVAL, "q": NOVAL, "s": NOVAL,
            "o": WRITE},
    positional="subcmd", strict_separator=True,
    subcommands=frozenset({"check", "format", "rule", "config", "linter", "analyze", "version"}))
PROGRAM_SPECS: dict[str, ProgramSpec] = {
    "ls": _LS, "cat": _CAT, "grep": _GREP, "egrep": _GREP, "fgrep": _GREP, "head": _HEAD,
    "tail": _TAIL, "wc": _WC, "pwd": _PWD, "echo": _ECHO, "pytest": _PYTEST,
    "py.test": _PYTEST, "ruff": _RUFF,
}

SYNTAX_FLAGS = "flags"            # inline-code flags as whole words
SYNTAX_CLUSTERED = "clustered"    # single-letter flags clustered after one '-'
SYNTAX_SHELL = "shell"            # option letters after '-' or '+'
SYNTAX_ALWAYS = "always"          # every invocation runs program text
SYNTAX_SUBCOMMAND = "subcommand"  # inline code via a subcommand or no arguments
SYNTAX_EXPRESSION = "expression"  # program text checked against a grammar
SYNTAX_RUNNER = "runner"          # runs another program; only listed targets


@dataclass(frozen=True)
class InterpreterSpec:
    # which argument-reading algorithm applies
    syntax: str
    # exact program basenames
    names: frozenset[str] = frozenset()
    # additional program basenames matched by full regex
    name_pattern: re.Pattern[str] | None = None
    # whole flags for flags/expression syntax, letters for clustered/shell syntax
    inline_flags: frozenset[str] = frozenset()
    # compare arguments lowercased
    case_insensitive: bool = False
    # option letter that names a module
    module_flag: str | None = None
    # modules accepted after module_flag
    allowed_modules: frozenset[str] = frozenset()
    # allowed modules that are re-checked by PROGRAM_SPECS
    redispatch_modules: frozenset[str] = frozenset()
    # letters accepted in a cluster without inline code
    option_letters: frozenset[str] = frozenset()
    # shell option letters that read the program from stdin
    stdin_letters: frozenset[str] = frozenset()
    # argument prefixes read as option clusters
    flag_prefixes: tuple[str, ...] = ()
    # running without a script reads code from stdin
    stdin_is_code: bool = False
    # first argument that runs inline code
    inline_subcommands: frozenset[str] = frozenset()
    # no arguments at all runs inline code
    bare_is_inline: bool = False
    # flags that name a script file
    script_flags: frozenset[str] = frozenset()
    # allowed expression forms
    expr_patterns: tuple[re.Pattern[str], ...] = ()
    # separator between expressions
    expr_separator: str = ""
    # characters of an expression quoted in the message
    quote_limit: int = 0
    # file suffix that marks a script
    script_suffix: str | None = None
    # table key reported for a script
    script_key: str | None = None
    # first argument that runs another program
    runner_subcommand: str | None = None
    # programs the runner may run directly
    runner_programs: frozenset[str] = frozenset()
    # interpreter entry whose targets the runner may run
    runner_target: str | None = None
    # event -> (rule id, message template)
    messages: Mapping[str, tuple[str, str]] = field(default_factory=dict)


_ONE_LINER = {"inline": ("confine:one-liner", "'{name}' runs inline code")}
INTERPRETERS: Mapping[str, InterpreterSpec] = MappingProxyType({
    "shell": InterpreterSpec(
        syntax=SYNTAX_SHELL,
        names=frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "fish", "csh", "tcsh",
                         "ash", "busybox"}),
        inline_flags=frozenset({"c"}), stdin_letters=frozenset({"s"}),
        flag_prefixes=("-", "+"), stdin_is_code=True,
        messages={"inline": ("confine:shell-c", "'{name} {arg}' runs a string as a command")},
    ),
    "python": InterpreterSpec(
        syntax=SYNTAX_CLUSTERED,
        name_pattern=re.compile(r"(python|pypy)(\d+(\.\d+)?)?"),
        inline_flags=frozenset({"c"}), module_flag="m",
        allowed_modules=frozenset({"pytest", "unittest", "ruff", "mypy", "py_compile",
                                   "compileall", "doctest"}),
        redispatch_modules=frozenset({"pytest", "ruff"}),
        option_letters=frozenset("BEIsSuqOb"), stdin_is_code=True,
        script_suffix=".py", script_key="python script",
        messages={
            "inline": ("confine:one-liner", "'{name} -{flag}' runs inline code"),
            "module": ("confine:python-module",
                       "'{name} -m {module}' is not an allowed module (allowed: {allowed})"),
            "option": ("confine:python-option",
                       "'{name} {arg}' is not an allowed interpreter option"),
        },
    ),
    "awk": InterpreterSpec(
        syntax=SYNTAX_ALWAYS, names=frozenset({"awk", "gawk", "mawk", "nawk"}),
        messages={"inline": ("confine:one-liner", "'{name}' runs awk programs as code")},
    ),
    "sed": InterpreterSpec(
        syntax=SYNTAX_EXPRESSION, names=frozenset({"sed"}),
        inline_flags=frozenset({"-e", "--expression"}), script_flags=frozenset({"-f", "--file"}),
        expr_patterns=(
            re.compile(r"((\d+|\$)(,(\d+|\$))?|/[^/\n]*/)?[pd]"),
            re.compile(r"s([/|#,:@])((?:\\.|(?!\1).)*)\1((?:\\.|(?!\1).)*)\1[gIip0-9]*"),
        ),
        expr_separator=";", quote_limit=40,
        messages={
            "script": ("confine:one-liner", "sed -f is not allowed"),
            "expression": ("confine:one-liner",
                           "sed expression '{part}' is not allowed "
                           "(only N,Mp / Nd / /re/p / s/a/b/flags)"),
        },
    ),
    "deno": InterpreterSpec(
        syntax=SYNTAX_SUBCOMMAND, names=frozenset({"deno"}),
        inline_subcommands=frozenset({"eval", "repl"}), bare_is_inline=True,
        messages={"inline": ("confine:one-liner", "deno eval and repl run inline code")},
    ),
    "node": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"node", "nodejs"}), case_insensitive=True,
        inline_flags=frozenset({"-e", "--eval", "-p", "--print", "-i", "--interactive", "-r",
                                "--require"}),
        stdin_is_code=True, messages=_ONE_LINER,
    ),
    "bun": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"bun"}), case_insensitive=True,
        inline_flags=frozenset({"-e", "--eval", "-p", "--print"}),
        stdin_is_code=True, messages=_ONE_LINER,
    ),
    "ruby": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"ruby"}), case_insensitive=True,
        inline_flags=frozenset({"-e"}), stdin_is_code=True, messages=_ONE_LINER,
    ),
    "perl": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"perl"}), case_insensitive=True,
        inline_flags=frozenset({"-e", "-E"}), stdin_is_code=True, messages=_ONE_LINER,
    ),
    "php": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"php"}), case_insensitive=True,
        inline_flags=frozenset({"-r", "-a"}), stdin_is_code=True, messages=_ONE_LINER,
    ),
    "lua": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"lua", "luajit"}), case_insensitive=True,
        inline_flags=frozenset({"-e"}), stdin_is_code=True, messages=_ONE_LINER,
    ),
    "rscript": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"Rscript"}), case_insensitive=True,
        inline_flags=frozenset({"-e"}), stdin_is_code=True, messages=_ONE_LINER,
    ),
    "osascript": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"osascript"}), case_insensitive=True,
        inline_flags=frozenset({"-e"}), stdin_is_code=True, messages=_ONE_LINER,
    ),
    "pwsh": InterpreterSpec(
        syntax=SYNTAX_FLAGS, names=frozenset({"pwsh"}), case_insensitive=True,
        inline_flags=frozenset({"-c", "-command", "-encodedcommand"}),
        stdin_is_code=True, messages=_ONE_LINER,
    ),
    "uv": InterpreterSpec(
        syntax=SYNTAX_RUNNER, names=frozenset({"uv"}),
        runner_subcommand="run", runner_programs=frozenset({"pytest", "ruff"}),
        runner_target="python",
        messages={"runner": ("confine:uv-run",
                             "'uv run' only runs pytest, ruff, 'python -m pytest|ruff' "
                             "or a python script file")},
    ),
})


def _name_matches(spec: InterpreterSpec, name: str) -> bool:
    return name in spec.names or (
        spec.name_pattern is not None and spec.name_pattern.fullmatch(name) is not None)


def interpreter_for(name: str) -> InterpreterSpec | None:
    for spec in INTERPRETERS.values():
        if _name_matches(spec, name):
            return spec
    return None


def _say(spec: InterpreterSpec, event: str, soft: Callable[[str, str], None],
         **values: str) -> None:
    rule, template = spec.messages[event]
    soft(rule, template.format(**values))


def _stdin(spec: InterpreterSpec, name: str, stdin_program: Callable[[str], None]) -> None:
    if spec.stdin_is_code:
        stdin_program(name)


def secret_like(name: str) -> bool:
    return _SECRET_NAME.search(name) is not None


def clean_env(source: Mapping[str, str], home: Path, extra: Sequence[str] = (),
              hidden: Collection[str] = ()) -> dict[str, str]:
    env = {k: source[k] for k in (*ENV_ALLOW, *extra)
           if k in source and k not in hidden and not secret_like(k)}
    env["HOME"] = str(home)
    env.setdefault("PATH", os.defpath)
    return env


def package_data_dirs() -> tuple[Path, ...]:
    base = resources.files("cora")
    return (Path(os.path.realpath(str(base / "data"))),
            Path(os.path.realpath(str(base / "bench" / "e2e_tasks"))))


def home_protected() -> tuple[Path, ...]:
    try:
        home = Path.home()
    except RuntimeError:
        return ()
    return tuple(Path(os.path.realpath(home / rel)) for rel in HOME_PROTECTED)


def default_protected(extra: Sequence[Path] = ()) -> tuple[Path, ...]:
    return package_data_dirs() + home_protected() + tuple(
        Path(os.path.realpath(p)) for p in extra)


def sandbox_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def _fold(path: Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.parts)


def _under(path: Path, base: Path) -> bool:
    b = _fold(base)
    return _fold(path)[:len(b)] == b


class PathGuard:
    def __init__(
        self, root: Path, protected: Sequence[Path], *, selftest_writable: bool = False
    ) -> None:
        self.root = Path(os.path.realpath(root))
        self.protected = tuple(protected)
        self.selftest_writable = selftest_writable

    def resolve(self, cand: str) -> Path:
        joined = cand if os.path.isabs(cand) else os.path.join(self.root, cand)
        return Path(os.path.realpath(joined))

    def check_real(self, real: Path, *, write: bool) -> Finding | None:
        for d in self.protected:
            if _under(real, d):
                return Finding("floor:protected-path", HARD, f"protected path: {real}")
        if not _under(real, self.root):
            return Finding("floor:outside-workspace", HARD, f"path outside workspace: {real}")
        name = real.name.casefold()
        exempt = {e.casefold() for e in CREDENTIAL_EXEMPT}
        if name not in exempt and any(
                fnmatchcase(name, p.casefold()) for p in CREDENTIAL_PATTERNS):
            return Finding("floor:credential-file", HARD, f"credential file: {name}")
        parts = _fold(real)[len(_fold(self.root)):]
        if name == "config" and ".git" in parts:
            return Finding("floor:protected-path", HARD, f"protected path: {real}")
        selftest_ok = (self.selftest_writable and len(parts) >= 2
                       and parts[0] == ".cora" and parts[1] == "selftest")
        if write and not selftest_ok and (any(p in WRITE_PROTECTED_DIRS for p in parts)
                                          or (len(parts) == 1 and name in WRITE_PROTECTED_FILES)):
            return Finding("floor:protected-write", HARD, f"writing here is not allowed: {real}")
        return None

    def check(self, cand: str, *, write: bool = False) -> Finding | None:
        if cand in SAFE_DEVICES:
            return None
        if cand.startswith("~"):
            return Finding("confine:tilde", HARD, f"home-relative path is not allowed: {cand}")
        if any(c in cand for c in GLOB_CHARS):
            f = self.check_real(self.resolve(cand), write=write)
            if f is not None:
                return f
            pattern = (cand if os.path.isabs(cand)
                       else os.path.join(glob.escape(str(self.root)), cand))
            for n, match in enumerate(glob.iglob(pattern)):
                if n >= MAX_GLOB_MATCHES:
                    return Finding("confine:glob", HARD, "glob matches too many paths")
                f = self.check_real(Path(os.path.realpath(match)), write=write)
                if f is not None:
                    return f
            return None
        return self.check_real(self.resolve(cand), write=write)


def _sb(path: object) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_profile(guard: PathGuard) -> str:
    tmp = os.path.realpath(tempfile.gettempdir())
    lines = ["(version 1)", "(allow default)", "(deny file-write*)",
             f"(allow file-write* (subpath {_sb(guard.root)}) (subpath {_sb(tmp)}) "
             '(subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/dev"))']
    reads = [p for p in guard.protected if p.exists()]
    if reads:
        lines.append("(deny file-read* " + " ".join(f"(subpath {_sb(p)})" for p in reads) + ")")
    return "\n".join(lines)


def _scan(command: str, pwd_safe: bool) -> tuple[str, str] | None:
    single = double = False
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and not single:
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif not single:
            if ch == "`":
                return ("confine:substitution", "command substitution (backticks) is not allowed")
            if ch == "$":
                nxt = command[i + 1 : i + 2]
                if nxt == "(":
                    return ("confine:substitution", "command substitution '$(...)' is not allowed")
                if pwd_safe and _PWD_REF.match(command, i + 1):
                    i += 1
                    continue
                if nxt == "'" and not double:
                    return ("confine:variable", "ANSI-C quoting ($'...') is not allowed")
                if not (nxt in _LITERAL_AFTER_DOLLAR or (double and nxt == '"')):
                    return ("confine:variable",
                            f"variable expansion '${nxt}...' is not allowed "
                            "(only $PWD is resolved)")
            elif ch == "{" and not double and _BRACE.match(command, i):
                return ("confine:brace", "brace expansion is not allowed")
        i += 1
    return None


def analyze(command: str, guard: PathGuard) -> ShellAnalysis:
    def whole(rule: str, reason: str) -> ShellAnalysis:
        return ShellAnalysis([], [Finding(rule, HARD, reason)])
    if not command.strip():
        return whole("confine:empty", "empty command")
    if len(command) > MAX_COMMAND_CHARS:
        return whole("confine:parse", f"command longer than {MAX_COMMAND_CHARS} characters")
    if any(ch in command for ch in "\n\r\x00"):
        return whole("confine:newline",
                     "multi-line commands are not allowed; run one line at a time")
    if _BRACE.search(command):
        return whole("confine:brace", "brace expansion is not allowed")
    root = str(guard.root)
    pwd_safe = not any(ch.isspace() or ch in "*?[]$'\"\\{}" for ch in root)
    problem = _scan(command, pwd_safe)
    if problem is not None:
        return whole(*problem)
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError as e:
        return whole("confine:parse", f"cannot parse the command ({e})")
    if any(_BRACE.search(t) for t in tokens):
        return whole("confine:brace", "brace expansion is not allowed")
    if pwd_safe:
        tokens = [t.replace("${PWD}", root).replace("$PWD", root) for t in tokens]
    groups: list[tuple[list[str], bool]] = []
    cur: list[str] = []
    piped = False
    last_sep: str | None = None
    for tok in tokens:
        if tok and set(tok) <= PUNCT:
            if tok in SEPARATORS:
                if not cur:
                    return whole("confine:syntax", f"missing command before '{tok}'")
                groups.append((cur, piped))
                cur, piped, last_sep = [], tok in PIPES, tok
                continue
            if tok in REDIRECT_OPS:
                cur.append(tok)
                continue
            if tok == "&":
                return whole("confine:background", "background jobs ('&') are not allowed")
            if tok in ("<(", ">("):
                return whole("confine:substitution", "process substitution is not allowed")
            if "(" in tok or ")" in tok:
                return whole("confine:subshell",
                             "subshells, groups and functions are not allowed")
            return whole("confine:syntax", f"unsupported shell operator '{tok}'")
        cur.append(tok)
    if cur:
        groups.append((cur, piped))
    elif last_sep is not None and last_sep != ";":
        return whole("confine:syntax", f"missing command after '{last_sep}'")
    if not groups:
        return whole("confine:empty", "empty command")
    return ShellAnalysis([_segment(w, p, guard) for w, p in groups], [])


def _candidates(word: str) -> list[str]:
    out = [word]
    if word.startswith("-"):
        if "=" in word:
            out.append(word.split("=", 1)[1])
        elif not word.startswith("--") and len(word) > 2:
            out.append(word[2:])
        if not word.startswith("--"):
            out.extend(word[k:] for k in range(1, len(word))
                       if word[k] in "/~" or word.startswith("..", k))
    elif "=" in word:
        out.append(word.split("=", 1)[1])
    for c in list(out):
        if ":" in c and "://" not in c:
            out.extend(c.split(":"))
    return [c for c in out if c]


def _check_word(word: str, guard: PathGuard, write: bool) -> Finding | None:
    for c in _candidates(word):
        f = guard.check(c, write=write)
        if f is not None:
            return f
    return None


def _program_operand(spec: ProgramSpec, name: str, a: str, index: int, guard: PathGuard,
                     out: list[Finding]) -> None:
    if spec.positional == "none" or a == "-":
        return
    if spec.positional == "echo":
        if _ECHO_PATH.search(a):
            f = _check_word(a, guard, False)
            if f is not None:
                out.append(f)
        return
    if spec.positional == "subcmd" and index == 0:
        if a not in spec.subcommands:
            out.append(Finding("confine:unknown-option", SOFT,
                               f"'{name} {a}' is not an allowed subcommand"))
        return
    cand = a.split("::", 1)[0].split("[", 1)[0] if spec.nodeid else a
    if not cand:
        return
    f = guard.check(cand, write=spec.positional == "subcmd")
    if f is not None:
        out.append(f)


def _program_long(spec: ProgramSpec, name: str, a: str, rest: list[str], guard: PathGuard,
                  out: list[Finding]) -> int:
    optname, eq, val = a.partition("=")
    opt = spec.longs.get(optname)
    if opt is None:
        out.append(Finding("confine:unknown-option", SOFT,
                           f"'{name} {optname}' is not allowed"))
        return 0
    takes, kind = opt
    value, consumed = (val, 0) if eq or not takes else ((rest[0] if rest else ""), 1)
    if optname in spec.recursion_longs or (
            optname in spec.recurse_value_opts and takes and value == "recurse"):
        out.append(Finding("confine:recursion", SOFT,
                           f"recursive '{name}' is not allowed; use the file tools"))
        return consumed
    if kind == "deny":
        out.append(Finding("confine:forbidden-option", SOFT,
                           f"'{name} {optname}' is not allowed"))
        return consumed
    if not takes:
        if eq:
            out.append(Finding("confine:unknown-option", SOFT,
                               f"'{name} {optname}' takes no value"))
        return 0
    if kind == "lit":
        f = _check_word(a if eq else value, guard, False)
    elif value:
        f = guard.check(value, write=kind == "write")
    else:
        f = None
    if f is not None:
        out.append(f)
    return consumed


def _program_cluster(spec: ProgramSpec, name: str, a: str, rest: list[str], guard: PathGuard,
                     out: list[Finding]) -> int:
    for j in range(1, len(a)):
        ch = a[j]
        if ch in spec.recursion_shorts:
            out.append(Finding("confine:recursion", SOFT,
                               f"recursive '{name}' is not allowed; use the file tools"))
            continue
        opt = spec.shorts.get(ch)
        if opt is None:
            out.append(Finding("confine:unknown-option", SOFT,
                               f"'{name} -{ch}' is not allowed"))
            f = _check_word(a, guard, False)
            if f is not None:
                out.append(f)
            return 0
        takes, kind = opt
        if not takes and kind != "deny":
            continue
        attached = a[j + 1:]
        value = attached or (rest[0] if rest and takes else "")
        consumed = 1 if takes and not attached else 0
        if f"-{ch}" in spec.recurse_value_opts and value == "recurse":
            out.append(Finding("confine:recursion", SOFT,
                               f"recursive '{name}' is not allowed; use the file tools"))
            return consumed
        if kind == "deny":
            if value in spec.allowed_values.get(f"-{ch}", frozenset()):
                return consumed
            out.append(Finding("confine:forbidden-option", SOFT,
                               f"'{name} -{ch}' is not allowed"))
            return consumed
        if kind == "lit":
            f = _check_word(a if attached else value, guard, False)
        elif value:
            f = guard.check(value, write=kind == "write")
        else:
            f = None
        if f is not None:
            out.append(f)
        return consumed
    return 0


def _check_program(spec: ProgramSpec, name: str, args: list[str], guard: PathGuard,
                   out: list[Finding]) -> None:
    npos = 0
    positional_only = False
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if not positional_only and a == "--":
            positional_only = True
        elif positional_only and spec.strict_separator and a.startswith("-") and a != "-":
            out.append(Finding("confine:unknown-option", SOFT,
                               f"'{name} {a}' is not allowed after '--'"))
        elif positional_only or not a.startswith("-") or a == "-":
            _program_operand(spec, name, a, npos, guard, out)
            npos += 1
        elif a.startswith("--"):
            i += _program_long(spec, name, a, args[i:], guard, out)
        elif spec.numeric_count and a[1:].isdigit():
            continue
        else:
            i += _program_cluster(spec, name, a, args[i:], guard, out)


def _segment(words: list[str], piped: bool, guard: PathGuard) -> Segment:
    findings: list[Finding] = []
    argv: list[str] = []
    last_word = -2
    i = 0
    while i < len(words):
        w = words[i]
        if w in REDIRECT_OPS:
            if argv and last_word == i - 1 and argv[-1].isdigit():
                argv.pop()
            target = words[i + 1] if i + 1 < len(words) else None
            if target is None or target in REDIRECT_OPS:
                findings.append(Finding("confine:syntax", HARD, f"'{w}' needs a target"))
                i += 1
                continue
            if w in HEREDOCS:
                findings.append(Finding("confine:heredoc", HARD,
                                        "here-documents and here-strings are not allowed"))
            elif not (w in DUP_REDIRECTS and (target.isdigit() or target == "-")):
                f = guard.check(target, write=w not in READ_REDIRECTS and w != "<&")
                if f is not None:
                    findings.append(f)
            i += 2
            continue
        argv.append(w)
        last_word = i
        i += 1
    assignments: list[str] = []
    while argv and _ASSIGN.fullmatch(argv[0]):
        assignments.append(argv.pop(0))
    argv = _unwrap(argv, assignments, findings)
    env_findings: list[Finding] = []
    for a in assignments:
        var, value = a.split("=", 1)
        if var not in ASSIGN_ALLOW or secret_like(var) or not _SAFE_ASSIGN_VALUE.fullmatch(value):
            env_findings.append(Finding("confine:env-assign", HARD,
                                        f"setting {var} in the command is not allowed"))
        f = _check_word(value, guard, False)
        if f is not None:
            findings.append(f)
    if not argv:
        findings.append(Finding("confine:empty", HARD, "this part of the command runs no program"))
        findings.extend(env_findings)
        return Segment([], "", piped, findings)
    _dispatch(argv, piped, guard, findings)
    findings.extend(env_findings)
    return Segment(argv, " ".join(argv), piped, findings)


def _dispatch(argv: list[str], piped: bool, guard: PathGuard, findings: list[Finding]) -> None:
    name = os.path.basename(argv[0])
    if "/" in argv[0]:
        f = guard.check(argv[0], write=False)
        if f is not None:
            findings.append(f)
    _structural(name, argv[1:], piped, findings)
    interp = interpreter_for(name)
    if (interp is not None and interp.syntax == SYNTAX_RUNNER
            and argv[1:2] == [interp.runner_subcommand]):
        inner = argv[2:]
        if _runner_target(interp, inner):
            _dispatch(inner, piped, guard, findings)
        else:
            rule, message = interp.messages["runner"]
            findings.append(Finding(rule, SOFT, message))
        return
    sub = _git_subcommand(argv[1:])[1] if name == "git" else ""
    spec = PROGRAM_SPECS.get(name)
    if spec is not None:
        _check_program(spec, name, argv[1:], guard, findings)
    else:
        write = not (name in READ_ONLY_PROGRAMS or sub in GIT_READ_SUBS)
        for w in argv[1:]:
            f = _check_word(w, guard, write)
            if f is not None:
                findings.append(f)
                break
        if interp is not None and interp.redispatch_modules:
            mod = _module_of(interp, argv[1:])
            if mod is not None and mod[0] in interp.redispatch_modules:
                _check_program(PROGRAM_SPECS[mod[0]], mod[0], mod[1], guard, findings)


def _runner_target(spec: InterpreterSpec, inner: list[str]) -> bool:
    if not inner:
        return False
    if inner[0] in spec.runner_programs:
        return True
    assert spec.runner_target is not None
    target = INTERPRETERS[spec.runner_target]
    if "/" in inner[0] or not _name_matches(target, inner[0]) or len(inner) < 2:
        return False
    assert target.module_flag is not None and target.script_suffix is not None
    if (len(inner) >= 3 and inner[1] == "-" + target.module_flag
            and inner[2] in target.redispatch_modules):
        return True
    return inner[1].endswith(target.script_suffix) and not inner[1].startswith("-")


def table_key(argv: list[str]) -> str | None:
    if not argv:
        return None
    name = os.path.basename(argv[0])
    interp = interpreter_for(name)
    if (interp is not None and interp.syntax == SYNTAX_RUNNER
            and argv[1:2] == [interp.runner_subcommand]):
        inner = argv[2:]
        return table_key(inner) if _runner_target(interp, inner) else None
    if interp is not None and interp.script_key is not None:
        assert interp.script_suffix is not None
        mod = _module_of(interp, argv[1:])
        if mod is not None:
            return mod[0] if mod[0] in PROGRAM_SPECS else None
        if len(argv) > 1 and argv[1].endswith(interp.script_suffix) and not argv[1].startswith("-"):
            return interp.script_key
        return None
    if name == "git":
        sub = _git_subcommand(argv[1:])[1]
        return f"git {sub}" if sub in GIT_READ_SUBS else None
    return name if name in PROGRAM_SPECS else None


def _unwrap(argv: list[str], assignments: list[str], out: list[Finding]) -> list[str]:
    for _ in range(MAX_WRAPPERS):
        if not argv:
            return argv
        name = os.path.basename(argv[0])
        rest = argv[1:]
        if name == "env":
            j = 0
            while j < len(rest):
                a = rest[j]
                if a in ("-i", "-", "--ignore-environment", "-0", "--null"):
                    j += 1
                    continue
                if a in ("-u", "--unset"):
                    j += 2
                    continue
                if a.startswith("-u") or a.startswith("--unset="):
                    j += 1
                    continue
                if a.startswith("-"):
                    out.append(Finding("confine:wrapper", SOFT,
                                       f"env option '{a}' is not allowed"))
                    return argv
                if _ASSIGN.fullmatch(a):
                    assignments.append(a)
                    j += 1
                    continue
                break
            if j >= len(rest):
                return argv
            argv = rest[j:]
            continue
        if name in ("nohup", "builtin", "exec"):
            argv = rest
            continue
        if name == "command":
            if rest[:1] == ["-p"]:
                argv = rest[1:]
                continue
            if rest and rest[0].startswith("-"):
                return argv
            argv = rest
            continue
        if name == "time":
            argv = rest[1:] if rest[:1] == ["-p"] else rest
            continue
        if name == "nice":
            if rest[:1] in (["-n"], ["--adjustment"]):
                argv = rest[2:]
            elif rest and (rest[0].startswith(("-n", "--adjustment="))
                           or (rest[0].startswith("-") and rest[0][1:].isdigit())):
                argv = rest[1:]
            else:
                argv = rest
            continue
        if name == "timeout":
            j = 0
            while j < len(rest) and rest[j].startswith("-"):
                j += 2 if rest[j] in ("-s", "-k", "--signal", "--kill-after") else 1
            argv = rest[j + 1:]
            continue
        if name == "stdbuf":
            j = 0
            while j < len(rest) and rest[j].startswith("-"):
                j += 2 if rest[j] in ("-i", "-o", "-e") else 1
            argv = rest[j:]
            continue
        return argv
    out.append(Finding("confine:wrapper", HARD, "too many nested wrapper commands"))
    return argv


def _git_subcommand(args: list[str]) -> tuple[int, str]:
    for i, a in enumerate(args):
        if not a.startswith("-"):
            return i, a
    return len(args), ""


def _follows_links(name: str, args: list[str]) -> bool:
    if name == "find":
        return any(a in FIND_FOLLOW for a in args)
    letters = FOLLOW_LINK_SHORT.get(name)
    if letters is None:
        return False
    return any(a in FOLLOW_LINK_LONG or (a.startswith("-") and not a.startswith("--")
               and any(c in letters for c in a[1:])) for a in args)


def _structural(name: str, args: list[str], piped: bool, out: list[Finding]) -> None:
    def soft(rule: str, reason: str) -> None:
        out.append(Finding(rule, SOFT, reason))

    def stdin_program(what: str) -> None:
        if piped:
            out.append(Finding("floor:pipe-exec", HARD,
                               f"{what} would run code read from a pipe"))
        else:
            soft("confine:interpreter-stdin", f"{what} without a script file is not allowed")

    if name in PRIVILEGE:
        out.append(Finding("floor:privilege", HARD, f"'{name}' runs commands as another user"))
        return
    if name in SHELL_KEYWORDS:
        out.append(Finding("confine:syntax", HARD, f"shell keyword '{name}' is not allowed"))
        return
    if any(c in name for c in GLOB_CHARS):
        out.append(Finding("confine:glob", HARD, "glob characters in the program name"))
        return
    if name not in PROGRAM_SPECS and _follows_links(name, args):
        soft("confine:follow-links", f"'{name}' follows symbolic links out of the workspace")
    if name in ("eval", "alias", "trap"):
        soft("confine:eval", f"'{name}' runs code given as text")
        return
    if name in ("source", "."):
        soft("confine:source", f"'{name}' runs commands from a file in this shell")
        return
    if name in ("cd", "pushd", "popd", "chdir"):
        soft("confine:cd", f"'{name}' changes the working directory")
        return
    if name in ("xargs", "parallel"):
        soft("confine:xargs", f"'{name}' runs programs built from its input")
        return
    if name in INDIRECT:
        soft("confine:indirect", f"'{name}' runs another program")
        return
    if name in NETWORK_TOOLS:
        out.append(Finding("floor:network", NETWORK, f"'{name}' uses the network"))
        return
    interp = interpreter_for(name)
    if interp is not None and _check_interpreter(interp, name, args, stdin_program, soft):
        return
    if name == "find" and any(a in FIND_EXEC for a in args):
        soft("confine:find-exec", "find actions that run or delete files are not allowed")
        return
    if name == "rg" and any(a == "--pre" or a.startswith("--pre=") for a in args):
        soft("confine:indirect", "rg --pre runs another program")
        return
    if name == "tar":
        _check_tar(args, soft)
        return
    if name == "git":
        _check_git(args, soft, out)
        return
    if name in ("chmod", "chown", "chgrp") and any(
            a == "--recursive" or (a.startswith("-") and not a.startswith("--") and "R" in a)
            for a in args):
        out.append(Finding("floor:chmod-recursive", HARD, f"recursive '{name}' is not allowed"))


def _check_interpreter(spec: InterpreterSpec, name: str, args: list[str],
                       stdin_program: Callable[[str], None],
                       soft: Callable[[str, str], None]) -> bool:
    if spec.syntax == SYNTAX_SHELL:
        _check_shell_options(spec, name, args, stdin_program, soft)
        return True
    if spec.syntax == SYNTAX_CLUSTERED:
        _check_clustered(spec, name, args, stdin_program, soft)
        return True
    if spec.syntax == SYNTAX_ALWAYS:
        _say(spec, "inline", soft, name=name)
        return True
    if spec.syntax == SYNTAX_EXPRESSION:
        _check_expression(spec, args, soft)
        return True
    if spec.syntax == SYNTAX_SUBCOMMAND:
        if (spec.bare_is_inline and not args) or (args and args[0] in spec.inline_subcommands):
            _say(spec, "inline", soft, name=name)
            return True
        return False
    if spec.syntax == SYNTAX_FLAGS:
        norm = str.lower if spec.case_insensitive else str
        long_flags = tuple(f + "=" for f in spec.inline_flags if f.startswith("--"))
        if any(norm(a) in spec.inline_flags or norm(a).startswith(long_flags) for a in args):
            _say(spec, "inline", soft, name=name)
            return True
        if all(a.startswith("-") for a in args):
            _stdin(spec, name, stdin_program)
            return True
        return False
    if spec.syntax == SYNTAX_RUNNER:
        return False
    raise ValueError(f"unknown interpreter syntax {spec.syntax!r}")


def _check_shell_options(spec: InterpreterSpec, name: str, args: list[str],
                         stdin_program: Callable[[str], None],
                         soft: Callable[[str, str], None]) -> None:
    for a in args:
        if a == "-":
            _stdin(spec, name, stdin_program)
            return
        if a.startswith("--"):
            continue
        if a[:1] in spec.flag_prefixes and len(a) > 1:
            if any(ch in a[1:] for ch in spec.inline_flags):
                _say(spec, "inline", soft, name=name, arg=a)
                return
            if any(ch in a[1:] for ch in spec.stdin_letters):
                _stdin(spec, name, stdin_program)
                return
            continue
        return
    _stdin(spec, name, stdin_program)


def _check_clustered(spec: InterpreterSpec, name: str, args: list[str],
                     stdin_program: Callable[[str], None],
                     soft: Callable[[str, str], None]) -> None:
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-":
            _stdin(spec, name, stdin_program)
            return
        if a == "--":
            if i + 1 < len(args):
                return
            break
        if not a.startswith("-") or len(a) == 1:
            return
        if a.startswith("--"):
            _say(spec, "option", soft, name=name, arg=a)
            return
        flags = a[1:]
        for k, ch in enumerate(flags):
            if ch in spec.inline_flags:
                _say(spec, "inline", soft, name=name, flag=ch)
                return
            if ch == spec.module_flag:
                module = flags[k + 1:] or (args[i + 1] if i + 1 < len(args) else "")
                if module not in spec.allowed_modules:
                    _say(spec, "module", soft, name=name, module=module,
                         allowed=", ".join(sorted(spec.allowed_modules)))
                return
            if ch not in spec.option_letters:
                _say(spec, "option", soft, name=name, arg=a)
                return
        i += 1
    _stdin(spec, name, stdin_program)


def _module_of(spec: InterpreterSpec, args: list[str]) -> tuple[str, list[str]] | None:
    for i, a in enumerate(args):
        if a in ("-", "--") or not a.startswith("-") or a.startswith("--"):
            return None
        flags = a[1:]
        for k, ch in enumerate(flags):
            if ch == spec.module_flag:
                if flags[k + 1:]:
                    return flags[k + 1:], args[i + 1:]
                return (args[i + 1], args[i + 2:]) if i + 1 < len(args) else None
            if ch not in spec.option_letters:
                return None
    return None


def _check_expression(spec: InterpreterSpec, args: list[str],
                      soft: Callable[[str, str], None]) -> None:
    script_long = tuple(f + "=" for f in spec.script_flags if f.startswith("--"))
    script_letters = [f[1] for f in spec.script_flags if not f.startswith("--")]
    expr_long = tuple(f + "=" for f in spec.inline_flags if f.startswith("--"))
    expr_letters = [f[1] for f in spec.inline_flags if not f.startswith("--")]
    exprs: list[str] = []
    operands: list[str] = []
    explicit = False
    i = 0
    while i < len(args):
        a = args[i]
        short = a.startswith("-") and not a.startswith("--")
        if a in spec.script_flags or a.startswith(script_long) or (
                short and any(c in a for c in script_letters)):
            _say(spec, "script", soft)
            return
        if a in spec.inline_flags or (short and any(c in a for c in expr_letters)):
            exprs.append(args[i + 1] if i + 1 < len(args) else "")
            explicit = True
            i += 2
            continue
        if a.startswith(expr_long):
            exprs.append(a.split("=", 1)[1])
            explicit = True
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            i += 1
            continue
        operands.append(a)
        i += 1
    if not explicit:
        exprs = operands[:1]
    for expr in exprs:
        for part in expr.split(spec.expr_separator):
            part = part.strip()
            if part and not any(p.fullmatch(part) for p in spec.expr_patterns):
                _say(spec, "expression", soft, part=part[:spec.quote_limit])
                return


def _check_tar(args: list[str], soft: Callable[[str, str], None]) -> None:
    for k, a in enumerate(args):
        if a.startswith(TAR_EXEC_PREFIXES):
            soft("confine:tar-exec", f"tar option '{a}' runs another program")
            return
        if (a == "-C" or a.startswith("--directory")
                or (a.startswith("-") and not a.startswith("--") and "C" in a)
                or (k == 0 and not a.startswith("-") and a.isalpha() and "C" in a)):
            soft("confine:tar-C", "tar -C changes the directory")
            return


def _pager_open(a: str) -> bool:
    if a.startswith("-O"):
        return True
    if a.startswith("--"):
        opt = a.split("=", 1)[0]
        return len(opt) >= 3 and (
            "--open-files-in-pager".startswith(opt) or "--open".startswith(opt))
    return a.startswith("-") and "O" in a[1:]


def _check_git(args: list[str], soft: Callable[[str, str], None], out: list[Finding]) -> None:
    if any(a.startswith("--output") for a in args):
        out.append(Finding("floor:git-output", HARD,
                           "git --output writes files and is not allowed"))
        return
    i, sub = _git_subcommand(args)
    for a in args[:i]:
        if a.startswith("-C"):
            soft("confine:git-C", "git -C changes the directory")
            return
        if a == "-c" or a.startswith(("-c", "--git-dir", "--work-tree", "--exec-path",
                                      "--namespace", "--config-env", "--super-prefix")):
            soft("confine:git-config", "git configuration overrides are not allowed")
            return
    rest = args[i + 1:]
    if any(_pager_open(a) for a in args):
        soft("confine:git-exec", "git can run a pager program for matched files")
        return
    if sub in GIT_NETWORK:
        out.append(Finding("floor:network", NETWORK, f"git {sub} uses the network"))
        return
    if sub == "config" and not any(
            a in ("--get", "--get-all", "--get-regexp", "--list", "-l") for a in rest):
        soft("confine:git-config", "git config can change repository settings")
        return
    if (sub in GIT_EXEC_SUBS
            or (sub == "rebase" and any(a in ("-x", "--exec") or a.startswith("--exec=")
                                        for a in rest))
            or (sub == "bisect" and rest[:1] == ["run"])
            or any(a.startswith(("--upload-pack", "--receive-pack", "--exec=")) for a in rest)):
        soft("confine:git-exec", f"git {sub} can run other programs")
