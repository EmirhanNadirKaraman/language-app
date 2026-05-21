"""
Per-user sliding-window LLM rate limiter (#12).

Why this exists
---------------
LLM-backed routes (chat, translate, explain, SRS production review, prep
examples/grammar explanation, book LLM repair) hit Anthropic per call.
Without throttling, a single user can run the bill up or starve the org-wide
quota in minutes. This limiter caps the per-user rate before the route body
runs.

Implementation
--------------
- One sliding-window deque[float] per user_id.
- Two thresholds:
    PER_MINUTE_DEFAULT = 30   requests in the last 60 seconds
    PER_HOUR_DEFAULT   = 400  requests in the last 3600 seconds
- Old timestamps are pruned on every check (no separate sweeper task).
- `asyncio.Lock` serialises check-and-record so concurrent requests from the
  same user can't both squeak past the limit.

NOT YET IMPLEMENTED (intentionally deferred — see CLAUDE.md sharp edges):
  * Multi-process backend. The state is in-process; a second uvicorn worker
    gets its own deque and effectively doubles the limit. Move to Redis or
    a single dedicated rate-limit worker before scaling out. The
    `check_and_record` signature is shaped so a Redis backend can drop in
    behind the same call site.
  * Per-endpoint differentiation. Today every protected route shares one
    bucket per user. If we ever want lighter limits for cheap endpoints
    (e.g. cached translate) and tighter for expensive ones (batch repair),
    pass a `bucket` argument through `check_and_record`.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, status

PER_MINUTE_DEFAULT = 30
PER_HOUR_DEFAULT   = 400

_windows: dict[str, deque[float]] = defaultdict(deque)
_lock = asyncio.Lock()


async def check_and_record(
    user_id: str,
    *,
    per_minute: int | None = None,
    per_hour:   int | None = None,
) -> None:
    """Raise HTTPException(429) if *user_id* exceeds either window, else
    record the current timestamp.

    Per-minute breach → detail='rate_limit_minute', Retry-After=60.
    Per-hour breach   → detail='rate_limit_hour',   Retry-After=3600.

    The lock guarantees serialised state mutation. Two requests racing in
    at exactly the same instant can't both pass when the user is at the
    edge of the limit — at most one wins, the other gets 429.

    Defaults are read from the module-level constants at *call time* (not
    capture time), so tests can monkeypatch `PER_MINUTE_DEFAULT` /
    `PER_HOUR_DEFAULT` to tighten the limits without re-wiring the
    dependency.
    """
    # Resolve at call time so test monkeypatching of the constants works.
    if per_minute is None:
        per_minute = PER_MINUTE_DEFAULT
    if per_hour is None:
        per_hour = PER_HOUR_DEFAULT

    now = monotonic()
    async with _lock:
        q = _windows[user_id]

        # Prune entries older than the largest window we care about.
        cutoff_hour = now - 3600
        while q and q[0] < cutoff_hour:
            q.popleft()

        if len(q) >= per_hour:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limit_hour",
                headers={"Retry-After": "3600"},
            )

        cutoff_minute = now - 60
        recent_minute = sum(1 for t in q if t >= cutoff_minute)
        if recent_minute >= per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limit_minute",
                headers={"Retry-After": "60"},
            )

        q.append(now)


def reset_for_tests() -> None:
    """Clear all in-memory state. Tests use this between cases to avoid
    leakage. Not a public API for the running app."""
    _windows.clear()
