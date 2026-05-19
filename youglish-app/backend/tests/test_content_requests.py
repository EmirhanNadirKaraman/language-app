"""
Content requests (channel/video index requests).

Covers:
  - POST /api/v1/content-requests creates a row with status='pending'
  - Duplicate request returns the existing row unchanged
  - A 'failed' duplicate gets reset to 'pending'
  - GET /api/v1/content-requests lists user's requests, newest first
  - Auth required

We don't actually spawn the subtitle-scraper subprocess in tests — the router
calls asyncio.ensure_future on _spawn_pipeline but that schedules a coroutine
that opens a subprocess we don't want running in CI. We patch _spawn_pipeline
to be a no-op for these tests.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
URL      = "/api/v1/content-requests"


def _email() -> str:
    return f"test+{uuid.uuid4().hex[:10]}@example.com"


def _channel_id() -> str:
    # Looks YouTube-ish but is unique per test
    return "UC" + uuid.uuid4().hex[:22]


async def _register_and_get_user(client: AsyncClient, db_pool, email: str) -> tuple[dict, str]:
    await client.post(REGISTER, json={"email": email, "password": "password123"})
    r = await client.post(LOGIN, json={"email": email, "password": "password123"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = str(await db_pool.fetchval("SELECT user_id FROM users WHERE email = $1", email))
    return headers, uid


@pytest.fixture(autouse=True)
def _patch_spawn(monkeypatch):
    """Prevent the real subprocess from being spawned during tests."""
    from backend.routers import content_requests
    monkeypatch.setattr(content_requests, "_spawn_pipeline", AsyncMock())


@pytest.fixture(autouse=True)
async def _cleanup_requests(db_pool):
    yield
    await db_pool.execute(
        "DELETE FROM content_request WHERE content_id LIKE 'UC%' OR content_id LIKE 'v_test_%'"
    )


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------

async def test_post_channel_request_creates_pending_row(client: AsyncClient, db_pool):
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    content_id = _channel_id()

    resp = await client.post(
        URL,
        json={"request_type": "channel", "content_id": content_id},
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["request_type"] == "channel"
    assert body["content_id"] == content_id
    assert body["status"] == "pending"
    assert body["error"] is None
    assert "request_id" in body and "created_at" in body and "updated_at" in body


async def test_post_video_request_creates_pending_row(client: AsyncClient, db_pool):
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    content_id = "v_test_" + uuid.uuid4().hex[:8]

    resp = await client.post(
        URL,
        json={"request_type": "video", "content_id": content_id},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["request_type"] == "video"


async def test_duplicate_pending_request_returns_existing(client: AsyncClient, db_pool):
    """Posting the same (type, content_id) twice yields the same request_id."""
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    content_id = _channel_id()

    r1 = await client.post(URL, json={"request_type": "channel", "content_id": content_id}, headers=headers)
    r2 = await client.post(URL, json={"request_type": "channel", "content_id": content_id}, headers=headers)

    assert r1.json()["request_id"] == r2.json()["request_id"]
    assert r2.json()["status"] == "pending"


async def test_failed_request_reset_to_pending_on_resubmit(client: AsyncClient, db_pool):
    """If a previous attempt failed, re-submitting flips status back to pending."""
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    content_id = _channel_id()

    # First submit
    r1 = await client.post(URL, json={"request_type": "channel", "content_id": content_id}, headers=headers)
    request_id = r1.json()["request_id"]

    # Simulate scraper marking it failed
    await db_pool.execute(
        "UPDATE content_request SET status='failed', error='test reason' WHERE request_id = $1",
        request_id,
    )

    # Resubmit
    r2 = await client.post(URL, json={"request_type": "channel", "content_id": content_id}, headers=headers)
    body = r2.json()
    assert body["status"] == "pending"
    assert body["error"] is None
    assert body["request_id"] == request_id


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

async def test_list_returns_users_requests_newest_first(client: AsyncClient, db_pool):
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    ids = [_channel_id() for _ in range(3)]
    for cid in ids:
        await client.post(URL, json={"request_type": "channel", "content_id": cid}, headers=headers)

    resp = await client.get(URL, headers=headers)

    assert resp.status_code == 200
    rows = resp.json()
    # Newest first → reverse of insertion order
    returned_ids = [r["content_id"] for r in rows][:3]
    assert returned_ids == list(reversed(ids))


async def test_list_isolates_users(client: AsyncClient, db_pool):
    """User A's requests must not appear in user B's list."""
    headers_a, _ = await _register_and_get_user(client, db_pool, _email())
    headers_b, _ = await _register_and_get_user(client, db_pool, _email())

    cid = _channel_id()
    await client.post(URL, json={"request_type": "channel", "content_id": cid}, headers=headers_a)

    resp_b = await client.get(URL, headers=headers_b)
    assert all(r["content_id"] != cid for r in resp_b.json())


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def test_post_requires_auth(client: AsyncClient):
    resp = await client.post(URL, json={"request_type": "channel", "content_id": _channel_id()})
    assert resp.status_code in (401, 403)


async def test_get_requires_auth(client: AsyncClient):
    resp = await client.get(URL)
    assert resp.status_code in (401, 403)
