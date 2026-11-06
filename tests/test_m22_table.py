from __future__ import annotations

import dataclasses
import os
import re
from collections.abc import Callable

import pytest

import m22_golden
from cora.core import shellguard
from cora.core.shellguard import INTERPRETERS, InterpreterSpec

HEADER, RECORDS = m22_golden.load_golden()

HITS: dict[str, list[tuple[str, list[str]]]] = {key: [] for key in INTERPRETERS}
for _rec in RECORDS:
    for _seg in m22_golden.segments(_rec["command"]):
        for _i in range(len(_seg)):
            _name = os.path.basename(_seg[_i])
            _spec = shellguard.interpreter_for(_name)
            if _spec is not None:
                _key = next(k for k, v in INTERPRETERS.items() if v is _spec)
                HITS[_key].append((_name, _seg[_i + 1 :]))


def _reasons() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for rec in RECORDS:
        for rule, _severity, reason in rec["analyze"]["findings"]:
            out.add((rule, reason))
        for seg in rec["analyze"]["segments"]:
            for rule, _severity, reason in seg["findings"]:
                out.add((rule, reason))
        for mode in m22_golden.MODES:
            _decision, rule, reason, _hard = rec[mode]
            out.add((rule, reason))
    return out


REASONS = _reasons()
SHELLGUARD_GONE = (
    "SHELLS",
    "AWKS",
    "PY_RE",
    "PY_MODULES_OK",
    "PY_FLAG_CHARS",
    "ONE_LINER_FLAGS",
    "SED_PRINT",
    "SED_SUB",
    "_NODE",
    "_python_module",
    "_check_python",
    "_check_sed",
    "_uv_run_target",
)


def _args(hits: list[tuple[str, list[str]]]) -> list[str]:
    return [arg for _name, args in hits for arg in args]


def _short(arg: str) -> bool:
    return arg.startswith("-") and not arg.startswith("--")


def _mod(spec: InterpreterSpec, args: list[str], module: str) -> bool:
    flag = "-" + spec.module_flag
    return any(
        args[j] == flag and args[j + 1 : j + 2] == [module] or args[j] == flag + module
        for j in range(len(args))
    )


def _mod_hit(spec: InterpreterSpec, hits: list[tuple[str, list[str]]], module: str) -> bool:
    return any(_mod(spec, args, module) for _name, args in hits)


def _matches(spec: InterpreterSpec, name: str) -> bool:
    return name in spec.names or (
        spec.name_pattern is not None and spec.name_pattern.fullmatch(name) is not None
    )


def _parts(spec: InterpreterSpec, hits: list[tuple[str, list[str]]]) -> list[str]:
    return [
        part.strip() for arg in _args(hits) for part in arg.split(spec.expr_separator)
    ]


def _p_names(spec, hits, records):
    names = {name for name, _args in hits}
    return all(n in names for n in spec.names)


def _p_name_pattern(spec, hits, records):
    names = [name for name, _args in hits]
    return any(re.search(r"\d", n) for n in names) and any(
        not re.search(r"\d", n) for n in names
    )


def _p_inline_flags(spec, hits, records):
    args = _args(hits)
    if spec.syntax == shellguard.SYNTAX_FLAGS:
        return all(
            any(
                a.lower() == f.lower()
                or (f.startswith("--") and a.lower().startswith(f.lower() + "="))
                for a in args
            )
            for f in spec.inline_flags
        )
    if spec.syntax == shellguard.SYNTAX_EXPRESSION:
        return all(
            any(a == f or a.startswith(f + "=") for a in args) for f in spec.inline_flags
        )
    return all(
        any(a[:1] in ("-", "+") and not a.startswith("--") and letter in a[1:] for a in args)
        for letter in spec.inline_flags
    )


def _p_case_insensitive(spec, hits, records):
    return any(a != a.lower() and a.lower() in spec.inline_flags for a in _args(hits))


def _p_module_flag(spec, hits, records):
    return any(_short(a) and spec.module_flag in a for a in _args(hits))


def _p_allowed_modules(spec, hits, records):
    return all(_mod_hit(spec, hits, m) for m in spec.allowed_modules)


def _p_redispatch_modules(spec, hits, records):
    return all(_mod_hit(spec, hits, m) for m in spec.redispatch_modules)


def _p_option_letters(spec, hits, records):
    args = _args(hits)
    return all(any(_short(a) and ch in a for a in args) for ch in spec.option_letters)


def _p_stdin_letters(spec, hits, records):
    args = _args(hits)
    prefixes = tuple(spec.flag_prefixes)
    return all(
        any(a.startswith(prefixes) and ch in a for a in args) for ch in spec.stdin_letters
    )


def _p_flag_prefixes(spec, hits, records):
    args = _args(hits)
    return all(
        any(len(a) >= 2 and not a.startswith("--") and a.startswith(p) for a in args)
        for p in spec.flag_prefixes
    )


def _p_stdin_is_code(spec, hits, records):
    return any(
        not args or "-" in args or all(a.startswith("-") for a in args)
        for _name, args in hits
    )


def _p_inline_subcommands(spec, hits, records):
    return all(
        any(args[:1] == [sc] for _name, args in hits) for sc in spec.inline_subcommands
    )


def _p_bare_is_inline(spec, hits, records):
    return any(not args for _name, args in hits)


def _p_script_flags(spec, hits, records):
    args = _args(hits)
    return all(
        any(a == f or a.startswith(f + "=") for a in args) for f in spec.script_flags
    )


def _p_expr_patterns(spec, hits, records):
    parts = _parts(spec, hits)
    return all(any(p.fullmatch(part) for part in parts) for p in spec.expr_patterns)


def _p_expr_separator(spec, hits, records):
    return any(spec.expr_separator in a for a in _args(hits))


def _p_quote_limit(spec, hits, records):
    return any(len(part) > spec.quote_limit for part in _parts(spec, hits))


def _p_script_suffix(spec, hits, records):
    return any(bool(args) and args[0].endswith(spec.script_suffix) for _name, args in hits)


def _p_script_key(spec, hits, records):
    return any(
        seg["table_key"] == spec.script_key
        for rec in records
        for seg in rec["analyze"]["segments"]
    )


def _p_runner_subcommand(spec, hits, records):
    return any(args[:1] == [spec.runner_subcommand] for _name, args in hits)


def _p_runner_programs(spec, hits, records):
    return all(
        any(args[:2] == [spec.runner_subcommand, p] for _name, args in hits)
        for p in spec.runner_programs
    )


def _p_runner_target(spec, hits, records):
    target = INTERPRETERS[spec.runner_target]
    return any(
        args[:1] == [spec.runner_subcommand] and len(args) > 1 and _matches(target, args[1])
        for _name, args in hits
    )


def _p_cluster_inline_letters(spec, hits, records):
    args = _args(hits)
    return all(
        any(_short(a) and len(a) > 2 and ch in a[1:] for a in args)
        for ch in spec.cluster_inline_letters
    )


def _p_cluster_value_letters(spec, hits, records):
    args = _args(hits)
    return all(
        any(_short(a) and len(a) > 2 and a[1] == ch for a in args)
        for ch in spec.cluster_value_letters
    )


def _p_inline_abbreviations(spec, hits, records):
    args = [a.lower() for a in _args(hits)]
    return all(
        any(a.startswith(short) and full.startswith(a) and a not in spec.inline_flags for a in args)
        for full, short in spec.inline_abbreviations.items()
    )


def _p_options_before_subcommand(spec, hits, records):
    return any(
        bool(args)
        and args[0].startswith("-")
        and any(x in spec.inline_subcommands for x in args[1:])
        for _name, args in hits
    )


def _p_subcommand_value_options(spec, hits, records):
    return all(
        any(opt in args for _name, args in hits) for opt in spec.subcommand_value_options
    )


def _p_multicall_names(spec, hits, records):
    return all(
        any(name == m and bool(args) and _matches(spec, args[0]) for name, args in hits)
        for m in spec.multicall_names
    )


PREDICATES: dict[str, Callable[[InterpreterSpec, list, list], bool]] = {
    "names": _p_names,
    "name_pattern": _p_name_pattern,
    "inline_flags": _p_inline_flags,
    "case_insensitive": _p_case_insensitive,
    "module_flag": _p_module_flag,
    "allowed_modules": _p_allowed_modules,
    "redispatch_modules": _p_redispatch_modules,
    "option_letters": _p_option_letters,
    "stdin_letters": _p_stdin_letters,
    "flag_prefixes": _p_flag_prefixes,
    "stdin_is_code": _p_stdin_is_code,
    "inline_subcommands": _p_inline_subcommands,
    "bare_is_inline": _p_bare_is_inline,
    "script_flags": _p_script_flags,
    "expr_patterns": _p_expr_patterns,
    "expr_separator": _p_expr_separator,
    "quote_limit": _p_quote_limit,
    "script_suffix": _p_script_suffix,
    "script_key": _p_script_key,
    "runner_subcommand": _p_runner_subcommand,
    "runner_programs": _p_runner_programs,
    "runner_target": _p_runner_target,
    "cluster_inline_letters": _p_cluster_inline_letters,
    "cluster_value_letters": _p_cluster_value_letters,
    "inline_abbreviations": _p_inline_abbreviations,
    "options_before_subcommand": _p_options_before_subcommand,
    "subcommand_value_options": _p_subcommand_value_options,
    "multicall_names": _p_multicall_names,
}


def _non_default_fields() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, spec in INTERPRETERS.items():
        for f in dataclasses.fields(InterpreterSpec):
            if f.name in ("syntax", "messages"):
                continue
            if f.default_factory is not dataclasses.MISSING:
                default = f.default_factory()
            else:
                default = f.default
            if getattr(spec, f.name) != default:
                out.append((key, f.name))
    return out


def _message_regex(template: str) -> re.Pattern[str]:
    pieces = re.split(r"(\{\w+\})", template)
    body = "".join(".*" if re.fullmatch(r"\{\w+\}", p) else re.escape(p) for p in pieces)
    return re.compile(body, re.S)


def _message_cases() -> list[tuple[str, str]]:
    return [(key, event) for key, spec in INTERPRETERS.items() for event in spec.messages]


def test_every_field_has_a_rule():
    fields = {f.name for f in dataclasses.fields(InterpreterSpec)} - {"syntax", "messages"}
    assert fields == set(PREDICATES)


@pytest.mark.parametrize("key", list(INTERPRETERS))
def test_every_entry_hit(key):
    assert HITS[key], f"no command in the golden corpus reaches entry {key!r}"


@pytest.mark.parametrize("key,field", _non_default_fields())
def test_entry_fields_exercised(key, field):
    spec = INTERPRETERS[key]
    assert PREDICATES[field](spec, HITS[key], RECORDS), f"{key}.{field} not exercised"


@pytest.mark.parametrize("key,event", _message_cases())
def test_messages_exercised(key, event):
    rule, template = INTERPRETERS[key].messages[event]
    regex = _message_regex(template)
    assert any(
        r == rule and isinstance(reason, str) and regex.fullmatch(reason) is not None
        for r, reason in REASONS
    ), f"{key}.{event} message not produced by any golden record"


def test_entries_disjoint():
    names = {n for spec in INTERPRETERS.values() for n in spec.names}
    names |= {name for hits in HITS.values() for name, _args in hits}
    for name in names:
        matched = [k for k, spec in INTERPRETERS.items() if _matches(spec, name)]
        assert len(matched) <= 1, f"{name!r} matches several entries: {matched}"


def test_table_is_single_source():
    present = [n for n in SHELLGUARD_GONE if hasattr(shellguard, n)]
    assert not present, f"table data still lives in shellguard: {present}"
