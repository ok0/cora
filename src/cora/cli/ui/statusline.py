from __future__ import annotations

import time

from rich.cells import cell_len

from cora.cli.ui.state import UiState

INTERRUPT_HINT = "Ctrl+C to interrupt"


def with_interrupt_hint(text: str) -> str:
    return f"{text} ({INTERRUPT_HINT})"


def fit(text: str, width: int, ellipsis: str) -> str:
    if width <= 0:
        return ""
    if cell_len(text) <= width:
        return text
    if cell_len(ellipsis) >= width:
        return ellipsis[:width]
    cut = text
    while cell_len(cut) + cell_len(ellipsis) > width:
        cut = cut[:-1]
    return cut + ellipsis


def context_percent(tokens: int | None, context: int | None) -> float | None:
    if tokens is None or context is None or context <= 0:
        return None
    return min(100.0, 100.0 * tokens / context)


def fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def statusline(ui: UiState, width: int, now: float | None = None) -> str:
    elapsed = fmt_elapsed((now if now is not None else time.monotonic()) - ui.started)
    flag_states = (("plan", ui.plan), ("check", ui.check), ("delegate", ui.delegate))
    modes = [name for name, on in flag_states if on]
    modes.append(f"todo:{'on' if ui.show_todos else 'off'}")
    items: list[tuple[int, str]] = [
        (0, f"approval:{ui.approval}"),
        (2, ui.model or "model:-"),
        (3, f"${ui.cost_usd:.4f}" if ui.cost_usd is not None else "$-"),
        (4, f"ctx {ui.context_pct:.0f}%" if ui.context_pct is not None else "ctx -"),
        (1, " ".join(modes)),
    ]
    if ui.groups:
        items.append((6, "tools:" + ",".join(ui.groups)))
    if ui.mouse is not None:
        items.append((1, f"mouse:{'on' if ui.mouse else 'off'}"))
    if ui.unseen:
        items.append((0, "v new output" if ui.glyphs.ascii else "↓ new output"))
    items.append((5, elapsed))

    def joined() -> str:
        return f" {ui.glyphs.sep} ".join(text.replace("\n", " ") for _, text in items)

    while len(items) > 1 and cell_len(joined()) > width:
        items.remove(max(items, key=lambda item: item[0]))
    return fit(joined(), width, ui.glyphs.ellipsis)
