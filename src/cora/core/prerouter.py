from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cora.core.decider import Score
from cora.core.shellguard import PathGuard
from cora.core.tools.base import IGNORED_DIRS

SPEC_CAP = 6000
MAX_WALK_FILES = 5000
MAX_FILE_BYTES = 1_000_000
MAX_IDENTIFIERS = 200
SPEC_SUFFIXES = (".md", ".txt")
FEATURE_KEYS = (
    "n_files",
    "n_py_files",
    "total_lines",
    "spec_chars",
    "named_paths",
    "named_missing",
    "scope_files",
)
KNN_KEYS = ("judge", "scope_files", "named_missing")
SIGNALS = ("judge", "scope", "knn")

_PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w-]+/)*[\w-]{2,}\.[A-Za-z][A-Za-z0-9]{0,5})(?![\w/-])")
_SNAKE = r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"
_CAMEL = r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"
_FILE = r"\b[\w-]+\.(?:py|md|txt|toml|json|cfg|ini|yaml|yml|csv)\b"
_TICK = r"`([^`\n]{1,80})`"
_TOKEN = r"[A-Za-z_][A-Za-z0-9_]{3,}"


@dataclass(frozen=True)
class RepoProbe:
    n_files: int
    n_py_files: int
    total_lines: int
    spec_chars: int
    named_paths: tuple[str, ...]
    named_missing: int
    scope_files: int


@dataclass(frozen=True)
class RouteInputs:
    prompt: str
    spec_text: str
    repo: RepoProbe


@dataclass(frozen=True)
class HistoryRow:
    task_id: str
    features: Mapping[str, float]
    cheap_ok: bool


@dataclass(frozen=True)
class PreRoute:
    tier: str
    score: float
    signal: str
    reasons: tuple[str, ...]
    inputs_hash: str


def named_paths(prompt: str) -> tuple[str, ...]:
    found = [m for m in _PATH_RE.findall(prompt) if ".." not in m and not m.startswith("/")]
    return tuple(sorted(set(found)))


def identifiers(spec_text: str) -> tuple[str, ...]:
    found = set(re.findall(_SNAKE, spec_text))
    found |= set(re.findall(_CAMEL, spec_text))
    found |= set(re.findall(_FILE, spec_text))
    for body in re.findall(_TICK, spec_text):
        found.update(re.findall(_TOKEN, body))
    kept = sorted(i for i in found if len(i) >= 4)
    return tuple(kept[:MAX_IDENTIFIERS])


def read_inputs(prompt: str, workspace: Path, *, guard: PathGuard | None = None) -> RouteInputs:
    root = Path(os.path.realpath(workspace))
    guard = guard or PathGuard(root, ())

    def _allowed(p: Path) -> bool:
        try:
            rel = p.relative_to(root).parts
        except ValueError:
            return False
        if any(part.startswith(".") or part in IGNORED_DIRS for part in rel):
            return False
        return guard.check_real(Path(os.path.realpath(p)), write=False) is None

    names = named_paths(prompt)
    missing = sum(1 for n in names if not (root / n).is_file())

    chunks: list[str] = []
    spec_set: set[str] = set()
    for n in names:
        if Path(n).suffix.lower() in SPEC_SUFFIXES and (root / n).is_file() and _allowed(root / n):
            data = (root / n).read_bytes()
            chunks.append(f"=== {n} ===\n{data.decode('utf-8', 'replace')}\n")
            spec_set.add(n)
    spec_text = "".join(chunks)[:SPEC_CAP]
    ids = identifiers(spec_text)

    n_files = 0
    n_py_files = 0
    total_lines = 0
    scope_files = 0
    for dirpath, dirs, files in os.walk(root):
        if n_files >= MAX_WALK_FILES:
            break
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in IGNORED_DIRS)
        for f in sorted(files):
            if n_files >= MAX_WALK_FILES:
                break
            p = Path(dirpath) / f
            if not _allowed(p) or p.is_symlink():
                continue
            n_files += 1
            rel = p.relative_to(root).as_posix()
            if p.suffix == ".py":
                n_py_files += 1
            if p.stat().st_size <= MAX_FILE_BYTES:
                data = p.read_bytes()
                if b"\0" not in data[:8192]:
                    total_lines += data.count(b"\n") + (
                        1 if data and not data.endswith(b"\n") else 0
                    )
                text = data.decode("utf-8", "replace")
                if rel not in spec_set and (p.name in ids or any(i in text for i in ids)):
                    scope_files += 1

    return RouteInputs(
        prompt,
        spec_text,
        RepoProbe(
            n_files,
            n_py_files,
            total_lines,
            len(spec_text),
            names,
            missing,
            scope_files,
        ),
    )


def features(inp: RouteInputs, judge: Score | None = None) -> dict[str, float]:
    repo = inp.repo
    out: dict[str, float] = {
        "n_files": float(repo.n_files),
        "n_py_files": float(repo.n_py_files),
        "total_lines": float(repo.total_lines),
        "spec_chars": float(repo.spec_chars),
        "named_paths": float(len(repo.named_paths)),
        "named_missing": float(repo.named_missing),
        "scope_files": float(repo.scope_files),
    }
    if judge is not None and not judge.fallback_used:
        out["judge"] = float(judge.value)
    return out


def knn_score(
    x: Mapping[str, float],
    history: Sequence[HistoryRow],
    *,
    k: int = 3,
    exclude_task: str,
) -> float | None:
    rows = [r for r in history if r.task_id != exclude_task]
    keys = [c for c in KNN_KEYS if c in x and all(c in r.features for r in rows)]
    if len(rows) < k or not keys:
        return None
    mean: dict[str, float] = {}
    std: dict[str, float] = {}
    for c in keys:
        vals = [r.features[c] for r in rows]
        mu = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))
        mean[c] = mu
        std[c] = sd if sd != 0 else 1.0

    def _z(v: float, c: str) -> float:
        return (v - mean[c]) / std[c]

    xz = {c: _z(x[c], c) for c in keys}
    scored = []
    for r in rows:
        dist = math.sqrt(sum((_z(r.features[c], c) - xz[c]) ** 2 for c in keys))
        scored.append((dist, r.task_id, r))
    scored.sort(key=lambda t: (t[0], t[1]))
    nearest = [t[2] for t in scored[:k]]
    return sum(not r.cheap_ok for r in nearest) / k


def signal_score(
    x: Mapping[str, float],
    *,
    signal: str,
    history: Sequence[HistoryRow] = (),
    task_id: str = "",
) -> float | None:
    if signal == "judge":
        if "judge" not in x:
            raise ValueError("judge feature missing")
        return float(x["judge"])
    if signal == "scope":
        return float(x["scope_files"] + x["named_missing"])
    if signal == "knn":
        return knn_score(x, history, exclude_task=task_id)
    raise ValueError(f"unknown signal {signal!r}")


def inputs_hash(
    x: Mapping[str, float],
    signal: str,
    threshold: float,
    history: Sequence[HistoryRow],
    task_id: str,
) -> str:
    payload = {
        "x": dict(x),
        "signal": signal,
        "threshold": threshold,
        "task_id": task_id,
        "history": [[r.task_id, dict(r.features), r.cheap_ok] for r in history],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def decide(
    x: Mapping[str, float],
    *,
    signal: str,
    threshold: float,
    history: Sequence[HistoryRow] = (),
    task_id: str = "",
) -> PreRoute:
    h = inputs_hash(x, signal, threshold, history, task_id)
    s = signal_score(x, signal=signal, history=history, task_id=task_id)
    if s is None:
        return PreRoute("strong", 1.0, signal, (f"signal={signal}", "knn_insufficient_history"), h)
    tier = "strong" if s >= threshold else "cheap"
    reasons = (f"signal={signal}", f"score={s:.4g}", f"threshold={threshold:.4g}")
    return PreRoute(tier, s, signal, reasons, h)
