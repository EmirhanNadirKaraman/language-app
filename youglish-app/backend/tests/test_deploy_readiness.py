"""
Deploy-readiness tests for #11 (CORS env config) and #13 (JWT expired refinement).
"""
from __future__ import annotations

import os
import time

import jwt
import pytest
from httpx import AsyncClient

from backend.core.security import create_access_token


# ---------------------------------------------------------------------------
# #11 — CORS_ORIGINS parser
# ---------------------------------------------------------------------------

def test_cors_origins_defaults_to_localhost_when_unset():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins(None) == ["http://localhost:5173"]


def test_cors_origins_defaults_to_localhost_when_empty():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins("") == ["http://localhost:5173"]
    assert _parse_cors_origins("   ") == ["http://localhost:5173"]


def test_cors_origins_parses_single_value():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins("https://example.com") == ["https://example.com"]


def test_cors_origins_parses_comma_separated():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins("https://a.com,https://b.com,https://c.com") == [
        "https://a.com", "https://b.com", "https://c.com",
    ]


def test_cors_origins_strips_whitespace():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins("  https://a.com , https://b.com ") == [
        "https://a.com", "https://b.com",
    ]


def test_cors_origins_drops_empty_entries():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins("https://a.com,,https://b.com,") == [
        "https://a.com", "https://b.com",
    ]


def test_cors_origins_all_empty_falls_back_to_default():
    from backend.main import _parse_cors_origins
    assert _parse_cors_origins(",,, ,,") == ["http://localhost:5173"]


# ---------------------------------------------------------------------------
# #11 — CORS header behaviour through the actual middleware
# ---------------------------------------------------------------------------

async def test_cors_default_origin_gets_acao_header(client: AsyncClient):
    """Preflight from the default localhost origin gets ACAO back."""
    resp = await client.options(
        "/api/languages",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_cors_unconfigured_origin_no_acao_header(client: AsyncClient):
    """Default config does NOT allow an arbitrary origin — no ACAO header."""
    resp = await client.options(
        "/api/languages",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"


# ---------------------------------------------------------------------------
# #13 — JWT expired vs malformed
# ---------------------------------------------------------------------------

def _expired_token(user_id: str) -> str:
    """Build a JWT with `exp` set in the past."""
    secret = os.getenv("SECRET_KEY")
    if not secret:
        pytest.skip("SECRET_KEY not in env")
    payload = {
        "sub": user_id,
        "exp": int(time.time()) - 60,   # 1 minute in the past
        "iat": int(time.time()) - 120,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def test_expired_token_returns_token_expired_detail(client: AsyncClient, db_pool):
    """ExpiredSignatureError → 401 with detail='token_expired'."""
    uid = await db_pool.fetchval(
        "INSERT INTO users (email, password_hash) VALUES ($1, 'x') RETURNING user_id",
        f"test+{int(time.time()*1000)}@example.com",
    )
    token = _expired_token(str(uid))

    resp = await client.get(
        "/api/v1/words/knowledge",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "token_expired"}
    auth_header = resp.headers.get("www-authenticate", "")
    assert "Bearer" in auth_header
    assert "token expired" in auth_header.lower()


async def test_malformed_token_returns_generic_invalid_token(client: AsyncClient):
    """Anything that's not a valid JWT (garbage, wrong signature, missing claims)
    keeps the existing generic 'Invalid token' detail."""
    resp = await client.get(
        "/api/v1/words/knowledge",
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid token"}


async def test_wrong_signature_returns_generic_invalid_token(client: AsyncClient):
    """A JWT signed with the wrong secret falls into InvalidTokenError, not ExpiredSignatureError."""
    bad_token = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "exp": int(time.time()) + 300},
        "wrong-secret",
        algorithm="HS256",
    )
    resp = await client.get(
        "/api/v1/words/knowledge",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid token"}


async def test_valid_token_still_authenticates(client: AsyncClient, db_pool):
    """Sanity: the new exception split doesn't break the happy path."""
    uid = await db_pool.fetchval(
        "INSERT INTO users (email, password_hash) VALUES ($1, 'x') RETURNING user_id",
        f"test+valid+{int(time.time()*1000)}@example.com",
    )
    token = create_access_token(str(uid))
    resp = await client.get(
        "/api/v1/words/knowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
