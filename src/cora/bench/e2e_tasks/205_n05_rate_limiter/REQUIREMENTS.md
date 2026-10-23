# Token-bucket rate limiter

Finish the `throttle` package. `throttle/__init__.py` and `throttle/clock.py` are done.
`FakeClock()` is a clock you can move with `advance(dt)`; its call returns the current time in seconds.

## `throttle/bucket.py`: `TokenBucket(capacity, refill_per_s, clock=time.monotonic)`

- The bucket starts full.
- It refills continuously at `refill_per_s` tokens per second, capped at `capacity`.
- `tokens` (property): the current token count after refill. It is a float.
- `allow(cost=1) -> bool`: if `tokens >= cost`, subtract `cost` and return True. Otherwise return False and consume nothing.
- `wait_time(cost=1) -> float`: 0.0 if `tokens >= cost`, else `(cost - tokens) / refill_per_s`.
- `capacity <= 0` or `refill_per_s <= 0` raises `ValueError`.
- `allow` and `wait_time` raise `ValueError` when `cost <= 0` or `cost > capacity`.

## `throttle/keyed.py`: `KeyedLimiter(capacity, refill_per_s, idle_ttl_s, clock=time.monotonic)`

- Keep one `TokenBucket` per key, with the same `capacity`, `refill_per_s` and `clock`. Create it full on first use.
- `allow(key, cost=1) -> bool`: use the key's bucket, with the same return value as `TokenBucket.allow`.
- Idle eviction: a key whose last `allow` call was at least `idle_ttl_s` seconds ago is dropped. Check this at the start of every `allow` call and every `active_keys` call.
- A dropped key starts full again on its next `allow`.
- `active_keys() -> list[str]`: the keys still held, sorted.

Example with `capacity=2`: `allow("a")`, `allow("a")` and `allow("a")` return True, True, False. Then `allow("b")` returns True. `active_keys()` returns `["a", "b"]`.
