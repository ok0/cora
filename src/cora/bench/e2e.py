from __future__ import annotations

import contextlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from cora.core.errors import ConfigError

E2E_PREFIX = "e2e_"
DIFFICULTIES = ("easy", "medium", "hard")
GRADER_DIRNAME = ".cora_grader"
REQUIREMENTS_NAME = "REQUIREMENTS.md"
GRADER_TIMEOUT_CAP_S = 120.0
MAX_GRADER_OUTPUT_BYTES = 64 * 1024
MAX_CHECKS = 200
GRADER_ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
REQUIRED_FIELDS = (
    "id",
    "title",
    "difficulty",
    "requirements",
    "template",
    "required_files",
    "limits.wall_s",
    "limits.cost_usd",
    "limits.max_iterations",
    "grader.dir",
    "grader.entry",
    "grader.timeout_s",
    "reference.dir",
)
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")
_MISSING = object()


def e2e_tasks_dir() -> Path:
    return Path(str(resources.files("cora.bench") / "e2e_tasks"))


@dataclass(frozen=True)
class E2ETask:
    id: str
    title: str
    difficulty: str
    root: Path
    requirements_path: Path
    template_dir: Path
    required_files: tuple[str, ...]
    wall_s: float
    cost_usd: float
    max_iterations: int
    grader_dir: Path
    grader_entry: str
    grader_timeout_s: float
    grader_visibility: str
    reference_dir: Path
    reference_delete: tuple[str, ...] = ()
    kind: str = "e2e"
    estimated_minutes: float | None = None


def _get(data: dict, dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _positive(value: Any) -> bool:
    return _is_number(value) and value > 0


def _rel_ok(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _parse_task(task_dir: Path, errors: list[str]) -> E2ETask | None:
    toml_path = task_dir / "task.toml"
    if not toml_path.is_file():
        errors.append(f"e2e task '{task_dir.name}': missing task.toml")
        return None
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        errors.append(f"e2e task '{task_dir.name}': invalid task.toml: {e}")
        return None
    raw_id = data.get("id")
    label = raw_id if isinstance(raw_id, str) and raw_id else task_dir.name
    start = len(errors)

    def bad(problem: str) -> None:
        errors.append(f"e2e task '{label}': {problem}")

    missing = [f for f in REQUIRED_FIELDS if _get(data, f) is _MISSING]
    for dotted in missing:
        bad(f"missing required field '{dotted}'")
    if missing:
        return None
    tid = _get(data, "id")
    if not isinstance(tid, str) or not tid.startswith(E2E_PREFIX):
        bad("id must start with 'e2e_'")
    title = _get(data, "title")
    if not isinstance(title, str) or not title.strip():
        bad("field 'title' must be a non-empty string")
    difficulty = _get(data, "difficulty")
    if difficulty not in DIFFICULTIES:
        bad("difficulty must be one of easy, medium, hard")
    required_files = _get(data, "required_files")
    if not (
        isinstance(required_files, list)
        and required_files
        and all(_rel_ok(f) for f in required_files)
    ):
        bad("required_files must be a non-empty list of relative paths")
    wall_s = _get(data, "limits.wall_s")
    if not _positive(wall_s):
        bad("limits.wall_s must be > 0")
    cost_usd = _get(data, "limits.cost_usd")
    if not _positive(cost_usd):
        bad("limits.cost_usd must be > 0")
    max_iterations = _get(data, "limits.max_iterations")
    if not (
        isinstance(max_iterations, int)
        and not isinstance(max_iterations, bool)
        and max_iterations > 0
    ):
        bad("limits.max_iterations must be > 0")
    timeout_s = _get(data, "grader.timeout_s")
    if not _positive(timeout_s):
        bad("grader.timeout_s must be > 0")
    visibility = _get(data, "grader.visibility")
    if visibility is _MISSING:
        visibility = "hidden"
    if visibility not in ("hidden", "visible"):
        bad("grader.visibility must be hidden or visible")
    delete = _get(data, "reference.delete")
    if delete is _MISSING:
        delete = []
    if not (isinstance(delete, list) and all(_rel_ok(d) for d in delete)):
        bad("reference.delete must be a list of relative paths")
    entry = _get(data, "grader.entry")
    if not _rel_ok(entry):
        bad("field 'grader.entry' must be a relative path")

    root = task_dir.resolve()

    def locate(dotted: str) -> Path | None:
        rel = _get(data, dotted)
        if not isinstance(rel, str) or not rel:
            bad(f"field '{dotted}' must be a relative path")
            return None
        if ".." in Path(rel).parts or Path(rel).is_absolute():
            bad(f"path escapes the task directory: {rel}")
            return None
        resolved = (task_dir / rel).resolve()
        if not resolved.is_relative_to(root):
            bad(f"path escapes the task directory: {rel}")
            return None
        return resolved

    requirements = locate("requirements")
    template = locate("template")
    grader_dir = locate("grader.dir")
    reference_dir = locate("reference.dir")
    if requirements is not None and not requirements.is_file():
        bad(f"requirements file not found: {_get(data, 'requirements')}")
    if template is not None and not template.is_dir():
        bad(f"template directory not found: {_get(data, 'template')}")
    if grader_dir is not None and not grader_dir.is_dir():
        bad(f"grader directory not found: {_get(data, 'grader.dir')}")
    if grader_dir is not None and grader_dir.is_dir() and _rel_ok(entry):
        if not (grader_dir / entry).is_file():
            bad(f"grader entry not found: {_get(data, 'grader.dir')}/{entry}")
    if reference_dir is not None and not reference_dir.is_dir():
        bad(f"reference directory not found: {_get(data, 'reference.dir')}")
    if template is not None and reference_dir is not None:
        if reference_dir.is_relative_to(template):
            bad(f"reference solution is inside the agent template ({_get(data, 'reference.dir')})")
    if template is not None and grader_dir is not None and visibility == "hidden":
        if grader_dir.is_relative_to(template):
            bad(f"hidden grader is inside the agent template ({_get(data, 'grader.dir')})")
    if template is not None and template.is_dir():
        if (template / REQUIREMENTS_NAME).exists() or (template / GRADER_DIRNAME).exists():
            bad("template must not contain REQUIREMENTS.md or .cora_grader")
    if len(errors) != start:
        return None
    return E2ETask(
        id=tid,
        title=title,
        difficulty=difficulty,
        root=task_dir,
        requirements_path=requirements,
        template_dir=template,
        required_files=tuple(required_files),
        wall_s=float(wall_s),
        cost_usd=float(cost_usd),
        max_iterations=max_iterations,
        grader_dir=grader_dir,
        grader_entry=entry,
        grader_timeout_s=float(timeout_s),
        grader_visibility=visibility,
        reference_dir=reference_dir,
        reference_delete=tuple(delete),
    )


def load_e2e_tasks(root: Path | None = None) -> tuple[E2ETask, ...]:
    base = root or e2e_tasks_dir()
    errors: list[str] = []
    tasks: list[E2ETask] = []
    first_dir: dict[str, Path] = {}
    dirs = sorted(
        p for p in base.iterdir()
        if p.is_dir() and p.name != "__pycache__" and not p.name.startswith(".")
    )
    for d in dirs:
        task = _parse_task(d, errors)
        if task is None:
            continue
        if task.id in first_dir:
            errors.append(
                f"duplicate e2e task id '{task.id}' in {first_dir[task.id].name} and {d.name}"
            )
            continue
        first_dir[task.id] = d
        tasks.append(task)
    if errors:
        raise ConfigError("invalid e2e task(s):\n" + "\n".join(f"- {e}" for e in errors))
    return tuple(tasks)


def select_e2e_tasks(ids: Sequence[str] | None, root: Path | None = None) -> tuple[E2ETask, ...]:
    tasks = load_e2e_tasks(root)
    if not ids:
        return tasks
    by_id = {t.id: t for t in tasks}
    selected: list[E2ETask] = []
    for x in ids:
        if x not in by_id:
            raise ConfigError(f"unknown e2e task id '{x}'; known: {[t.id for t in tasks]}")
        selected.append(by_id[x])
    return tuple(selected)


def agent_prompt(task: E2ETask) -> str:
    files = ", ".join(task.required_files)
    return (
        "Read REQUIREMENTS.md in the current directory and implement everything it asks for "
        f"in this directory. Required files: {files}. Work only inside this directory. When "
        "you are done, reply with a short final answer that summarises what you built."
    )


def prepare_workspace(task: E2ETask, tmp: Path) -> Path:
    ws = tmp / "ws"
    shutil.copytree(task.template_dir, ws, ignore=_IGNORE)
    shutil.copyfile(task.requirements_path, ws / REQUIREMENTS_NAME)
    if task.grader_visibility == "visible":
        shutil.copytree(task.grader_dir, ws / GRADER_DIRNAME, ignore=_IGNORE)
    return ws


def apply_reference(task: E2ETask, ws: Path, *, delete: bool = True) -> None:
    fields = vars(task)
    shutil.copytree(fields["reference_dir"], ws, dirs_exist_ok=True, ignore=_IGNORE)
    if delete:
        for rel in fields["reference_delete"]:
            (ws / rel).unlink(missing_ok=True)


def inject_grader(task: E2ETask, ws: Path) -> Path:
    dest = ws / GRADER_DIRNAME
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task.grader_dir, dest, ignore=_IGNORE)
    return dest / task.grader_entry


def grader_env(ws: Path) -> dict[str, str]:
    env = {k: os.environ[k] for k in GRADER_ENV_ALLOW if k in os.environ}
    env.update(
        {
            "HOME": str(ws),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    return env


@dataclass
class GraderResult:
    status: str
    score: float
    full_pass: bool
    checks: list[dict]
    reason: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    output_truncated: bool = False
    missing_files: list[str] = field(default_factory=list)
    output_tail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _kill_group(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)


def _read_tail(path: Path, cap: int) -> tuple[str, bool]:
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(max(0, size - cap))
        data = fh.read(min(size, cap))
    return data.decode("utf-8", "replace"), size > cap


def _parse_checks(text: str) -> list[dict]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("no output")
    try:
        obj = json.loads(lines[-1])
    except ValueError:
        raise ValueError("last line is not JSON") from None
    checks = obj.get("checks") if isinstance(obj, dict) else None
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
        raise ValueError(f"checks must be a list of 1 to {MAX_CHECKS} entries")
    for c in checks:
        if not (
            isinstance(c, dict)
            and isinstance(c.get("name"), str)
            and c["name"]
            and isinstance(c.get("passed"), bool)
        ):
            raise ValueError("each check needs a non-empty name and a boolean passed")
    return checks


def _failed(
    reason: str,
    *,
    missing: list[str],
    code: int | None = None,
    timed_out: bool = False,
    truncated: bool = False,
    tail: str = "",
) -> GraderResult:
    return GraderResult(
        status="grader_error",
        score=0.0,
        full_pass=False,
        checks=[],
        reason=reason,
        exit_code=code,
        timed_out=timed_out,
        output_truncated=truncated,
        missing_files=missing,
        output_tail=tail,
    )


def run_grader(task: E2ETask, ws: Path, scratch: Path) -> GraderResult:
    missing = [f for f in task.required_files if not (ws / f).is_file()]
    entry = inject_grader(task, ws)
    scratch.mkdir(parents=True, exist_ok=True)
    timeout = min(task.grader_timeout_s, GRADER_TIMEOUT_CAP_S)
    out_path = scratch / "grader.stdout"
    err_path = scratch / "grader.stderr"
    timed_out = False
    with out_path.open("wb") as out, err_path.open("wb") as err:
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-B", str(entry)],
                cwd=ws,
                env=grader_env(ws),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
        except OSError as e:
            return _failed(f"cannot start grader: {type(e).__name__}", missing=missing)
        try:
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc.pid)
                code = proc.wait()
        finally:
            _kill_group(proc.pid)
    stdout_tail, out_cut = _read_tail(out_path, MAX_GRADER_OUTPUT_BYTES)
    stderr_tail, err_cut = _read_tail(err_path, MAX_GRADER_OUTPUT_BYTES)
    truncated = out_cut or err_cut
    tail = (stderr_tail + stdout_tail)[-1000:]
    if timed_out:
        return _failed(
            f"grader timed out after {timeout:g}s", missing=missing, code=code,
            timed_out=True, truncated=truncated, tail=tail,
        )
    if code != 0:
        return _failed(
            f"grader exited with code {code}", missing=missing, code=code,
            truncated=truncated, tail=tail,
        )
    try:
        checks = _parse_checks(stdout_tail)
    except ValueError as e:
        return _failed(
            f"invalid grader output: {e}", missing=missing, code=code,
            truncated=truncated, tail=tail,
        )
    normalised = [
        {
            "name": c["name"],
            "passed": c["passed"],
            "detail": str(c.get("detail", ""))[:500],
        }
        for c in checks
    ]
    passed = sum(1 for c in normalised if c["passed"])
    total = len(normalised)
    return GraderResult(
        status="ok",
        score=passed / total,
        full_pass=passed == total,
        checks=normalised,
        exit_code=code,
        output_truncated=truncated,
        missing_files=missing,
        output_tail=tail,
    )
