"""
Transcript click → progression tests.

Source of truth: youglish-app/features/transcript-click-progression/tests.md

Covers:
  Unit (no DB):
    - compute_delta("transcript_clicked") shape: passive_delta=1, times_seen_delta=1,
      passive_srs="create", active_delta=0, active_srs=None
  Integration (real DB):
    - POST returns 204
    - passive_level incremented by 1
    - times_seen incremented by 1
    - First click creates passive SRS card with default SM-2 values
    - Second click increments passive_level again but does NOT advance the SRS card
    - word_id < 1 (path value 0) returns 422
    - Unauthenticated request returns 401
"""
import uuid

import pytest
from httpx import AsyncClient

from backend.services.progression_service import compute_delta

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email() -> str:
    return f"test+{uuid.uuid4().hex[:10]}@example.com"


async def _register_and_login(client: AsyncClient, db_pool, email: str) -> tuple[dict, str]:
    await client.post(REGISTER, json={"email": email, "password": "password123"})
    r = await client.post(LOGIN, json={"email": email, "password": "password123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    uid = str(await db_pool.fetchval("SELECT user_id FROM users WHERE email = $1", email))
    return headers, uid


async def _get_word(db_pool) -> int:
    row = await db_pool.fetchrow("SELECT word_id FROM word_table LIMIT 1")
    if row is None:
        pytest.skip("word_table is empty — run the subtitle pipeline first")
    return row["word_id"]


async def _get_knowledge(db_pool, uid: str, word_id: int) -> dict | None:
    row = await db_pool.fetchrow(
        """
        SELECT passive_level, times_seen
          FROM user_word_knowledge
         WHERE user_id = $1::uuid AND item_id = $2 AND item_type = 'word'
        """,
        uid, word_id,
    )
    return dict(row) if row else None


async def _get_passive_srs_card(db_pool, uid: str, word_id: int) -> dict | None:
    row = await db_pool.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions, due_date
          FROM srs_cards
         WHERE user_id = $1::uuid AND item_id = $2
           AND item_type = 'word' AND direction = 'passive'
        """,
        uid, word_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Unit test — compute_delta
# ---------------------------------------------------------------------------

def test_transcript_clicked_delta():
    d = compute_delta("transcript_clicked")
    assert d.passive_delta == 1
    assert d.times_seen_delta == 1
    assert d.passive_srs == "create"
    assert d.active_delta == 0
    assert d.active_srs is None


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

async def test_transcript_click_returns_204(client: AsyncClient, db_pool):
    word_id = await _get_word(db_pool)
    headers, _ = await _register_and_login(client, db_pool, _email())

    resp = await client.post(f"/api/v1/words/word/{word_id}/transcript-click", headers=headers)

    assert resp.status_code == 204


async def test_transcript_click_increments_passive_level(client: AsyncClient, db_pool):
    word_id = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    await client.post(f"/api/v1/words/word/{word_id}/transcript-click", headers=headers)

    row = await _get_knowledge(db_pool, uid, word_id)
    assert row is not None
    assert row["passive_level"] == 1


async def test_transcript_click_increments_times_seen(client: AsyncClient, db_pool):
    word_id = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    await client.post(f"/api/v1/words/word/{word_id}/transcript-click", headers=headers)

    row = await _get_knowledge(db_pool, uid, word_id)
    assert row is not None
    assert row["times_seen"] == 1


async def test_first_click_creates_passive_srs_card_with_defaults(client: AsyncClient, db_pool):
    """The 'create' SRS action inserts with interval=1.0, ease=2.5, reps=0."""
    word_id = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    await client.post(f"/api/v1/words/word/{word_id}/transcript-click", headers=headers)

    card = await _get_passive_srs_card(db_pool, uid, word_id)
    assert card is not None
    assert card["interval_days"] == 1.0
    assert card["ease_factor"] == 2.5
    assert card["repetitions"] == 0


async def test_second_click_does_not_advance_srs_card(client: AsyncClient, db_pool):
    """
    'create' is a no-op when a card already exists. The second click should
    NOT change interval_days, ease_factor, or repetitions.
    """
    word_id = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    # First click — creates card
    await client.post(f"/api/v1/words/word/{word_id}/transcript-click", headers=headers)
    card_after_first = await _get_passive_srs_card(db_pool, uid, word_id)

    # Second click — card must stay identical
    await client.post(f"/api/v1/words/word/{word_id}/transcript-click", headers=headers)
    card_after_second = await _get_passive_srs_card(db_pool, uid, word_id)

    assert card_after_second["interval_days"] == card_after_first["interval_days"]
    assert card_after_second["ease_factor"]   == card_after_first["ease_factor"]
    assert card_after_second["repetitions"]   == card_after_first["repetitions"]

    # passive_level must have incremented a second time
    row = await _get_knowledge(db_pool, uid, word_id)
    assert row["passive_level"] == 2


async def test_transcript_click_word_id_zero_returns_422(client: AsyncClient, db_pool):
    """FastAPI Path(ge=1) rejects word_id=0 before the handler runs."""
    headers, _ = await _register_and_login(client, db_pool, _email())

    resp = await client.post("/api/v1/words/word/0/transcript-click", headers=headers)

    assert resp.status_code == 422


async def test_transcript_click_requires_auth(client: AsyncClient, db_pool):
    word_id = await _get_word(db_pool)

    resp = await client.post(f"/api/v1/words/word/{word_id}/transcript-click")

    assert resp.status_code == 401
