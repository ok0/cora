"""Live bench preflight: per-provider account checks through the optional account_status
capability. Orchestration only; provider-specific wording comes from the providers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cora.core.errors import CoraError, ProviderAccountError, account_guidance
from cora.core.providers import AccountStatus, account_capability

KEY_CAP_NOTE = "key spending cap, not the account balance"
ACCOUNT_CHECK_TIMEOUT_S = 40.0  # whole capability call (may include two sequential 15 s GETs)


class PreflightRefused(CoraError): ...


@dataclass
class PreflightResult:
    limit_remaining: float | None = None  # smallest across providers
    credits: dict | None = None  # AccountStatus.details of the last provider that set it
    balance: float | None = None  # smallest across providers
    notices: list[str] = field(default_factory=list)
    statuses: dict[str, AccountStatus] = field(default_factory=dict)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def skip_line(name: str) -> str:
    return f"preflight: account check not available for {name}: skipped"


def _low_balance(status: AccountStatus, balance: float) -> str:
    return (
        f"preflight: WARNING: {status.provider} account balance is ${balance:.4f} (<= 0): "
        "paid requests will likely be rejected (out of credits). Continuing anyway."
    )


def _apply(
    name: str, status: AccountStatus, run_cap_usd: float, now: datetime, out: PreflightResult
) -> None:
    out.statuses[name] = status
    out.notices.extend(str(n) for n in status.notes)
    exp = status.expires_at
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp <= now:
            raise PreflightRefused(
                f"preflight: the API key expired at {exp.isoformat()}; not starting the live bench"
            )
    lr = _num(status.limit_remaining)
    if lr is not None:
        out.limit_remaining = lr if out.limit_remaining is None else min(out.limit_remaining, lr)
        if lr < run_cap_usd:
            raise PreflightRefused(
                f"preflight: key limit_remaining ${lr:.4f} is below this run's cap "
                f"${run_cap_usd:.4f} (--max-cost); lower --max-cost or raise the key limit "
                f"({KEY_CAP_NOTE})"
            )
        out.notices.append(
            f"preflight: key limit_remaining=${lr:.4f} >= run cap ${run_cap_usd:.4f} "
            f"({KEY_CAP_NOTE})"
        )
    elif status.limit_unlimited:
        out.notices.append(
            f"preflight: key limit_remaining=unlimited ({KEY_CAP_NOTE}); "
            f"run cap ${run_cap_usd:.4f}"
        )
    out.notices.extend(str(n) for n in status.balance_notes)
    if status.details is not None:
        out.credits = dict(status.details)
    balance = _num(status.balance)
    if balance is not None:
        out.balance = balance if out.balance is None else min(out.balance, balance)
        if balance <= 0:
            out.notices.append(status.balance_warning or _low_balance(status, balance))


async def run_preflight(
    providers: Mapping[str, Any],
    run_cap_usd: float,
    *,
    now: datetime | None = None,
    timeout_s: float = ACCOUNT_CHECK_TIMEOUT_S,
) -> PreflightResult:
    """providers: provider name -> provider object (or None), only providers used by the run."""
    now = now or datetime.now(UTC)
    out = PreflightResult()
    for name, target in providers.items():
        check = account_capability(target)
        if check is None:
            out.notices.append(skip_line(name))
            continue
        try:
            async with asyncio.timeout(timeout_s):
                status = await check()
        except ProviderAccountError as e:
            who = getattr(target, "display_name", None) or name
            raise PreflightRefused(
                f"preflight: {who} refused the key check (HTTP {e.status}); "
                "not starting the live bench\n"
                + account_guidance(e.status, provider=e.provider or name)
            ) from None
        except TimeoutError:
            out.notices.append(
                f"preflight: account check for {name} timed out after {timeout_s:g}s; continuing"
            )
            continue
        except Exception as e:
            out.notices.append(
                f"preflight: account check for {name} failed ({type(e).__name__}); continuing"
            )
            continue
        if status is None:
            out.notices.append(skip_line(name))
            continue
        if not isinstance(status, AccountStatus):
            out.notices.append(
                f"preflight: account check for {name} failed (unexpected result); continuing"
            )
            continue
        _apply(name, status, run_cap_usd, now, out)
    return out
