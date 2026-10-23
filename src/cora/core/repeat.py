from __future__ import annotations

from dataclasses import dataclass

REPEAT_TEMPERATURE = 0.7
FEEDBACK_AT = 2
BOOST_FROM = 3
Failure = tuple[str, str | None]


def normalize_reply(text: str) -> str:
    return " ".join(text.split("\nObservation:")[0].split())


@dataclass(frozen=True)
class RepeatSignal:
    kind: str
    count: int
    feedback: bool
    boost: bool


class RepeatTracker:
    def __init__(self) -> None:
        self._prev_text: str | None = None
        self._prev_failure: Failure | None = None
        self._key: tuple[str, str | None] | None = None
        self._count = 0

    def observe(self, text: str, failure: Failure | None) -> RepeatSignal | None:
        norm = normalize_reply(text)
        key: tuple[str, str | None] | None
        if failure is not None and failure == self._prev_failure:
            key = failure
        elif self._prev_text is not None and norm == self._prev_text:
            key = ("same_reply", None)
        else:
            key = None
        self._prev_text, self._prev_failure = norm, failure
        if key is None:
            self._key, self._count = None, 0
            return None
        if key == self._key:
            self._count += 1
        else:
            self._key, self._count = key, 2
        return RepeatSignal(
            key[0], self._count, self._count == FEEDBACK_AT, self._count >= BOOST_FROM
        )
