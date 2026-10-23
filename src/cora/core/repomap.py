import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cora.core.shellguard import PathGuard
from cora.core.tools.base import IGNORED_DIRS

CACHE_RELPATH = Path("index") / "repomap.json"
CACHE_VERSION = 1
TRUNCATION_MARKER = "[repo map truncated]"
MAX_PARSE_BYTES = 512_000
MAX_SYMBOLS = 30

FileRecord = tuple[int, int, tuple[str, ...]]


@dataclass(frozen=True)
class RepoEntry:
    path: str
    size: int
    symbols: tuple[str, ...] = ()


def python_symbols(source: bytes) -> tuple[str, ...]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
        return ()
    return tuple(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _load_cache(cache_path: Path | None) -> dict[str, FileRecord]:
    if cache_path is None:
        return {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        return {}
    files = raw.get("files")
    if not isinstance(files, dict):
        return {}
    loaded: dict[str, FileRecord] = {}
    for path, info in files.items():
        if not isinstance(info, dict):
            return {}
        mtime = info.get("mtime_ns")
        size = info.get("size")
        syms = info.get("symbols")
        if not (_is_int(mtime) and _is_int(size) and isinstance(syms, list)
                and all(isinstance(s, str) for s in syms)):
            return {}
        loaded[path] = (mtime, size, tuple(syms))
    return loaded


def _write_cache(cache_path: Path, files: dict[str, FileRecord]) -> None:
    payload = {
        "version": CACHE_VERSION,
        "files": {
            p: {"mtime_ns": m, "size": s, "symbols": list(sy)}
            for p, (m, s, sy) in files.items()
        },
    }
    tmp = cache_path.with_suffix(".tmp")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(tmp, cache_path)
    except OSError:
        return


def _line(e: RepoEntry) -> str:
    head = f"{e.path} ({e.size} B)"
    if not e.symbols:
        return head
    syms = list(e.symbols[:MAX_SYMBOLS])
    extra = len(e.symbols) - MAX_SYMBOLS
    if extra > 0:
        syms.append(f"+{extra} more")
    return f"{head}: {', '.join(syms)}"


@dataclass
class RepoMap:
    entries: tuple[RepoEntry, ...]
    parsed: int = 0
    capped: bool = False

    @classmethod
    def build(
        cls,
        workspace: Path,
        guard: PathGuard,
        *,
        max_files: int,
        cache_path: Path | None = None,
    ) -> "RepoMap":
        root = Path(os.path.realpath(workspace))
        cached = _load_cache(cache_path)

        collected: list[tuple[str, Path, os.stat_result]] = []
        capped = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in IGNORED_DIRS
                and guard.check_real(
                    Path(os.path.realpath(os.path.join(dirpath, d))), write=False) is None
            )
            for fn in sorted(filenames):
                real = Path(os.path.realpath(os.path.join(dirpath, fn)))
                if guard.check_real(real, write=False) is not None or not real.is_file():
                    continue
                if len(collected) >= max_files:
                    capped = True
                    break
                try:
                    st = os.stat(real)
                except OSError:
                    continue
                rel = (Path(dirpath) / fn).relative_to(root).as_posix()
                collected.append((rel, real, st))
            if capped:
                break

        files: dict[str, FileRecord] = {}
        entries: list[RepoEntry] = []
        parsed = 0
        for rel, real, st in collected:
            syms: tuple[str, ...] = ()
            if rel.endswith(".py") and st.st_size <= MAX_PARSE_BYTES:
                hit = cached.get(rel)
                if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
                    syms = hit[2]
                else:
                    try:
                        data = real.read_bytes()
                    except OSError:
                        data = None
                    if data is not None:
                        syms = python_symbols(data)
                        parsed += 1
            files[rel] = (st.st_mtime_ns, st.st_size, syms)
            entries.append(RepoEntry(rel, st.st_size, syms))

        if cache_path is not None and files != cached:
            _write_cache(cache_path, files)
        return cls(tuple(entries), parsed, capped)

    def render(self, max_chars: int) -> str:
        lines = [_line(e) for e in self.entries]
        full = "\n".join(lines)
        if not self.capped and len(full) <= max_chars:
            return full
        if len(TRUNCATION_MARKER) > max_chars:
            return TRUNCATION_MARKER[:max_chars]
        kept: list[str] = []
        used = 0
        for line in lines:
            if used + len(line) + 1 + len(TRUNCATION_MARKER) > max_chars:
                break
            kept.append(line)
            used += len(line) + 1
        return "\n".join(kept + [TRUNCATION_MARKER])
