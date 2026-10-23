from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from cora.core.config import validate_openrouter_settings
from cora.core.errors import (
    ACCOUNT_STATUSES,
    BODY_MAX_CHARS,
    DETAIL_MAX_CHARS,
    MissingAPIKeyError,
    ProviderAccountError,
    ProviderError,
    register_account_guidance,
)
from cora.core.providers.base import AccountStatus, register_provider
from cora.core.types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    NativeToolCall,
    estimate_tokens,
    messages_tokens,
)

RETRY_DELAYS_S = (1, 2)
DEFAULT_REQUEST_DEADLINE_S = 90.0
DEFAULT_STREAM_STALL_TIMEOUT_S = 30.0
ACCOUNT_TIMEOUT_S = 15.0
NAME = "openrouter"
DISPLAY_NAME = "OpenRouter"
CREDITS_URL = "https://openrouter.ai/settings/credits"
BALANCE_WARNING = "preflight: WARNING: OpenRouter account balance"
_AFFORD_RE = re.compile(r"can only afford\s+(\d+)", re.IGNORECASE)
_GUIDANCE: dict[int, tuple[str, ...]] = {
    401: (
        "OpenRouter rejected the API key: it is invalid, revoked or expired.",
        "Fix: set a valid key in the configured api_key_env (default OPENROUTER_API_KEY).",
    ),
    402: (
        "OpenRouter account is out of credits: the prepaid account balance cannot pay for "
        "this request. This is the account balance, not the API key's limit.",
        f"Fix: buy credits or enable auto top-up at {CREDITS_URL}. Having a saved payment "
        "card alone does not pay for requests.",
    ),
    403: (
        "OpenRouter denied access: the key is not allowed to make this request "
        "(permissions, model access, region or provider policy, or the key's own limit).",
        "Fix: check the key's settings and limit, and whether the model is available to you.",
    ),
}
_sleep = asyncio.sleep  # indirection so tests can fake backoff time
CACHE_CONTROL = {"type": "ephemeral"}


class RequestDeadlineExceeded(httpx.TimeoutException):
    """One HTTP attempt exceeded request_deadline_s (retried like a transport error)."""


class StreamStalled(httpx.TimeoutException):
    """No SSE data line within stream_stall_timeout_s (retried like a transport error)."""


class _RetryableStatus(Exception):
    """Internal: 429/5xx on a streaming attempt with retries left."""


def _wire_message(m: Message) -> dict:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content}
    if m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments or "{}"},
                }
                for c in m.tool_calls
            ],
        }
    return {"role": m.role, "content": m.content}


def _mark_cache_prefix(wire: list[dict]) -> None:
    last = -1
    for i, msg in enumerate(wire):
        if msg.get("role") != "system":
            break
        last = i
    if last < 0:
        return
    content = wire[last]["content"]
    if isinstance(content, str) and content:
        wire[last]["content"] = [
            {"type": "text", "text": content, "cache_control": dict(CACHE_CONTROL)}
        ]


def _cached_tokens(usage: dict) -> int:
    d = usage.get("prompt_tokens_details")
    if not isinstance(d, dict):
        return 0
    v = d.get("cached_tokens")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return int(v)
    return 0


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
            )
        )
    return tuple(calls)


def _usage_cost(usage: dict) -> float | None:
    c = usage.get("cost")
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return float(c)
    return None


@register_account_guidance(NAME)
def openrouter_guidance(status: int, body: str) -> list[str]:
    lines = list(_GUIDANCE.get(status, ()))
    if status == 402 and (m := _AFFORD_RE.search(body)):
        lines.append(
            f"Hint: the remaining balance can only afford {m.group(1)} tokens; "
            "the account balance is almost exhausted."
        )
    return lines


def _number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_expiry(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


AccountGet = Callable[[str], Awaitable[tuple[int, Any]]]


async def openrouter_account_status(account_get: AccountGet) -> AccountStatus:
    """/auth/key + /credits -> AccountStatus. Raises ProviderAccountError on 401/402/403."""
    notes: list[str] = []
    expires_at: datetime | None = None
    limit: float | None = None
    limit_remaining: float | None = None
    unlimited = False
    try:
        status, payload = await account_get("/auth/key")
    except Exception as e:  # network error: warn and continue; HTTP 402 mid-run is authoritative
        notes.append(
            f"preflight: warning: key check failed ({type(e).__name__}); continuing - an "
            "HTTP 402/401/403 during the run aborts it"
        )
        status, payload = None, None
    if status in ACCOUNT_STATUSES:
        raise ProviderAccountError(
            status, f"openrouter HTTP {status}: key check refused", provider=NAME
        )
    if status is not None:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not (200 <= status < 300) or not isinstance(data, dict):
            notes.append(f"preflight: unexpected key check response (HTTP {status}); continuing")
        else:
            raw = data.get("expires_at")
            if raw is not None:
                try:
                    exp = parse_expiry(raw) if isinstance(raw, str) else None
                except ValueError:
                    exp = None
                if exp is None:
                    notes.append("preflight: could not parse the key expires_at; continuing")
                else:
                    expires_at = exp
            lr = data.get("limit_remaining")
            if lr is None:
                unlimited = True
            elif _number(lr):
                limit_remaining = float(lr)
            else:
                notes.append("preflight: key limit_remaining is not a number; continuing")
            lim = data.get("limit")
            limit = float(lim) if _number(lim) else None
    balance_notes: list[str] = []
    balance: float | None = None
    details: dict[str, float] | None = None
    warning: str | None = None
    try:
        cstatus, cpayload = await account_get("/credits")
    except Exception as e:  # info only: never blocks the run
        balance_notes.append(f"preflight: credits unavailable ({type(e).__name__}; info only)")
    else:
        cdata = cpayload.get("data") if isinstance(cpayload, dict) else None
        if not (200 <= cstatus < 300) or not isinstance(cdata, dict):
            balance_notes.append(f"preflight: credits unavailable (HTTP {cstatus}; info only)")
        else:
            total, used = cdata.get("total_credits"), cdata.get("total_usage")
            if _number(total) and _number(used):
                balance = float(total) - float(used)
                details = {"total_credits": float(total), "total_usage": float(used)}
                balance_notes.append(
                    f"preflight: account balance ${balance:.4f} "
                    f"(total_credits ${total:.4f} - total_usage ${used:.4f})"
                )
                warning = (
                    f"{BALANCE_WARNING} is ${balance:.4f} (<= 0): requests to paid models will "
                    "likely be rejected with HTTP 402 (out of credits). Buy credits or enable "
                    f"auto top-up at {CREDITS_URL}. Continuing anyway (':free' models can still "
                    "work)."
                )
    return AccountStatus(
        provider=DISPLAY_NAME,
        balance=balance,
        limit=limit,
        limit_remaining=limit_remaining,
        limit_unlimited=unlimited,
        expires_at=expires_at,
        notes=tuple(notes),
        balance_notes=tuple(balance_notes),
        balance_warning=warning,
        details=details,
    )


@register_provider(NAME)
class OpenRouterProvider:
    display_name = DISPLAY_NAME

    def __init__(
        self,
        settings: Mapping[str, Any],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        validate_openrouter_settings(settings)
        env = settings.get("api_key_env", "OPENROUTER_API_KEY")
        api_key = os.environ.get(env)
        if not api_key:
            raise MissingAPIKeyError(
                f"{env} is not set. Export it (e.g. `export {env}=...`) to use the "
                "openrouter provider. Never commit keys."
            )
        self._api_key = api_key
        self.base_url = settings.get("base_url", "https://openrouter.ai/api/v1")
        self.timeout_s = settings.get("timeout_s", 120)
        self.request_deadline_s = float(
            settings.get("request_deadline_s", DEFAULT_REQUEST_DEADLINE_S)
        )
        self.stream_stall_timeout_s = float(
            settings.get("stream_stall_timeout_s", DEFAULT_STREAM_STALL_TIMEOUT_S)
        )
        self.provider_sort: str | None = settings.get("provider_sort")
        self.require_parameters: bool = settings.get("require_parameters") is True
        self.provider_ignore: tuple[str, ...] = tuple(settings.get("provider_ignore") or ())
        self.transport = transport

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "[REDACTED]")

    def _body(self, request: CompletionRequest) -> dict[str, Any]:
        msgs = [_wire_message(m) for m in request.messages]
        if request.cache_prefix:
            _mark_cache_prefix(msgs)
        body: dict[str, Any] = {
            "model": request.model,
            "messages": msgs,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "usage": {"include": True},
        }
        if request.stop:
            body["stop"] = request.stop
        if request.tools:
            body["tools"] = request.tools
            body["tool_choice"] = "auto"
        if request.response_format:
            body["response_format"] = request.response_format
        prefs: dict[str, Any] = {}
        if self.provider_sort:
            prefs["sort"] = self.provider_sort
        if self.require_parameters:
            prefs["require_parameters"] = True
        if self.provider_ignore:
            prefs["ignore"] = list(self.provider_ignore)
        if prefs:
            body["provider"] = prefs
        return body

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "X-Title": "CORA",
        }

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if 200 <= resp.status_code < 300:
            return
        body = self._redact(resp.text)[:BODY_MAX_CHARS]
        msg = f"openrouter HTTP {resp.status_code}: {body[:DETAIL_MAX_CHARS]}"
        if resp.status_code in ACCOUNT_STATUSES:
            raise ProviderAccountError(resp.status_code, msg, body=body, provider=NAME)
        raise ProviderError(msg)

    def _chunk_error(self, err: Any) -> ProviderError:
        raw = json.dumps(err, ensure_ascii=False) if isinstance(err, (dict, list)) else str(err)
        body = self._redact(raw)[:BODY_MAX_CHARS]
        msg = "openrouter stream error: " + self._redact(str(err))[:DETAIL_MAX_CHARS]
        code = err.get("code") if isinstance(err, dict) else None
        if code in ACCOUNT_STATUSES:
            return ProviderAccountError(int(code), msg, body=body, provider=NAME)
        return ProviderError(msg)

    async def account_get(self, path: str) -> tuple[int, Any]:
        """GET an account endpoint ('/auth/key', '/credits'); no retries.

        Returns (status, parsed JSON or None). Network errors raise a redacted ProviderError.
        """
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=ACCOUNT_TIMEOUT_S, transport=self.transport
            ) as client:
                resp = await client.get(url, headers=self._headers())
        except httpx.HTTPError as e:
            raise ProviderError(
                self._redact(f"openrouter request failed: {type(e).__name__}: {e}")
            ) from None
        try:
            data = resp.json()
        except ValueError:
            data = None
        return resp.status_code, data

    async def account_status(self) -> AccountStatus:
        return await openrouter_account_status(self.account_get)

    def _response(
        self,
        request: CompletionRequest,
        text: str,
        usage: dict,
        model: str,
        tool_calls: tuple[NativeToolCall, ...] = (),
        finish_reason: str | None = None,
    ) -> CompletionResponse:
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        if input_tokens is None:
            input_tokens = messages_tokens(request.messages)
        if output_tokens is None:
            output_tokens = estimate_tokens(text + "".join(c.arguments for c in tool_calls))
        return CompletionResponse(
            text=text,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            model=model,
            tool_calls=tuple(tool_calls),
            cost_usd=_usage_cost(usage),
            cached_input_tokens=_cached_tokens(usage),
            finish_reason=finish_reason,
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        body = self._body(request)
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self.transport
            ) as client:
                resp = await self._post_with_retry(client, url, body, self._headers())
        except httpx.HTTPError as e:
            raise ProviderError(
                self._redact(f"openrouter request failed: {type(e).__name__}: {e}")
            ) from None
        self._raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError:
            raise ProviderError("openrouter returned invalid JSON") from None
        if not data.get("choices"):
            raise ProviderError(
                self._redact(
                    f"openrouter response without choices: {str(data.get('error'))[:300]}"
                )
            )
        msg = data["choices"][0].get("message") or {}
        text = msg.get("content") or ""
        tool_calls = _parse_tool_calls(msg.get("tool_calls"))
        model = data.get("model", request.model)
        fr = data["choices"][0].get("finish_reason")
        return self._response(
            request,
            text,
            data.get("usage", {}),
            model,
            tool_calls,
            finish_reason=fr if isinstance(fr, str) else None,
        )

    async def stream(
        self, request: CompletionRequest, on_text: Callable[[str], None]
    ) -> CompletionResponse:
        body = self._body(request)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        url = f"{self.base_url}/chat/completions"
        emitted = False

        def emit(text: str) -> None:
            nonlocal emitted
            emitted = True
            on_text(text)

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self.transport
            ) as client:
                attempt = 0
                while True:
                    last = attempt >= len(RETRY_DELAYS_S)
                    try:
                        return await self._stream_once(
                            client, url, body, request, emit, last_attempt=last
                        )
                    except _RetryableStatus:
                        pass
                    except httpx.TransportError:
                        if emitted or last:
                            raise
                    await _sleep(RETRY_DELAYS_S[attempt])
                    attempt += 1
        except httpx.HTTPError as e:
            raise ProviderError(
                self._redact(f"openrouter request failed: {type(e).__name__}: {e}")
            ) from None

    async def _stream_once(
        self,
        client: httpx.AsyncClient,
        url: str,
        body: dict[str, Any],
        request: CompletionRequest,
        emit: Callable[[str], None],
        *,
        last_attempt: bool,
    ) -> CompletionResponse:
        try:
            async with asyncio.timeout(self.request_deadline_s):
                req = client.build_request("POST", url, json=body, headers=self._headers())
                resp = await client.send(req, stream=True)
                try:
                    if (resp.status_code == 429 or resp.status_code >= 500) and not last_attempt:
                        raise _RetryableStatus()
                    if not (200 <= resp.status_code < 300):
                        await resp.aread()
                        self._raise_for_status(resp)
                    return await self._read_sse(resp, request, emit)
                finally:
                    await resp.aclose()
        except TimeoutError:
            raise RequestDeadlineExceeded(
                f"no complete response within request_deadline_s={self.request_deadline_s:g}s"
            ) from None

    async def _read_sse(
        self, resp: httpx.Response, request: CompletionRequest, emit: Callable[[str], None]
    ) -> CompletionResponse:
        parts: list[str] = []
        usage: dict[str, Any] = {}
        model = request.model
        acc: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
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
                if "error" in chunk:
                    raise self._chunk_error(chunk["error"])
                if chunk.get("usage"):
                    usage = chunk["usage"]
                model = chunk.get("model", model)
                for choice in chunk.get("choices") or []:
                    if isinstance(choice.get("finish_reason"), str):
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        parts.append(content)
                        emit(content)
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index", 0))
                        slot = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
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
        finally:
            await lines.aclose()
        calls = tuple(
            NativeToolCall(s["id"] or f"call_{i}", s["name"], s["arguments"])
            for i, s in sorted(acc.items())
        )
        return self._response(
            request, "".join(parts), usage, model, calls, finish_reason=finish_reason
        )

    async def _send_with_deadline(
        self, client: httpx.AsyncClient, req: httpx.Request
    ) -> httpx.Response:
        try:
            async with asyncio.timeout(self.request_deadline_s):
                return await client.send(req)
        except TimeoutError:
            raise RequestDeadlineExceeded(
                f"no complete response within request_deadline_s={self.request_deadline_s:g}s"
            ) from None

    async def _post_with_retry(
        self, client: httpx.AsyncClient, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                req = client.build_request("POST", url, json=body, headers=headers)
                resp = await self._send_with_deadline(client, req)
            except httpx.TransportError:
                if attempt >= len(RETRY_DELAYS_S):
                    raise
            else:
                retryable = resp.status_code == 429 or resp.status_code >= 500
                if not retryable or attempt >= len(RETRY_DELAYS_S):
                    return resp
            await _sleep(RETRY_DELAYS_S[attempt])
            attempt += 1
