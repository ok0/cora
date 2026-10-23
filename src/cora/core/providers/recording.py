from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cora.core.config import RecordSettings
from cora.core.errors import ReplayMissError
from cora.core.providers.base import (
    AccountStatus,
    Provider,
    StreamingProvider,
    _factory_for,
    account_capability,
    create_provider,
    current_workspace,
)
from cora.core.types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    NativeToolCall,
)

ENTRY_FORMAT = 1
WS_PLACEHOLDER = "<WS>"
HOME_PLACEHOLDER = "<HOME>"
TS_PLACEHOLDER = "<TS>"
REDACTED = "[REDACTED]"

TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?")
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_\-]{15,}"),
)


def scrub_text(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if len(secret) >= 8:
            text = text.replace(secret, REDACTED)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def scrub_obj(obj: Any, secrets: Sequence[str]) -> Any:
    if isinstance(obj, str):
        return scrub_text(obj, secrets)
    if isinstance(obj, dict):
        return {k: scrub_obj(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_obj(v, secrets) for v in obj]
    if isinstance(obj, tuple):
        return tuple(scrub_obj(v, secrets) for v in obj)
    return obj


def tool_call_to_dict(c: NativeToolCall) -> dict:
    return {"id": c.id, "name": c.name, "arguments": c.arguments, "extra_content": c.extra_content}


def message_to_dict(m: Message) -> dict:
    return {
        "role": m.role,
        "content": m.content,
        "tool_calls": [tool_call_to_dict(c) for c in m.tool_calls],
        "tool_call_id": m.tool_call_id,
        "extra_content": m.extra_content,
    }


def _substitute(obj: Any, pairs: Sequence[tuple[str, str]]) -> Any:
    if isinstance(obj, str):
        s = obj
        for needle, placeholder in pairs:
            s = s.replace(needle, placeholder)
        return TS_RE.sub(TS_PLACEHOLDER, s)
    if isinstance(obj, dict):
        return {k: _substitute(v, pairs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, pairs) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_substitute(v, pairs) for v in obj)
    return obj


def _needles(paths: Sequence[str], placeholder: str) -> list[tuple[str, str]]:
    seen: list[str] = []
    for p in paths:
        if len(p) < 2 or p == "/" or p in seen:
            continue
        seen.append(p)
    seen.sort(key=len, reverse=True)
    return [(p, placeholder) for p in seen]


def normalize_request(
    request: CompletionRequest, *, workspace: Path | None, home: str | None
) -> dict:
    normalized = {
        "model": request.model,
        "messages": [message_to_dict(m) for m in request.messages],
        "tools": request.tools,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stop": list(request.stop) if request.stop is not None else None,
    }
    pairs: list[tuple[str, str]] = []
    if workspace is not None:
        ws_paths = [str(workspace), str(workspace.resolve()), os.path.realpath(workspace)]
        pairs.extend(_needles(ws_paths, WS_PLACEHOLDER))
    if home is not None:
        home_paths = [home, os.path.realpath(home)]
        pairs.extend(_needles(home_paths, HOME_PLACEHOLDER))
    return _substitute(normalized, pairs)


def request_key(normalized: dict) -> str:
    text = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def response_to_dict(r: CompletionResponse) -> dict:
    return {
        "text": r.text,
        "tool_calls": [tool_call_to_dict(c) for c in r.tool_calls],
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cached_input_tokens": r.cached_input_tokens,
        "cost_usd": r.cost_usd,
        "model": r.model,
        "finish_reason": r.finish_reason,
        "extra_content": r.extra_content,
    }


def response_from_dict(d: dict) -> CompletionResponse:
    return CompletionResponse(
        text=d["text"],
        input_tokens=d["input_tokens"],
        output_tokens=d["output_tokens"],
        model=d["model"],
        tool_calls=tuple(
            NativeToolCall(
                id=c["id"],
                name=c["name"],
                arguments=c["arguments"],
                extra_content=c.get("extra_content"),
            )
            for c in d.get("tool_calls", [])
        ),
        cost_usd=d.get("cost_usd"),
        cached_input_tokens=d.get("cached_input_tokens", 0),
        extra_content=d.get("extra_content"),
        finish_reason=d.get("finish_reason"),
        replayed=True,
    )


def default_home() -> str:
    return os.environ.get("HOME") or str(Path.home())


class RecordStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def load(self, key: str) -> dict | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, entry: dict) -> Path:
        key = entry["key"]
        path = self.path_for(key)
        text = json.dumps(entry, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return path


class RecordingProvider:
    def __init__(
        self,
        inner: Provider | None,
        *,
        name: str,
        store_dir: str | Path,
        mode: str,
        secrets: Sequence[str] = (),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if mode not in ("record", "replay"):
            raise ValueError(f"invalid recording mode: {mode!r}")
        if mode == "record" and inner is None:
            raise ValueError("record mode requires an inner provider")
        self.inner = inner
        self.name = name
        self.store_dir = store_dir
        self.mode = mode
        self.secrets = tuple(secrets)
        self.now = now if now is not None else (lambda: datetime.now(UTC))

    def _store(self) -> RecordStore:
        root = Path(self.store_dir).expanduser()
        if not root.is_absolute():
            root = (current_workspace() or Path.cwd()) / root
        return RecordStore(root)

    def _key(self, request: CompletionRequest) -> tuple[str, dict]:
        norm = normalize_request(request, workspace=current_workspace(), home=default_home())
        return request_key(norm), norm

    def _save(
        self,
        key: str,
        norm: dict,
        request: CompletionRequest,
        resp: CompletionResponse,
        *,
        stream: bool,
    ) -> None:
        entry = {
            "format": ENTRY_FORMAT,
            "key": key,
            "provider": self.name,
            "model": request.model,
            "recorded_at": self.now().isoformat(timespec="seconds"),
            "stream": stream,
            "request": scrub_obj(norm, self.secrets),
            "response": scrub_obj(response_to_dict(resp), self.secrets),
        }
        self._store().save(entry)

    def _replay(self, key: str, request: CompletionRequest) -> CompletionResponse:
        store = self._store()
        entry = store.load(key)
        if entry is None:
            raise ReplayMissError(key, request.model, str(store.path_for(key)))
        return response_from_dict(entry["response"])

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        key, norm = self._key(request)
        if self.mode == "replay":
            return self._replay(key, request)
        assert self.inner is not None
        resp = await self.inner.complete(request)
        self._save(key, norm, request, resp, stream=False)
        return resp

    async def account_status(self) -> AccountStatus | None:
        if self.mode == "replay":
            return None
        fn = account_capability(self.inner)
        return await fn() if fn else None


class StreamingRecordingProvider(RecordingProvider):
    async def stream(
        self, request: CompletionRequest, on_text: Callable[[str], None]
    ) -> CompletionResponse:
        key, norm = self._key(request)
        if self.mode == "replay":
            resp = self._replay(key, request)
            if resp.text:
                on_text(resp.text)
            return resp
        assert self.inner is not None
        resp = await cast(StreamingProvider, self.inner).stream(request, on_text)
        self._save(key, norm, request, resp, stream=True)
        return resp


def wrap_provider(
    name: str,
    settings: Mapping[str, Any],
    record: RecordSettings,
    *,
    secrets: Sequence[str],
) -> Provider:
    if record.mode == "replay":
        factory = _factory_for(name, settings)
        cls = (
            StreamingRecordingProvider
            if callable(getattr(factory, "stream", None))
            else RecordingProvider
        )
        return cls(None, name=name, store_dir=record.dir, mode="replay", secrets=secrets)
    inner = create_provider(name, settings)
    cls = (
        StreamingRecordingProvider
        if callable(getattr(inner, "stream", None))
        else RecordingProvider
    )
    return cls(inner, name=name, store_dir=record.dir, mode="record", secrets=secrets)
