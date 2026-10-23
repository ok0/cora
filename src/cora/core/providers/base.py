from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

from cora.core.config import CoraConfig, effective_record_settings, secret_env_names
from cora.core.errors import (
    ConfigError,
    ProviderError,
    register_account_guidance,  # noqa: F401  (re-export)
)
from cora.core.types import CompletionRequest, CompletionResponse

T = TypeVar("T")
CALL_TIMEOUT_RETRIES = 1


class Provider(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...


class StreamingProvider(Provider, Protocol):
    async def stream(
        self, request: CompletionRequest, on_text: Callable[[str], None]
    ) -> CompletionResponse: ...


@dataclass(frozen=True)
class AccountStatus:
    """Provider-neutral account snapshot returned by the optional account_status() capability.

    preflight interprets only: expires_at (<= now: refuse), limit_remaining (< run cap: refuse),
    limit_unlimited (info line), balance (<= 0: warn). Text fields are provider-formatted,
    already redacted, and printed verbatim.
    """

    provider: str  # display name, e.g. "OpenRouter"
    balance: float | None = None  # prepaid balance in USD
    limit: float | None = None  # key/spend limit in USD
    limit_remaining: float | None = None  # remaining key/spend limit in USD
    limit_unlimited: bool = False  # the provider reported "no key limit"
    expires_at: datetime | None = None  # key expiry (tz-aware preferred)
    notes: tuple[str, ...] = ()  # printed before the limit line
    balance_notes: tuple[str, ...] = ()  # printed after the limit line
    balance_warning: str | None = None  # wording used when balance <= 0
    details: dict[str, float] | None = None  # provider-specific figures (info only)


class AccountStatusProvider(Protocol):
    """Optional capability. Return None if the provider has no account concept; raise
    ProviderAccountError(provider=<name>) on HTTP 401/402/403."""

    async def account_status(self) -> AccountStatus | None: ...


def account_capability(provider: object) -> Callable[[], Awaitable[AccountStatus | None]] | None:
    fn = getattr(provider, "account_status", None)
    return fn if callable(fn) else None


ProviderFactory = Callable[[Mapping[str, Any]], Provider]
_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str) -> Callable[[T], T]:
    def decorator(factory: T) -> T:
        _REGISTRY[name] = factory  # type: ignore[assignment]
        return factory

    return decorator


def _factory_for(name: str, settings: Mapping[str, Any]) -> ProviderFactory:
    kind = settings.get("type", name)
    if not isinstance(kind, str):
        raise ConfigError(f"invalid [providers.{name}].type: must be a string")
    factory = _REGISTRY.get(kind)
    if factory is None:
        if kind == name:
            raise ConfigError(f"unknown provider '{name}'; registered: {sorted(_REGISTRY)}")
        registered = sorted(_REGISTRY)
        raise ConfigError(
            f"unknown provider type '{kind}' for [providers.{name}]; registered: {registered}"
        )
    return factory


def create_provider(name: str, settings: Mapping[str, Any]) -> Provider:
    return _factory_for(name, settings)(settings)


ProviderEventSink = Callable[[str, dict[str, Any]], None]
_EVENT_SINK: ContextVar[ProviderEventSink | None] = ContextVar(
    "cora_provider_event_sink", default=None
)


def emit_provider_event(kind: str, **data: Any) -> None:
    sink = _EVENT_SINK.get()
    if sink is None:
        return
    with contextlib.suppress(Exception):
        sink(kind, data)


@contextlib.contextmanager
def provider_events(sink: ProviderEventSink | None) -> Iterator[None]:
    token = _EVENT_SINK.set(sink)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


_WORKSPACE: ContextVar[Path | None] = ContextVar("cora_provider_workspace", default=None)


@contextlib.contextmanager
def provider_workspace(path: Path | None) -> Iterator[None]:
    token = _WORKSPACE.set(path)
    try:
        yield
    finally:
        _WORKSPACE.reset(token)


def current_workspace() -> Path | None:
    return _WORKSPACE.get()


def registered_providers() -> list[str]:
    return sorted(_REGISTRY)


class ProviderPool:
    def __init__(self, config: CoraConfig) -> None:
        self._settings: dict[str, Mapping[str, Any]] = {}
        for spec in config.models:
            name = spec.provider
            if name in self._settings:
                continue
            s = config.providers.get(name, {})
            if not isinstance(s, Mapping):
                s = {}
            _factory_for(name, s)
            self._settings[name] = s
        self._providers: dict[str, Provider] = {}
        self._record = effective_record_settings(config.record)
        if self._record.mode != "off":
            self._secrets: tuple[str, ...] = tuple(
                v
                for n in sorted(secret_env_names(config))
                if (v := os.environ.get(n)) and len(v) >= 8
            )
        else:
            self._secrets = ()

    def get(self, name: str) -> Provider:
        cached = self._providers.get(name)
        if cached is not None:
            return cached
        if name not in self._settings:
            raise KeyError(name)
        if self._record.mode == "off":
            provider = create_provider(name, self._settings[name])
        else:
            from cora.core.providers.recording import wrap_provider

            provider = wrap_provider(
                name, self._settings[name], self._record, secrets=self._secrets
            )
        self._providers[name] = provider
        return provider


class ProviderTimeout(ProviderError):
    def __init__(self, model: str, timeout_s: float, *, attempts: int, wall_limited: bool) -> None:
        self.model = model
        self.timeout_s = timeout_s
        self.attempts = attempts
        self.wall_limited = wall_limited
        super().__init__(
            f"model call to {model} timed out after {attempts} attempt(s) of up to {timeout_s:g}s"
        )


async def call_with_timeout[T](
    fn: Callable[[], Awaitable[T]],
    *,
    model: str,
    timeout_s: float,
    budget_s: float | None = None,
    retries: int = CALL_TIMEOUT_RETRIES,
) -> T:
    loop = asyncio.get_running_loop()
    remaining = budget_s
    for attempt in range(retries + 1):
        limit = timeout_s if remaining is None else min(timeout_s, remaining)
        if limit <= 0:
            raise ProviderTimeout(model, timeout_s, attempts=attempt, wall_limited=True)
        t0 = loop.time()
        try:
            async with asyncio.timeout(limit) as cm:
                return await fn()
        except TimeoutError:
            if not cm.expired():
                raise
        wall_limited = remaining is not None and limit < timeout_s
        if remaining is not None:
            remaining -= loop.time() - t0
        emit_provider_event(
            "call_timeout", attempt=attempt + 1, timeout_s=limit, wall_limited=wall_limited
        )
        if wall_limited:
            raise ProviderTimeout(model, timeout_s, attempts=attempt + 1, wall_limited=True)
    raise ProviderTimeout(model, timeout_s, attempts=retries + 1, wall_limited=False)
