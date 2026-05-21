"""
Prompt-keyed LLM response cache backed by PostgreSQL.

Two API shapes:

  Low-level (legacy callers — get/set explicitly):
      key = make_cache_key("guided_open", MODEL, {"target_word": w, "language": l})
      cached = await get_cached(pool, key)
      if cached is None:
          result = await llm_service.some_call(...)
          await set_cached(pool, key, "guided_open", MODEL, result)

  High-level (recommended — #24 thundering-herd safe):
      result = await get_or_compute(
          pool, key, "guided_open", MODEL,
          compute=lambda: llm_service.some_call(...),
      )

Cache hit path: single UPDATE...RETURNING (atomic increment + fetch).
Cache miss path: INSERT ON CONFLICT DO NOTHING (safe for concurrent writers).

Thundering-herd guard (#24): get_or_compute serialises concurrent callers
of the same cache_key on a per-key asyncio.Lock so the provider is invoked
exactly once. Different keys do not block each other. Lock objects are
in-process — multi-worker deployments need a distributed lock (Redis /
Postgres advisory) to coordinate across processes; documented limitation.

Bump _CACHE_VERSION to invalidate all existing entries at once.
"""
import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import asyncpg

_CACHE_VERSION = "v1"

# ---------------------------------------------------------------------------
# Per-key locks (#24 — prevent thundering herd on concurrent cache misses)
# ---------------------------------------------------------------------------

# cache_key -> Lock used to serialise concurrent fills of that key. Lock objects
# stay in the dict for the process lifetime; the set of distinct cache keys is
# bounded by the llm_cache table itself, and a Lock costs ~100 bytes. Trading
# memory for simplicity — periodic cleanup is the next step if it ever matters.
_locks: dict[str, asyncio.Lock] = {}
# Guards the _locks dict itself so two coroutines racing to look up the same
# key get the SAME Lock object back.
_locks_guard = asyncio.Lock()


async def _get_lock(cache_key: str) -> asyncio.Lock:
    """Return the per-key Lock for cache_key, creating it if missing."""
    async with _locks_guard:
        lock = _locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            _locks[cache_key] = lock
        return lock


def reset_for_tests() -> None:
    """Drop every per-key Lock. Test-only — production code never calls this.

    Useful when a test wants a clean slate (e.g. asserting that a specific
    Lock instance was used). Per-test keys are uuid4-suffixed so leaks are
    harmless in normal test runs.
    """
    _locks.clear()


def make_cache_key(prompt_key: str, model: str, params: dict) -> str:
    """
    Produce a stable, collision-resistant cache key.

    Inputs are JSON-serialised with sorted keys and no whitespace so the
    result is independent of dict insertion order and Python version.
    The version prefix makes it trivial to invalidate all cached entries.
    """
    payload = json.dumps(
        {"v": _CACHE_VERSION, "pk": prompt_key, "m": model, "p": params},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


async def get_cached(pool: asyncpg.Pool, cache_key: str) -> dict | None:
    """
    Return the cached response dict for *cache_key*, or None on a miss.

    On a hit, atomically increments hit_count and updates last_hit_at.
    Entries whose expires_at is in the past are treated as misses.
    """
    row = await pool.fetchrow(
        """
        UPDATE llm_cache
        SET hit_count   = hit_count + 1,
            last_hit_at = NOW()
        WHERE cache_key = $1
          AND (expires_at IS NULL OR expires_at > NOW())
        RETURNING response
        """,
        cache_key,
    )
    if row is None:
        return None
    raw = row["response"]
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


async def set_cached(
    pool: asyncpg.Pool,
    cache_key: str,
    prompt_key: str,
    model: str,
    response: dict,
    *,
    ttl_seconds: int | None = None,
) -> None:
    """
    Store *response* under *cache_key*.

    Uses ON CONFLICT DO NOTHING so concurrent writers are safe — the first
    successful insert wins and subsequent ones silently no-op.
    Pass ttl_seconds to create an expiring entry; omit for a permanent one.
    """
    expires_at: datetime | None = None
    if ttl_seconds is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    await pool.execute(
        """
        INSERT INTO llm_cache (cache_key, prompt_key, model, response, expires_at)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (cache_key) DO NOTHING
        """,
        cache_key,
        prompt_key,
        model,
        json.dumps(response),
        expires_at,
    )


# ---------------------------------------------------------------------------
# Thundering-herd-safe wrapper (#24)
# ---------------------------------------------------------------------------

async def get_or_compute(
    pool: asyncpg.Pool,
    cache_key: str,
    prompt_key: str,
    model: str,
    compute: Callable[[], Awaitable[dict]],
    *,
    ttl_seconds: int | None = None,
) -> dict:
    """Return the cached response for cache_key, computing it on miss.

    Thundering-herd safe: concurrent callers for the same cache_key serialise
    on a per-key asyncio.Lock, so `compute()` is invoked at most once across
    a wave of misses. Different cache_keys do not block each other.

    Flow:
      1. Fast path — call get_cached. On hit, return without touching the lock.
      2. On miss, acquire the per-key lock.
      3. Re-check the cache inside the lock (another waiter may have filled
         it while we were queued).
      4. Still missing → call compute(), persist via set_cached, return.

    Exception handling:
      - If compute() raises, the lock is released (no entry written) and a
        subsequent caller will re-attempt compute on its own double-check.
      - If set_cached raises (very rare — INSERT ON CONFLICT DO NOTHING), the
        lock is still released; subsequent callers will see the same miss and
        try again. The compute result we just produced is lost; acceptable
        because the alternative is hanging the wave indefinitely.

    Args:
        pool:         asyncpg connection pool used by get_cached / set_cached.
        cache_key:    the make_cache_key() output. Must be stable for the
                      same inputs.
        prompt_key:   the high-level prompt category (matches make_cache_key
                      input). Stored on the row for analytics.
        model:        model identifier. Stored on the row for analytics.
        compute:      async no-arg function that returns the dict to cache.
                      Invoked at most once per concurrent wave per cache_key.
        ttl_seconds:  optional TTL forwarded to set_cached. Omit for a
                      permanent entry.

    Returns:
        The cached response dict (either freshly computed or read from cache).
    """
    # 1. Fast path — no lock needed if the cache already has the answer.
    cached = await get_cached(pool, cache_key)
    if cached is not None:
        return cached

    lock = await _get_lock(cache_key)
    async with lock:
        # 2. Double-check — another coroutine may have filled the entry while
        #    we were waiting for the lock. This is the load-bearing step that
        #    makes the wave see only ONE compute() call.
        cached = await get_cached(pool, cache_key)
        if cached is not None:
            return cached

        # 3. Still missing — invoke the provider exactly once.
        result = await compute()

        # 4. Persist before releasing the lock so subsequent waiters' double-
        #    check hits.
        await set_cached(
            pool, cache_key, prompt_key, model, result,
            ttl_seconds=ttl_seconds,
        )
        return result
