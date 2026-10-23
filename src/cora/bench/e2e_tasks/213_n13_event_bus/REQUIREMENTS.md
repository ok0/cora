# In-process event bus

Build a small publish/subscribe bus in the `evbus` package in this directory. Some functions are
stubs that raise `NotImplementedError`; implement them. Keep `evbus/__init__.py` and
`evbus/errors.py` as they are.

## Topics and patterns (`evbus/topics.py`)

- A topic is one or more segments separated by `.`. Each segment is non-empty and uses only
  `a-z`, `0-9` and `_`. `validate_topic(t)` raises `ValueError(f"bad topic '{t}'")` otherwise.
  Bad examples: `""`, `"a..b"`, `"A.b"`, `"a-b"`, `"a.*"`.
- A pattern uses the same segments plus two wildcards: `*` matches exactly one segment, and `#`
  matches zero or more segments and may only be the last segment. `validate_pattern(p)` raises
  `ValueError(f"bad pattern '{p}'")` otherwise. `"a.#.b"` is bad. `"#"` and `"a.*.#"` are good.
- `matches(pattern, topic) -> bool` says whether a valid pattern matches a valid topic:
  - `"a.*"` matches `a.b`, but not `a` or `a.b.c`.
  - `"a.*.c"` matches `a.b.c`.
  - `"orders.#"` matches `orders`, `orders.a` and `orders.a.b`, but not `order`.
  - `"#"` matches every topic.

## History (`evbus/history.py`)

- `History(maxlen)` keeps the last `maxlen` recorded events. `History(-1)` raises `ValueError`.
- `record(topic, payload)` appends an event and drops the oldest one when more than `maxlen` are
  kept.
- `matching(pattern)` returns the `(topic, payload)` pairs whose topic matches the pattern, oldest
  first.

## Bus (`evbus/bus.py`)

- `Bus(history=0)`: with `history > 0`, the last `history` published events are kept.
- `subscribe(pattern, handler, *, priority=0, once=False, replay=False) -> int` returns a token.
  Tokens are 1, 2, 3, ... per bus. A handler is called as `handler(topic, payload)`.
- `unsubscribe(token) -> bool` returns True if the token was active and is now removed. It returns
  False for an unknown or already removed token.
- `publish(topic, payload=None) -> int` returns the number of handlers called.

Delivery rules:

- Handlers run by priority, highest first. Equal priorities run in subscription order. Example:
  subscribers with priorities 0, 5, 5, -1 (subscribed in that order) run as the 5, the second 5,
  the 0, then the -1.
- The subscriber list is taken when `publish` starts. A subscriber added during a publish is not
  called by that publish. A subscriber removed during a publish is still called by that publish.
- A handler that raises does not stop delivery. After all matching handlers have run, if any
  raised, `publish` raises `DispatchError`. Its `errors` attribute is a list of
  `(token, exception)` pairs in call order. If none raised, `publish` returns the count.
- A `once=True` subscription is removed after its first delivery, even if its handler raised.
- With `history > 0`, each published event is recorded before its handlers are called.
- `replay=True` delivers the recorded events that match the pattern to the new handler during
  `subscribe`, oldest first. With `once=True`, only the oldest matching recorded event is delivered,
  and the subscription is then removed.
