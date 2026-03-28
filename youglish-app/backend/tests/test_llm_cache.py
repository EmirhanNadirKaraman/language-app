"""
LLM cache tests.

Pure unit tests (no DB):
  - make_cache_key determinism and sensitivity

Integration tests (real DB via db_pool fixture):
  - cache miss returns None
  - set then get returns the stored value
  - hit_count increments on repeated gets
  - ON CONFLICT DO NOTHING: second set_cached for the same key is silently ignored
  - expired entries are treated as misses
"""
import uuid


from backend.services.llm_cache_service import get_cached, make_cache_key, set_cached

# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------

def test_make_cache_key_is_deterministic():
    k1 = make_cache_key("guided_open", "model-x", {"a": 1, "b": 2})
    k2 = make_cache_key("guided_open", "model-x", {"b": 2, "a": 1})  # different insertion order
    assert k1 == k2


def test_make_cache_key_differs_on_prompt_key():
    k1 = make_cache_key("guided_open",   "model-x", {"w": "Hund"})
    k2 = make_cache_key("guided_close",  "model-x", {"w": "Hund"})
    assert k1 != k2


def test_make_cache_key_differs_on_model():
    k1 = make_cache_key("guided_open", "model-a", {"w": "Hund"})
    k2 = make_cache_key("guided_open", "model-b", {"w": "Hund"})
    assert k1 != k2


def test_make_cache_key_differs_on_params():
    k1 = make_cache_key("guided_open", "model-x", {"target_word": "laufen",  "language": "de"})
    k2 = make_cache_key("guided_open", "model-x", {"target_word": "rennen",  "language": "de"})
    k3 = make_cache_key("guided_open", "model-x", {"target_word": "laufen",  "language": "fr"})
    assert k1 != k2
    assert k1 != k3
    assert k2 != k3


def test_make_cache_key_returns_hex_string():
    k = make_cache_key("p", "m", {})
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)


# ---------------------------------------------------------------------------
# Integration tests — real DB
# ---------------------------------------------------------------------------

def _unique_key() -> str:
    """Return a cache key that is guaranteed not to exist yet."""
    return make_cache_key("test_prompt", "test-model", {"uuid": uuid.uuid4().hex})


async def test_cache_miss_returns_none(db_pool):
    result = await get_cached(db_pool, _unique_key())
    assert result is None


async def test_set_and_get_returns_stored_value(db_pool):
    key = _unique_key()
    payload = {"opening": "Hallo, wie geht es dir?", "extra": 42}

    await set_cached(db_pool, key, "test_prompt", "test-model", payload)

    result = await get_cached(db_pool, key)
    assert result == payload


async def test_hit_count_increments(db_pool):
    key = _unique_key()
    await set_cached(db_pool, key, "test_prompt", "test-model", {"v": 1})

    await get_cached(db_pool, key)
    await get_cached(db_pool, key)

    row = await db_pool.fetchrow(
        "SELECT hit_count FROM llm_cache WHERE cache_key = $1", key
    )
    assert row["hit_count"] == 2


async def test_last_hit_at_is_updated(db_pool):
    key = _unique_key()
    await set_cached(db_pool, key, "test_prompt", "test-model", {"v": 1})

    before = await db_pool.fetchrow(
        "SELECT last_hit_at FROM llm_cache WHERE cache_key = $1", key
    )
    assert before["last_hit_at"] is None  # not yet hit

    await get_cached(db_pool, key)

    after = await db_pool.fetchrow(
        "SELECT last_hit_at FROM llm_cache WHERE cache_key = $1", key
    )
    assert after["last_hit_at"] is not None


async def test_second_set_cached_is_noop(db_pool):
    """ON CONFLICT DO NOTHING — the first stored value wins."""
    key = _unique_key()
    await set_cached(db_pool, key, "test_prompt", "test-model", {"v": "first"})
    await set_cached(db_pool, key, "test_prompt", "test-model", {"v": "second"})

    result = await get_cached(db_pool, key)
    assert result["v"] == "first"


async def test_expired_entry_is_treated_as_miss(db_pool):
    key = _unique_key()
    # Store with a TTL that has already passed by back-dating expires_at directly
    await db_pool.execute(
        """
        INSERT INTO llm_cache (cache_key, prompt_key, model, response, expires_at)
        VALUES ($1, 'test', 'test-model', '{"v":1}'::jsonb,
                NOW() - INTERVAL '1 second')
        """,
        key,
    )

    result = await get_cached(db_pool, key)
    assert result is None


async def test_non_expiring_entry_is_returned(db_pool):
    key = _unique_key()
    await set_cached(db_pool, key, "test_prompt", "test-model", {"v": "permanent"})

    result = await get_cached(db_pool, key)
    assert result == {"v": "permanent"}


async def test_ttl_entry_is_returned_before_expiry(db_pool):
    key = _unique_key()
    await set_cached(db_pool, key, "test_prompt", "test-model", {"v": "ttl"}, ttl_seconds=3600)

    result = await get_cached(db_pool, key)
    assert result == {"v": "ttl"}
