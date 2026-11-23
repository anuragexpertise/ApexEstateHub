"""Small thread-safe sliding-window rate limiter.

Counts are kept per gunicorn worker (in process memory), so the effective
limit across N workers is up to N x max_calls. That is adequate to blunt
abuse of CPU-heavy or push-triggering endpoints; use Redis-backed limiting
if you need an exact global limit.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_buckets: dict[str, list[float]] = {}
_MAX_KEYS = 10_000


def rate_ok(key: str, max_calls: int, window: float) -> bool:
    """Return True and record the call if under the limit, else False."""
    now = time.monotonic()
    with _lock:
        if len(_buckets) > _MAX_KEYS:  # bound memory: drop idle keys
            for k in [k for k, v in _buckets.items() if not v or now - v[-1] > window]:
                _buckets.pop(k, None)
        times = [t for t in _buckets.get(key, ()) if now - t < window]
        if len(times) >= max_calls:
            _buckets[key] = times
            return False
        times.append(now)
        _buckets[key] = times
        return True


def reset(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _buckets.clear()
        else:
            _buckets.pop(key, None)
