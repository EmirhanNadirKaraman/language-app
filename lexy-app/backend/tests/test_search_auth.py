"""
Audit #7 / 2026-05-21: search + corpus endpoints are authenticated.

Before this fix, /api/search, /api/suggest, /api/video-sentences,
/api/word-forms, /api/languages, /api/categories were all public —
logged-out users could browse the scraped corpus. The router now carries
get_current_user as a dependency.

These tests assert two things per endpoint:
  1. Unauthenticated request → 401 or 403 (matches the project's existing
     auth convention; FastAPI's HTTPBearer dependency returns 403 when no
     credentials are presented and 401 when credentials are invalid/expired).
  2. Authenticated request reaches the route (status code reflects the
     route's own behaviour — typically 200 with the documented response
     shape, even when the corpus is empty).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from ._email_helper import make_test_email


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    email = make_test_email()
    await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Unauthenticated → 401/403
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "/api/search?q=test",
        "/api/suggest?q=test",
        "/api/video-sentences?video_id=anything",
        "/api/word-forms?q=test",
        "/api/languages",
        "/api/categories",
    ],
)
async def test_unauthenticated_corpus_endpoint_rejected(client: AsyncClient, url: str):
    resp = await client.get(url)
    assert resp.status_code in (401, 403), (
        f"{url} returned {resp.status_code}; expected 401/403"
    )


async def test_unauthenticated_bad_token_rejected(client: AsyncClient):
    """Even with a malformed token, /api/search must reject."""
    resp = await client.get(
        "/api/search?q=test",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Authenticated → route runs
# ---------------------------------------------------------------------------

async def test_authenticated_search_returns_documented_shape(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/search?q=zzznoresults", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "zzznoresults"
    assert "results" in body
    assert "total" in body


async def test_authenticated_suggest_returns_list(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/suggest?q=zzz", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_authenticated_languages_returns_list(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/languages", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_authenticated_categories_returns_list(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/categories", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_authenticated_word_forms_returns_list(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/word-forms?q=test", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Truly-public endpoints still public (regression guard)
# ---------------------------------------------------------------------------

async def test_auth_register_still_public(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": make_test_email(), "password": "password123"},
    )
    assert resp.status_code in (200, 201)


async def test_auth_login_still_public(client: AsyncClient):
    """Login itself must not require an existing token."""
    email = make_test_email()
    await client.post("/api/v1/auth/register",
                      json={"email": email, "password": "password123"})
    resp = await client.post("/api/v1/auth/login",
                             json={"email": email, "password": "password123"})
    assert resp.status_code == 200


async def test_client_error_log_still_public(client, db_pool):
    """The frontend crash reporter must work pre-login (errors happen at any
    auth state). Backend route accepts unauthenticated POSTs."""
    resp = await client.post(
        "/api/v1/errors/client",
        json={"message": "test-from-anon-search-auth"},
    )
    assert resp.status_code in (200, 204)
    # Clean up: row uses ON DELETE SET NULL on user_id; cleanup-by-email won't
    # touch it because the row's user_id is already NULL. Delete by message tag
    # so the table doesn't grow across parallel runs.
    await db_pool.execute(
        "DELETE FROM client_error_log WHERE message = $1",
        "test-from-anon-search-auth",
    )
