from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from cora.core.config import MemorySettings
from cora.core.shellguard import PathGuard, analyze, secret_like
from cora.core.types import Message, NativeToolCall, estimate_tokens, messages_tokens

OMITTED_MARKER = "- ...(older steps omitted)"
RECENT_TRUNCATE_CHARS = 500
SUPERSEDED_MARKER = "[superseded: {path} read again later]"
READ_TOOL = "read_file"
COMPRESSED_MARKER = "\n...[compressed: {n} chars omitted]...\n"
COMPRESSED_TAG = "[compressed: "
OBSERVATION_PREFIX = "Observation:"
LEDGER_HEADER = (
    "Working state (kept when older messages are trimmed; re-read a file before editing it):"
)
PROTECTED_MARK = "<protected>"
REDACTED_MARK = "<redacted>"
LEDGER_CMD_CHARS = 120
LEDGER_TAIL_CHARS = 120
LEDGER_DECISION_CHARS = 160
SUMMARY_LINE_CHARS = 400
SUMMARY_INPUT_CHARS = 4000
SUMMARY_MSG_CHARS = 300
SUMMARY_MAX_TOKENS = 256
SUMMARY_SYSTEM = (
    "Summarize, in at most 3 short sentences, what these earlier agent steps did and found "
    "(files touched, commands run, results, decisions). Do not quote file contents."
)
_PROTECTED_RULES = frozenset({"floor:protected-path", "floor:credential-file"})


class PersistentStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def append(self, session_id: str, kind: str, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"kind": kind, "data": data}, ensure_ascii=False)
        with self._path(session_id).open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read(self, session_id: str, kind: str | None = None) -> list[dict]:
        path = self._path(session_id)
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if kind is not None:
            rows = [r for r in rows if r["kind"] == kind]
        return rows


def _msg_to_dict(m: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        d["tool_calls"] = [
            {
                "id": c.id,
                "name": c.name,
                "arguments": c.arguments,
                **({"extra_content": c.extra_content} if c.extra_content is not None else {}),
            }
            for c in m.tool_calls
        ]
    if m.tool_call_id is not None:
        d["tool_call_id"] = m.tool_call_id
    if m.extra_content is not None:
        d["extra_content"] = m.extra_content
    return d


def _msg_from_dict(d: dict[str, Any]) -> Message:
    calls = tuple(
        NativeToolCall(
            id=c["id"],
            name=c["name"],
            arguments=c["arguments"],
            extra_content=c.get("extra_content"),
        )
        for c in d.get("tool_calls", [])
    )
    return Message(
        role=d["role"],
        content=d["content"],
        tool_calls=calls,
        tool_call_id=d.get("tool_call_id"),
        extra_content=d.get("extra_content"),
    )


def normalize_read_path(root: Path, raw: str) -> str | None:
    cand = Path(raw).expanduser()
    try:
        p = (cand if cand.is_absolute() else root / cand).resolve()
        return p.relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def read_path_of(root: Path, tool: str, args: Any, ok: bool) -> str | None:
    if tool != READ_TOOL or not ok or not isinstance(args, dict):
        return None
    if not isinstance(args.get("path"), str):
        return None
    return normalize_read_path(root, args["path"])


def superseded(path: str) -> str:
    return SUPERSEDED_MARKER.format(path=path)


def is_observation(m: Message) -> bool:
    return m.role == "tool" or (m.role == "user" and m.content.startswith(OBSERVATION_PREFIX))


def compress_text(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit or COMPRESSED_TAG in text:
        return text
    head = limit // 2
    tail = limit - head
    tail_text = text[-tail:] if tail else ""
    out = text[:head] + COMPRESSED_MARKER.format(n=len(text) - limit) + tail_text
    return out if len(out) < len(text) else text


def compress_observations(
    messages: list[Message],
    limit: int,
    keep_last: int,
    *,
    start: int = 0,
    protected: Collection[int] = (),
) -> int:
    if limit <= 0:
        return 0
    obs = [i for i in range(start, len(messages)) if is_observation(messages[i])]
    if not obs:
        return 0
    last = obs[-1]
    end = len(messages) - max(keep_last, 0)
    changed = 0
    for i in obs:
        if i >= end or i == last or i in protected:
            continue
        new = compress_text(messages[i].content, limit)
        if new != messages[i].content:
            messages[i] = dataclasses.replace(messages[i], content=new)
            changed += 1
    return changed


def _one_line(text: str, n: int) -> str:
    s = " ".join(text.split())
    if len(s) > n:
        s = s[: n - 1] + "…"
    return s


def mask_path(root: Path, guard: PathGuard | None, raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    if guard is not None and guard.check_real(
        guard.resolve(os.path.expanduser(raw)), write=False
    ) is not None:
        return PROTECTED_MARK
    rel = normalize_read_path(root, raw)
    return rel if rel is not None else PROTECTED_MARK


def mask_command(guard: PathGuard | None, command: str) -> str:
    if guard is None:
        return command
    a = analyze(command, guard)
    found = list(a.findings) + [f for seg in a.segments for f in seg.findings]
    if any(f.rule in _PROTECTED_RULES for f in found):
        return PROTECTED_MARK
    return command


def scrub_secrets(text: str, env: Mapping[str, str], names: Collection[str]) -> str:
    for name in sorted(set(names) | {n for n in env if secret_like(n)}):
        v = env.get(name)
        if v and len(v) >= 6:
            text = text.replace(v, REDACTED_MARK)
    return text


def summary_messages(evicted: list[tuple[Message, str | None]]) -> list[Message]:
    lines: list[str] = []
    for msg, path in evicted:
        if path:
            lines.append(f"- {msg.role}: [read {path}]")
        else:
            text = msg.content or ("called " + ", ".join(c.name for c in msg.tool_calls))
            lines.append(f"- {msg.role}: " + _one_line(text, SUMMARY_MSG_CHARS))
    joined = "\n".join(lines)[:SUMMARY_INPUT_CHARS]
    return [Message("system", SUMMARY_SYSTEM), Message("user", joined)]


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _verdict(c: dict) -> str:
    return "PASS" if c["ok"] else "FAIL"


def _format(s: dict) -> str:
    lines = [LEDGER_HEADER]
    checks = s["checks"]
    if checks:
        last = checks[-1]
        latest = f"Latest check: it{last['iteration']} {_verdict(last)} `{last['command']}`"
        if last["tail"]:
            latest += ": " + last["tail"]
        lines.append(latest)
    files = s["files"]
    if files:
        parts = []
        for p, f in files.items():
            if f["op"] == "delete":
                parts.append(
                    f"{p} (deleted, it{f['last']})" if s["detail"] else f"{p} (deleted)"
                )
            else:
                parts.append(
                    f"{p} ({f['op']} x{f['edits']}, it{f['last']})" if s["detail"] else p
                )
        lines.append("Files changed: " + "; ".join(parts))
    earlier = checks[:-1]
    if earlier:
        lines.append("Earlier checks:")
        for c in earlier:
            line = f"- it{c['iteration']} {_verdict(c)} `{c['command']}`"
            if s["tails"] and c["tail"]:
                line += ": " + c["tail"]
            lines.append(line)
    if s["decisions"]:
        lines.append("Decisions:")
        for d in s["decisions"]:
            line = f"- it{d['iteration']} {d['kind']}: {d['text']}"
            if d["count"] > 1:
                line += f" (x{d['count']})"
            lines.append(line)
    if s["read"]:
        lines.append(
            "Read earlier, no longer shown (re-read if needed): " + ", ".join(s["read"])
        )
    if s["summaries"]:
        lines.append("Earlier steps: " + " ".join(s["summaries"]))
    return "\n".join(lines)


def _pop_earlier_check(s: dict, ok: bool) -> bool:
    checks = s["checks"]
    for i in range(len(checks) - 1):
        if bool(checks[i]["ok"]) is ok:
            del checks[i]
            return True
    return False


def _step_tails(s: dict) -> bool:
    if s["tails"]:
        s["tails"] = False
        return True
    return False


def _step_pass(s: dict) -> bool:
    return _pop_earlier_check(s, True)


def _step_detail(s: dict) -> bool:
    if s["detail"]:
        s["detail"] = False
        return True
    return False


def _step_summary_old(s: dict) -> bool:
    if len(s["summaries"]) > 1:
        del s["summaries"][0]
        return True
    return False


def _step_read(s: dict) -> bool:
    if s["read"]:
        del s["read"][0]
        return True
    return False


def _step_fail(s: dict) -> bool:
    return _pop_earlier_check(s, False)


def _step_decision(s: dict) -> bool:
    if s["decisions"]:
        del s["decisions"][0]
        return True
    return False


def _step_summary_last(s: dict) -> bool:
    if s["summaries"]:
        del s["summaries"][0]
        return True
    return False


def _step_latest_tail(s: dict) -> bool:
    checks = s["checks"]
    if checks and checks[-1]["tail"]:
        checks[-1]["tail"] = ""
        return True
    return False


_COMPACT_STEPS = (
    _step_tails,
    _step_pass,
    _step_detail,
    _step_summary_old,
    _step_read,
    _step_fail,
    _step_decision,
    _step_summary_last,
    _step_latest_tail,
)


class WorkingStateLedger:
    def __init__(self, *, record: bool = True) -> None:
        self.record = record
        self.files: dict[str, dict] = {}
        self.checks: list[dict] = []
        self.decisions: list[dict] = []
        self.read_evicted: list[str] = []
        self.summaries: list[str] = []

    def note_file(self, path: str, op: str, iteration: int) -> None:
        if not self.record:
            return
        cur = self.files.get(path)
        edits = (cur["edits"] if cur else 0) + 1
        self.files[path] = {"op": op, "edits": edits, "last": iteration}

    def note_check(self, command: str, ok: bool, iteration: int, output: str) -> None:
        if not self.record:
            return
        self.checks.append(
            {
                "command": _one_line(command, LEDGER_CMD_CHARS),
                "ok": ok,
                "iteration": iteration,
                "tail": ""
                if ok
                else _one_line(output[-LEDGER_TAIL_CHARS * 2 :], LEDGER_TAIL_CHARS),
            }
        )

    def note_decision(self, kind: str, text: str, iteration: int) -> None:
        if not self.record:
            return
        t = _one_line(text, LEDGER_DECISION_CHARS)
        last = self.decisions[-1] if self.decisions else None
        if last is not None and last["kind"] == kind and last["text"] == t:
            last["count"] += 1
            last["iteration"] = iteration
        else:
            self.decisions.append({"kind": kind, "text": t, "iteration": iteration, "count": 1})

    def note_read_evicted(self, path: str) -> None:
        if not self.record:
            return
        if path not in self.read_evicted:
            self.read_evicted.append(path)

    def note_read_back(self, path: str) -> None:
        if path in self.read_evicted:
            self.read_evicted.remove(path)

    def add_summary(self, text: str) -> str:
        t = _one_line(text, SUMMARY_LINE_CHARS)
        if t:
            self.summaries.append(t)
        return t

    def is_empty(self) -> bool:
        return not (
            self.files or self.checks or self.decisions or self.read_evicted or self.summaries
        )

    def render(self, max_chars: int) -> str:
        if self.is_empty():
            return ""
        s: dict[str, Any] = {
            "files": dict(self.files),
            "checks": [dict(c) for c in self.checks],
            "decisions": [dict(d) for d in self.decisions],
            "read": list(self.read_evicted),
            "summaries": list(self.summaries),
            "detail": True,
            "tails": True,
        }
        while True:
            text = _format(s)
            if len(text) <= max_chars:
                return text
            if not any(step(s) for step in _COMPACT_STEPS):
                return text[: max_chars - 1] + "…"

    def to_dict(self) -> dict:
        return {
            "files": {p: dict(f) for p, f in self.files.items()},
            "checks": [dict(c) for c in self.checks],
            "decisions": [dict(d) for d in self.decisions],
            "read_evicted": list(self.read_evicted),
            "summaries": list(self.summaries),
        }

    @classmethod
    def from_dict(cls, data: Any, *, record: bool) -> WorkingStateLedger:
        led = cls(record=record)
        if not isinstance(data, dict):
            return led
        files = data.get("files")
        if isinstance(files, dict):
            for p, f in files.items():
                if (
                    isinstance(p, str)
                    and isinstance(f, dict)
                    and isinstance(f.get("op"), str)
                    and _is_int(f.get("edits"))
                    and _is_int(f.get("last"))
                ):
                    led.files[p] = {"op": f["op"], "edits": f["edits"], "last": f["last"]}
        checks = data.get("checks")
        if isinstance(checks, list):
            for c in checks:
                if (
                    isinstance(c, dict)
                    and isinstance(c.get("command"), str)
                    and isinstance(c.get("ok"), bool)
                    and _is_int(c.get("iteration"))
                    and isinstance(c.get("tail"), str)
                ):
                    led.checks.append(
                        {
                            "command": c["command"],
                            "ok": c["ok"],
                            "iteration": c["iteration"],
                            "tail": c["tail"],
                        }
                    )
        decisions = data.get("decisions")
        if isinstance(decisions, list):
            for d in decisions:
                if (
                    isinstance(d, dict)
                    and isinstance(d.get("kind"), str)
                    and isinstance(d.get("text"), str)
                    and _is_int(d.get("iteration"))
                    and _is_int(d.get("count"))
                ):
                    led.decisions.append(
                        {
                            "kind": d["kind"],
                            "text": d["text"],
                            "iteration": d["iteration"],
                            "count": d["count"],
                        }
                    )
        read = data.get("read_evicted")
        if isinstance(read, list):
            led.read_evicted = [r for r in read if isinstance(r, str)]
        summaries = data.get("summaries")
        if isinstance(summaries, list):
            led.summaries = [x for x in summaries if isinstance(x, str)]
        return led


class WorkingMemory:
    SUMMARY_PREFIX = "Summary of earlier steps:\n"

    def __init__(
        self,
        settings: MemorySettings,
        store: PersistentStore | None = None,
        session_id: str = "",
        *,
        dedupe_reads: bool = False,
        compress_chars: int = 0,
    ) -> None:
        self.settings = settings
        self.store = store
        self.session_id = session_id
        self.dedupe_reads = dedupe_reads
        self.compress_chars = compress_chars
        self.pinned: list[Message] = []
        self.summary_lines: list[str] = []
        self.recent: list[Message] = []
        self.read_paths: list[str | None] = []
        self.ledger = (
            WorkingStateLedger(record=settings.ledger)
            if (settings.ledger or settings.summarize == "llm")
            else None
        )
        self.ledger_text = ""
        self._evicted: list[tuple[Message, str | None]] = []
        self.dedupe_count = 0
        self.compressed_count = 0

    def pin(self, msg: Message) -> None:
        self.pinned.append(msg)

    def _sync_tags(self) -> None:
        if len(self.read_paths) != len(self.recent):
            self.read_paths = [None] * len(self.recent)

    def add(self, msg: Message, *, read_path: str | None = None) -> None:
        limit = self.settings.max_observation_chars
        if msg.role in ("user", "tool") and len(msg.content) > limit:
            msg = dataclasses.replace(msg, content=msg.content[:limit] + "\n...[truncated]")
        self._sync_tags()
        keep_tag = self.dedupe_reads or self.compress_chars > 0 or self.ledger is not None
        tag = read_path if keep_tag else None
        if tag is not None and self.dedupe_reads:
            for i in range(len(self.recent)):
                if self.read_paths[i] == tag:
                    self.recent[i] = dataclasses.replace(self.recent[i], content=superseded(tag))
                    self.read_paths[i] = None
                    self.dedupe_count += 1
        self.recent.append(msg)
        self.read_paths.append(tag)
        if self.ledger is not None and tag is not None:
            self.ledger.note_read_back(tag)

    def _compress_old(self) -> None:
        if self.compress_chars <= 0:
            return
        self._sync_tags()
        protected = {
            i
            for i, t in enumerate(self.read_paths)
            if t is not None and t not in self.read_paths[i + 1 :]
        }
        self.compressed_count += compress_observations(
            self.recent,
            self.compress_chars,
            self.settings.keep_last_messages,
            protected=protected,
        )

    def drain_context_counts(self) -> tuple[int, int]:
        counts = (self.dedupe_count, self.compressed_count)
        self.dedupe_count = 0
        self.compressed_count = 0
        return counts

    def _assemble(self, system_prompt: str) -> list[Message]:
        messages = [Message(role="system", content=system_prompt), *self.pinned]
        if self.ledger is not None:
            self.ledger_text = self.ledger.render(self.settings.ledger_max_chars)
            if self.ledger_text:
                messages.append(Message(role="user", content=self.ledger_text))
        if self.summary_lines:
            messages.append(
                Message(role="user", content=self.SUMMARY_PREFIX + "\n".join(self.summary_lines))
            )
        messages.extend(self.recent)
        return messages

    def _evict_one(self) -> None:
        self._sync_tags()
        old = self.recent.pop(0)
        tag = self.read_paths.pop(0)
        if self.store is not None:
            rec: dict[str, Any] = {"role": old.role, "content": old.content}
            if self.ledger is not None and tag is not None:
                rec["read_path"] = tag
            self.store.append(self.session_id, "evicted", rec)
        if self.ledger is not None:
            self._evicted.append((old, tag))
            if tag is not None:
                self.ledger.note_read_evicted(tag)
        text = old.content or ("called " + ", ".join(c.name for c in old.tool_calls))
        line = f"- {old.role}: {text[:160]}".replace("\n", " ")
        self.summary_lines.append(line)

    def _evict_oldest(self) -> None:
        self._evict_one()
        while self.recent and self.recent[0].role == "tool":
            self._evict_one()

    def build(self, system_prompt: str) -> list[Message]:
        budget = self.settings.context_budget_tokens
        keep_last = self.settings.keep_last_messages
        self._compress_old()

        def over_budget() -> bool:
            return messages_tokens(self._assemble(system_prompt)) > budget

        while over_budget() and len(self.recent) > keep_last:
            self._evict_oldest()

        dropped = False
        while (
            estimate_tokens("\n".join(self.summary_lines)) > budget // 4
            and len(self.summary_lines) > 1
        ):
            self.summary_lines.pop(0)
            dropped = True
        if dropped:
            self.summary_lines[0] = OMITTED_MARKER

        if over_budget():
            for i, m in enumerate(self.recent):
                if len(m.content) > RECENT_TRUNCATE_CHARS:
                    self.recent[i] = dataclasses.replace(
                        m, content=m.content[:RECENT_TRUNCATE_CHARS] + "…"
                    )
                if not over_budget():
                    break

        while over_budget() and len(self.recent) > 2:
            self._evict_oldest()

        if over_budget():
            for i, m in enumerate(self.pinned):
                self.pinned[i] = dataclasses.replace(m, content=m.content[:budget])

        return self._assemble(system_prompt)

    def drain_evicted(self) -> list[tuple[Message, str | None]]:
        out = self._evicted
        self._evicted = []
        return out

    def compact(self, keep: int = 2) -> int:
        n = 0
        while len(self.recent) > keep:
            self._evict_oldest()
            n += 1
        return n

    def to_dict(self) -> dict:
        self._sync_tags()
        d: dict = {
            "pinned": [_msg_to_dict(m) for m in self.pinned],
            "summary_lines": list(self.summary_lines),
            "recent": [_msg_to_dict(m) for m in self.recent],
        }
        if any(t is not None for t in self.read_paths):
            d["read_paths"] = list(self.read_paths)
        if self.ledger is not None:
            d["ledger"] = self.ledger.to_dict()
        return d

    @classmethod
    def from_dict(
        cls,
        data: dict,
        settings: MemorySettings,
        store: PersistentStore | None,
        session_id: str,
        *,
        dedupe_reads: bool = False,
        compress_chars: int = 0,
    ) -> WorkingMemory:
        mem = cls(
            settings,
            store,
            session_id,
            dedupe_reads=dedupe_reads,
            compress_chars=compress_chars,
        )
        mem.pinned = [_msg_from_dict(d) for d in data.get("pinned", [])]
        mem.summary_lines = list(data.get("summary_lines", []))
        mem.recent = [_msg_from_dict(d) for d in data.get("recent", [])]
        tags = data.get("read_paths")
        if (
            isinstance(tags, list)
            and len(tags) == len(mem.recent)
            and all(t is None or isinstance(t, str) for t in tags)
        ):
            mem.read_paths = list(tags)
        else:
            mem.read_paths = [None] * len(mem.recent)
        if mem.ledger is not None and isinstance(data.get("ledger"), dict):
            mem.ledger = WorkingStateLedger.from_dict(data["ledger"], record=settings.ledger)
        return mem
