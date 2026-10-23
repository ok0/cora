from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar

import httpx

from cora.core.config import OPENAI_COMPAT, validate_openai_compat_settings
from cora.core.errors import (
    ACCOUNT_STATUSES,
    BODY_MAX_CHARS,
    DETAIL_MAX_CHARS,
    MissingAPIKeyError,
    ProviderAccountError,
    ProviderError,
)
from cora.core.providers.base import emit_provider_event, register_provider
from cora.core.providers.openrouter import (
    DEFAULT_REQUEST_DEADLINE_S,
    DEFAULT_STREAM_STALL_TIMEOUT_S,
    RETRY_DELAYS_S,
    RequestDeadlineExceeded,
    StreamStalled,
    _cached_tokens,
    _usage_cost,
)
from cora.core.types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    NativeToolCall,
)

T = TypeVar("T")
NAME = OPENAI_COMPAT
DEFAULT_TIMEOUT_S = 120
DEFAULT_MAX_429_RETRIES = 4
MAX_RETRY_AFTER_S = 120.0
_sleep = asyncio.sleep


def backoff_s(n: int) -> float:
    return RETRY_DELAYS_S[min(n, len(RETRY_DELAYS_S) - 1)] * 2 ** max(
        0, n - len(RETRY_DELAYS_S) + 1
    )


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    if v.replace(".", "", 1).isdigit():
        return max(0.0, float(v))
    try:
        dt = parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0.0, (dt - now).total_seconds())


class RequestThrottle:
    def __init__(
        self,
        rpm_limit: int | None,
        *,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        self.interval = 60.0 / rpm_limit if rpm_limit else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next: float | None = None
        self._lock: asyncio.Lock | None = None

    async def wait(self) -> None:
        if self.interval == 0:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = self._clock()
            start = now if self._next is None else max(now, self._next)
            if start > now:
                await self._sleep(start - now)
            self._next = start + self.interval


class _RateLimited(Exception):
    def __init__(self, retry_after: str | None) -> None:
        super().__init__()
        self.retry_after = retry_after


class _RetryableStatus(Exception):
    pass


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        )
    return ""


def _extra(v: Any) -> dict | None:
    return v if isinstance(v, dict) else None


def _parse_tool_calls(raw: Any) -> tuple[NativeToolCall, ...]:
    calls: list[NativeToolCall] = []
    for i, tc in enumerate(raw or []):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, (dict, list)):
            args = json.dumps(args)
        elif args is None:
            args = ""
        calls.append(
            NativeToolCall(
                str(tc.get("id") or f"call_{i}"),
                str(fn.get("name") or ""),
                str(args),
                extra_content=_extra(tc.get("extra_content")),
            )
        )
    return tuple(calls)


def _wire_message(m: Message) -> dict:
    if m.role == "tool":
        wire: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": m.tool_call_id or "",
            "content": m.content,
        }
    elif m.tool_calls:
        calls: list[dict[str, Any]] = []
        for c in m.tool_calls:
            call: dict[str, Any] = {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": c.arguments or "{}"},
            }
            if c.extra_content is not None:
                call["extra_content"] = c.extra_content
            calls.append(call)
        wire = {"role": "assistant", "content": m.content or None, "tool_calls": calls}
    else:
        wire = {"role": m.role, "content": m.content}
    if m.role == "assistant" and m.extra_content is not None:
        wire["extra_content"] = m.extra_content
    return wire


@register_provider(NAME)
class OpenAICompatProvider:
    display_name = "OpenAI-compatible"

    def __init__(
        self,
        settings: Mapping[str, Any],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        validate_openai_compat_settings(settings, 'providers (type = "openai_compat")')
        env = settings["api_key_env"]
        base_url = settings["base_url"].rstrip("/")
        key = os.environ.get(env)
        if not key:
            raise MissingAPIKeyError(
                f"{env} is not set. Export it (e.g. `export {env}=...`) to use the "
                f"{NAME} provider at {base_url}. Never commit keys."
            )
        self._api_key = key
        self.base_url = base_url
        self.timeout_s = settings.get("timeout_s", DEFAULT_TIMEOUT_S)
        self.request_deadline_s = float(
            settings.get("request_deadline_s", DEFAULT_REQUEST_DEADLINE_S)
        )
        self.stream_stall_timeout_s = float(
            settings.get("stream_stall_timeout_s", DEFAULT_STREAM_STALL_TIMEOUT_S)
        )
        self.max_429_retries = int(settings.get("max_429_retries", DEFAULT_MAX_429_RETRIES))
        self.transport = transport
        self._sleep_fn = sleep
        self._now = now or (lambda: datetime.now(UTC))
        self._throttle = RequestThrottle(
            settings.get("rpm_limit"), clock=clock or time.monotonic, sleep=self._sleep
        )

    async def _sleep(self, s: float) -> None:
        await (self._sleep_fn or _sleep)(s)

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "[REDACTED]")

    def _body(self, request: CompletionRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [_wire_message(m) for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop:
            body["stop"] = request.stop
        if request.tools:
            body["tools"] = request.tools
            body["tool_choice"] = "auto"
        if request.response_format:
            body["response_format"] = request.response_format
        return body

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if 200 <= resp.status_code < 300:
            return
        body = self._redact(resp.text)[:BODY_MAX_CHARS]
        msg = f"{NAME} HTTP {resp.status_code}: {body[:DETAIL_MAX_CHARS]}"
        if resp.status_code in ACCOUNT_STATUSES:
            raise ProviderAccountError(resp.status_code, msg, body=body, provider=NAME)
        raise ProviderError(msg)

    def _chunk_error(self, err: Any) -> ProviderError:
        raw = json.dumps(err, ensure_ascii=False) if isinstance(err, (dict, list)) else str(err)
        body = self._redact(raw)[:BODY_MAX_CHARS]
        msg = f"{NAME} stream error: " + self._redact(str(err))[:DETAIL_MAX_CHARS]
        code = err.get("code") if isinstance(err, dict) else None
        if code in ACCOUNT_STATUSES:
            return ProviderAccountError(int(code), msg, body=body, provider=NAME)
        return ProviderError(msg)

    def _response(
        self,
        request: CompletionRequest,
        text: str,
        usage: dict,
        model: str,
        tool_calls: tuple[NativeToolCall, ...] = (),
        extra: dict | None = None,
        finish_reason: str | None = None,
    ) -> CompletionResponse:
        return CompletionResponse(
            text=text,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=model,
            tool_calls=tuple(tool_calls),
            cost_usd=_usage_cost(usage),
            cached_input_tokens=_cached_tokens(usage),
            extra_content=extra,
            finish_reason=finish_reason,
        )

    async def _rate_limited(self, retry_after: str | None, n: int) -> None:
        ra = parse_retry_after(retry_after, self._now())
        exhausted = n >= self.max_429_retries or (ra is not None and ra > MAX_RETRY_AFTER_S)
        wait = ra if ra is not None else backoff_s(n)
        emit_provider_event(
            "rate_limited",
            status=429,
            attempt=n + 1,
            max_429_retries=self.max_429_retries,
            retry_after_s=ra,
            wait_s=None if exhausted else wait,
            retrying=not exhausted,
        )
        if exhausted:
            detail = (
                f" (Retry-After {ra:g}s exceeds {MAX_RETRY_AFTER_S:g}s)"
                if ra is not None and ra > MAX_RETRY_AFTER_S
                else ""
            )
            raise ProviderError(f"{NAME} rate limited: HTTP 429 after {n} retries{detail}")
        await self._sleep(wait)

    async def _attempts(
        self,
        once: Callable[[bool], Awaitable[T]],
        *,
        transport_retry_ok: Callable[[], bool],
    ) -> T:
        transient = 0
        limited = 0
        while True:
            await self._throttle.wait()
            try:
                return await once(transient >= len(RETRY_DELAYS_S))
            except _RateLimited as e:
                await self._rate_limited(e.retry_after, limited)
                limited += 1
            except _RetryableStatus:
                await self._sleep(RETRY_DELAYS_S[transient])
                transient += 1
            except httpx.TransportError:
                if not transport_retry_ok() or transient >= len(RETRY_DELAYS_S):
                    raise
                await self._sleep(RETRY_DELAYS_S[transient])
                transient += 1

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        body = self._body(request)
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self.transport
            ) as client:

                async def once(last: bool) -> httpx.Response:
                    req = client.build_request("POST", url, json=body, headers=headers)
                    try:
                        async with asyncio.timeout(self.request_deadline_s):
                            resp = await client.send(req)
                    except TimeoutError:
                        raise RequestDeadlineExceeded(
                            "no complete response within "
                            f"request_deadline_s={self.request_deadline_s:g}s"
                        ) from None
                    if resp.status_code == 429:
                        raise _RateLimited(resp.headers.get("Retry-After"))
                    if resp.status_code >= 500 and not last:
                        raise _RetryableStatus()
                    return resp

                resp = await self._attempts(once, transport_retry_ok=lambda: True)
        except httpx.HTTPError as e:
            raise ProviderError(
                self._redact(f"{NAME} request failed: {type(e).__name__}: {e}")
            ) from None
        self._raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError:
            raise ProviderError(f"{NAME} returned invalid JSON") from None
        if not isinstance(data, dict):
            raise ProviderError(f"{NAME} returned invalid JSON")
        choices = data.get("choices")
        if not choices or not isinstance(choices[0], dict):
            raise ProviderError(
                self._redact(f"{NAME} response without choices: {str(data.get('error'))[:300]}")
            )
        msg = choices[0].get("message")
        if not isinstance(msg, dict):
            msg = {}
        text = _content_text(msg.get("content"))
        tool_calls = _parse_tool_calls(msg.get("tool_calls"))
        extra = _extra(msg.get("extra_content"))
        raw_model = data.get("model")
        model = raw_model if isinstance(raw_model, str) else request.model
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        fr = choices[0].get("finish_reason")
        return self._response(
            request,
            text,
            usage,
            model,
            tool_calls,
            extra,
            finish_reason=fr if isinstance(fr, str) else None,
        )

    async def stream(
        self, request: CompletionRequest, on_text: Callable[[str], None]
    ) -> CompletionResponse:
        body = self._body(request)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        url = f"{self.base_url}/chat/completions"
        headers = self._headers()
        emitted = False

        def emit(text: str) -> None:
            nonlocal emitted
            emitted = True
            on_text(text)

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self.transport
            ) as client:

                async def once(last: bool) -> CompletionResponse:
                    try:
                        async with asyncio.timeout(self.request_deadline_s):
                            req = client.build_request("POST", url, json=body, headers=headers)
                            resp = await client.send(req, stream=True)
                            try:
                                if resp.status_code == 429:
                                    await resp.aread()
                                    raise _RateLimited(resp.headers.get("Retry-After"))
                                if resp.status_code >= 500 and not last:
                                    raise _RetryableStatus()
                                if not (200 <= resp.status_code < 300):
                                    await resp.aread()
                                    self._raise_for_status(resp)
                                return await self._read_sse(resp, request, emit)
                            finally:
                                await resp.aclose()
                    except TimeoutError:
                        raise RequestDeadlineExceeded(
                            "no complete response within "
                            f"request_deadline_s={self.request_deadline_s:g}s"
                        ) from None

                return await self._attempts(once, transport_retry_ok=lambda: not emitted)
        except httpx.HTTPError as e:
            raise ProviderError(
                self._redact(f"{NAME} request failed: {type(e).__name__}: {e}")
            ) from None

    async def _read_sse(
        self, resp: httpx.Response, request: CompletionRequest, emit: Callable[[str], None]
    ) -> CompletionResponse:
        parts: list[str] = []
        usage: dict[str, Any] = {}
        model = request.model
        extra: dict | None = None
        finish_reason: str | None = None
        acc: dict[int, dict[str, Any]] = {}
        loop = asyncio.get_running_loop()
        lines = resp.aiter_lines()
        last_data = loop.time()
        try:
            while True:
                remaining = self.stream_stall_timeout_s - (loop.time() - last_data)
                try:
                    if remaining <= 0:
                        raise TimeoutError
                    async with asyncio.timeout(remaining):
                        line = await anext(lines)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise StreamStalled(
                        "no stream data within "
                        f"stream_stall_timeout_s={self.stream_stall_timeout_s:g}s"
                    ) from None
                if not line.startswith("data:"):
                    continue
                last_data = loop.time()
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                if "error" in chunk:
                    raise self._chunk_error(chunk["error"])
                if isinstance(chunk.get("usage"), dict) and chunk["usage"]:
                    usage = chunk["usage"]
                if isinstance(chunk.get("model"), str):
                    model = chunk["model"]
                for choice in chunk.get("choices") or []:
                    if not isinstance(choice, dict):
                        continue
                    if isinstance(choice.get("finish_reason"), str):
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        delta = {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        parts.append(content)
                        emit(content)
                    if _extra(delta.get("extra_content")) is not None:
                        extra = _extra(delta.get("extra_content"))
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index", 0))
                        slot = acc.setdefault(
                            idx, {"id": "", "name": "", "arguments": "", "extra_content": None}
                        )
                        if tc.get("id"):
                            slot["id"] = str(tc["id"])
                        fn = tc.get("function") or {}
                        name = fn.get("name")
                        if name:
                            slot["name"] = (
                                name
                                if not slot["name"] or name == slot["name"]
                                else slot["name"] + name
                            )
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]
                        tc_extra = _extra(tc.get("extra_content"))
                        if tc_extra is not None:
                            slot["extra_content"] = tc_extra
        finally:
            await lines.aclose()
        calls = tuple(
            NativeToolCall(
                s["id"] or f"call_{i}",
                s["name"],
                s["arguments"],
                extra_content=s["extra_content"],
            )
            for i, s in sorted(acc.items())
        )
        return self._response(
            request, "".join(parts), usage, model, calls, extra, finish_reason=finish_reason
        )
