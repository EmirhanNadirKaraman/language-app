"""
Prompt-keyed LLM response cache backed by PostgreSQL.

Usage:
    key = make_cache_key("guided_open", MODEL, {"target_word": w, "language": l})
    cached = await get_cached(pool, key)
    if cached is None:
        result = await llm_service.some_call(...)
        await set_cached(pool, key, "guided_open", MODEL, result)

Cache hit path: single UPDATE...RETURNING (atomic increment + fetch).
Cache miss path: INSERT ON CONFLICT DO NOTHING (safe for concurrent writers).

Bump _CACHE_VERSION to invalidate all existing entries at once.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import asyncpg

_CACHE_VERSION = "v1"


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
