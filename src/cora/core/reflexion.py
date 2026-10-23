from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence

from cora.core.prompts import REFLECT_TEMPLATE
from cora.core.types import Message


def limit_sentences(text: str, n: int) -> str:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    return " ".join(parts[:n])


async def reflect(
    call: Callable[[list[Message]], Awaitable[str]],
    task: str,
    trajectory: Sequence[Message],
    failure: str,
    *,
    max_sentences: int | None = None,
) -> str:
    traj = "\n".join(f"{m.role}: {m.content}" for m in trajectory[-6:])[-3000:]
    prompt = REFLECT_TEMPLATE.format(task=task, trajectory=traj, failure=failure[-2000:])
    text = (await call([Message("user", prompt)])).strip()
    result = text or "(no reflection)"
    if max_sentences is not None:
        result = limit_sentences(result, max_sentences) or "(no reflection)"
    return result
