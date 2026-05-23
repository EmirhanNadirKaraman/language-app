"""
Test fixtures.

Run tests from lexy-app/:
    cd lexy-app
    pytest                 # serial
    pytest -n auto         # parallel via pytest-xdist

The tests hit the real development database. Each test uses emails in the
pattern  test+{worker_id}_{random}@example.com  (built by `make_test_email()`
in `_email_helper.py`). The autouse `cleanup` fixture deletes only rows
matching THIS worker's pattern, so parallel workers can't trample each other's
in-flight users.
"""
import os
from pathlib import Path

import asyncpg
import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

from ._email_helper import cleanup_pattern

# .env is four levels up from this file:
# tests/ → backend/ → lexy-app/ → sentence-to-phrase-matcher/
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")


@pytest.fixture(scope="session")
async def db_pool():
    pool = await asyncpg.create_pool(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    yield pool
    await pool.close()


@pytest.fixture
async def client(db_pool):
    """
    HTTP client wired to the FastAPI app with the test pool injected.

    The app lifespan still runs (creating its own pool), but all routes
    use our test pool via dependency_overrides.
    """
    from backend.database import get_pool
    from backend.main import app

    app.dependency_overrides[get_pool] = lambda: db_pool

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def cleanup(db_pool):
    """Delete all test users created during a test, and clear any in-memory
    rate-limiter state so per-user counters from one test don't carry into
    the next."""
    yield
    # Per-worker scoped delete — under pytest-xdist each worker only touches
    # the rows whose email carries its own worker tag. Serial runs collapse to
    # the 'main' tag.
    await db_pool.execute(
        "DELETE FROM users WHERE email LIKE $1",
        cleanup_pattern(),
    )
    # Reset in-process LLM rate limiter (#12). Importing here keeps the
    # fixture cheap when the limiter module isn't loaded.
    from backend.services import rate_limiter
    rate_limiter.reset_for_tests()


async def _reap_word_ids(pool, word_ids: list[int]) -> None:
    """Delete synthetic word_table rows a test created.

    word_table is GLOBAL (not user-scoped), so the autouse user cleanup above
    can't reach these rows — without this they accumulate forever and break
    LIMIT-1 picks in other suites. Safe + order-independent because:
      * word_table's FK children (word_to_sentence, word_strength,
        most_frequent_words) are ON DELETE CASCADE;
      * user_word_knowledge / srs_cards have NO FK to word_table (they use the
        polymorphic (item_id, item_type) key) and are removed via the user
        CASCADE, so they never block this delete.
    Idempotent: deleting an already-gone id is a no-op.
    """
    if not word_ids:
        return
    await pool.execute("DELETE FROM word_table WHERE word_id = ANY($1::int[])", word_ids)


@pytest.fixture
async def tracked_words(db_pool):
    """Registry for synthetic word_table rows a test inserts. Append each
    created word_id (helpers like test_words._create_ambiguous_word do this for
    you); the teardown reaps them via _reap_word_ids so word_table stays clean.
    """
    created: list[int] = []
    yield created
    await _reap_word_ids(db_pool, created)
