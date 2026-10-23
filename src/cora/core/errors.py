from __future__ import annotations

import json
from collections.abc import Callable, Sequence


class CoraError(Exception): ...


class ConfigError(CoraError): ...


class ReplayMissError(ConfigError):
    def __init__(self, key: str, model: str, path: str) -> None:
        self.key, self.model, self.path = key, model, path
        super().__init__(
            f"replay miss: no recording for model '{model}' key {key} (expected {path}); "
            "the request changed since it was recorded - re-record with CORA_RECORD_MODE=record"
        )


class MissingAPIKeyError(CoraError): ...


class ProviderError(CoraError): ...


AccountGuidance = Callable[[int, str], Sequence[str]]
_ACCOUNT_GUIDANCE: dict[str, AccountGuidance] = {}


def register_account_guidance(name: str) -> Callable[[AccountGuidance], AccountGuidance]:
    """Register provider `name`'s 401/402/403 explanation: fn(status, body) -> lines."""

    def decorator(fn: AccountGuidance) -> AccountGuidance:
        _ACCOUNT_GUIDANCE[name] = fn
        return fn

    return decorator


def _generic_guidance(status: int, provider: str | None) -> list[str]:
    who = provider or "the provider"
    return [
        f"Account error from {who} (HTTP {status}): the API key or account cannot make "
        "this request.",
        f"Fix: check the API key and the account (balance, limits, access) for {who}.",
    ]


ACCOUNT_STATUSES = (401, 402, 403)
DETAIL_MAX_CHARS = 300
BODY_MAX_CHARS = 4000


class ProviderAccountError(ProviderError):
    """HTTP 401/402/403: the key or account cannot make further calls."""

    def __init__(
        self, status: int, message: str, *, body: str | None = None, provider: str = ""
    ) -> None:
        """body: redacted raw response body (may be None).

        provider: registry name of the raising provider ("" if unknown).
        """
        super().__init__(message)
        self.status = status
        self.body = body
        self.provider = provider


def trim_detail(text: str, limit: int = DETAIL_MAX_CHARS) -> str:
    s = text.strip()
    try:
        data = json.loads(s)
    except ValueError:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        msg = err.get("message") if isinstance(err, dict) else data.get("message")
        if isinstance(msg, str) and msg.strip():
            s = msg
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


def account_guidance(status: int, body: str | None = None, *, provider: str | None = None) -> str:
    text = body or ""
    lines: list[str] | None = None
    fn = _ACCOUNT_GUIDANCE.get(provider) if provider else None
    if fn is not None:
        try:
            lines = [str(x) for x in fn(status, text)]
        except Exception:
            lines = None
    if lines is None:
        lines = _generic_guidance(status, provider)
    detail = trim_detail(text) if text.strip() else ""
    lines.append(f"HTTP {status}: {detail}" if detail else f"HTTP {status}")
    return "\n".join(lines)


def describe_provider_error(exc: BaseException) -> str:
    if isinstance(exc, ProviderAccountError):
        return account_guidance(
            exc.status,
            exc.body if exc.body is not None else str(exc),
            provider=exc.provider or None,
        )
    return str(exc)


class WorkspaceViolation(CoraError): ...


class InvalidTransition(CoraError): ...
