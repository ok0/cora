from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cora.core.tools.base import IGNORED_DIRS

MENTION_RE = re.compile(r"(?<!\S)@(\S+)")
TRAILING = ".,;:!?)]}\"'"
TRUNC_MARK = "\n...[truncated]"


@dataclass(frozen=True)
class MentionExpansion:
    text: str
    notes: tuple[str, ...]
    attached: tuple[str, ...]


def expand_mentions(
    prompt: str,
    root: Path,
    *,
    max_file_chars: int,
    max_total_chars: int,
    max_dir_entries: int,
) -> MentionExpansion:
    root = root.resolve()
    out = ""
    notes: list[str] = []
    attached: list[str] = []
    seen: set[Path] = set()
    for m in MENTION_RE.finditer(prompt):
        raw = m.group(1)
        cands = [raw]
        stripped = raw.rstrip(TRAILING)
        if stripped != raw and stripped:
            cands.append(stripped)
        chosen: tuple[str, Path] | None = None
        outside = False
        for c in cands:
            p = (root / c).resolve()
            if not p.is_relative_to(root):
                notes.append(f"@{c}: outside the workspace; not attached")
                outside = True
                break
            if p.exists():
                chosen = (c, p)
                break
        if chosen is None:
            if not outside:
                notes.append(f"@{raw}: not found; not attached")
            continue
        c, p = chosen
        if p in seen:
            continue
        seen.add(p)
        rel = p.relative_to(root).as_posix() or "."
        if p.is_dir():
            header = f"\n\n--- @{rel}/ (directory listing) ---\n"
            entries = sorted(
                (e for e in p.iterdir() if e.name not in IGNORED_DIRS),
                key=lambda e: e.name,
            )
            lines = [e.name + ("/" if e.is_dir() else "") for e in entries[:max_dir_entries]]
            more = len(entries) - len(lines)
            if more > 0:
                lines.append(f"... ({more} more)")
            body = "\n".join(lines) or "(empty directory)"
            trunc = False
        elif not p.is_file():
            notes.append(f"@{c}: not a regular file; not attached")
            continue
        else:
            header = f"\n\n--- @{rel} ---\n"
            try:
                with p.open("rb") as fh:
                    data = fh.read(max_file_chars * 4 + 4)
                more = p.stat().st_size > len(data)
            except OSError as e:
                notes.append(f"@{c}: cannot read ({e.strerror or e}); not attached")
                continue
            if b"\0" in data[:8192]:
                notes.append(f"@{c}: binary file; not attached")
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as e:
                if more and e.start >= len(data) - 3:
                    text = data[: e.start].decode("utf-8")
                else:
                    notes.append(f"@{c}: binary file; not attached")
                    continue
            trunc = more or len(text) > max_file_chars
            body = text[:max_file_chars]
        room = max_total_chars - len(out) - len(header) - len(TRUNC_MARK)
        if room <= 0:
            notes.append(f"@{rel}: skipped; mention total limit {max_total_chars} chars reached")
            continue
        if len(body) > room:
            body = body[:room]
            trunc = True
        out += header + body + (TRUNC_MARK if trunc else "")
        if trunc:
            notes.append(f"@{rel}: truncated")
        attached.append(rel)
    return MentionExpansion(out, tuple(notes), tuple(attached))


def mention_candidates(root: Path, partial: str, limit: int = 50) -> list[str]:
    if partial.startswith(("/", "~")):
        return []
    d, sep, prefix = partial.rpartition("/")
    root = root.resolve()
    base = (root / d).resolve() if d else root
    if not base.is_relative_to(root) or not base.is_dir():
        return []
    out: list[str] = []
    try:
        for entry in sorted(base.iterdir(), key=lambda e: e.name):
            name = entry.name
            if name in IGNORED_DIRS or not name.startswith(prefix):
                continue
            if name.startswith(".") and not prefix.startswith("."):
                continue
            out.append(f"{d}{sep}{name}" + ("/" if entry.is_dir() else ""))
            if len(out) >= limit:
                break
    except OSError:
        return out
    return out
