"""
Test fixtures.

Run tests from youglish-app/:
    cd youglish-app
    pytest

The tests hit the real development database. Each test uses emails in the
pattern  test+<random>@example.com  and the autouse `cleanup` fixture deletes
them all after each test, so tests stay independent without needing a separate
test database.
"""
import os
from pathlib import Path

import asyncpg
import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

# .env is four levels up from this file:
# tests/ → backend/ → youglish-app/ → sentence-to-phrase-matcher/
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
    """Delete all test users created during a test."""
    yield
    await db_pool.execute("DELETE FROM users WHERE email LIKE 'test+%@example.com'")
