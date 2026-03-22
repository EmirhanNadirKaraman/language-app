"""
SRS review feature tests.

Source of truth: youglish-app/features/srs-review/tests.md

Covers:
  Unit (no DB):
    - compute_delta for all four review progression events
  Integration (real DB):
    - GET /srs/due: empty for new user, returns card, display_text = word surface,
      excludes known items, requires language param, respects limit
    - POST /srs/review/{card_id}: returns success, advances SM-2 on correct,
      resets SM-2 on incorrect, returns 404 for another user's card

Implementation matches feature spec — no fixes required.
"""
import uuid

import pytest
from httpx import AsyncClient

from backend.services.progression_service import compute_delta

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
SRS_DUE  = "/api/v1/srs/due"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email() -> str:
    return f"test+{uuid.uuid4().hex[:10]}@example.com"


async def _register_and_get_user(client: AsyncClient, db_pool, email: str) -> tuple[dict, str]:
    """Register user, return (auth_headers, user_id_str)."""
    await client.post(REGISTER, json={"email": email, "password": "password123"})
    r = await client.post(LOGIN, json={"email": email, "password": "password123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    uid = str(await db_pool.fetchval("SELECT user_id FROM users WHERE email = $1", email))
    return headers, uid


async def _get_word(db_pool) -> tuple[int, str, str]:
    """Return (word_id, word, language) or skip if word_table is empty."""
    row = await db_pool.fetchrow("SELECT word_id, word, language FROM word_table LIMIT 1")
    if row is None:
        pytest.skip("word_table is empty — run the subtitle pipeline first")
    return row["word_id"], row["word"], row["language"]


async def _get_srs_card(pool, user_id: str, item_id: int, item_type: str, direction: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions, due_date
          FROM srs_cards
         WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3 AND direction = $4
        """,
        user_id, item_id, item_type, direction,
    )
    return dict(row) if row else None


async def _mark_learning_and_get_card_id(client, headers, language, word_id) -> int:
    """Mark word as learning (creates passive SRS card due NOW) and return card_id."""
    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )
    resp = await client.get(SRS_DUE, params={"language": language}, headers=headers)
    cards = resp.json()
    assert cards, "Expected a due card after marking word as learning"
    return cards[0]["card_id"]


# ---------------------------------------------------------------------------
# Unit tests — compute_delta for review events
# ---------------------------------------------------------------------------

def test_passive_review_correct_delta():
    """Passive correct review: only advances passive SRS card, no level deltas."""
    d = compute_delta("passive_review_correct")
    assert d.passive_delta == 0
    assert d.active_delta == 0
    assert d.passive_srs == "correct"
    assert d.active_srs is None


def test_passive_review_incorrect_delta():
    """Passive incorrect review: only penalises passive SRS card, no level deltas."""
    d = compute_delta("passive_review_incorrect")
    assert d.passive_delta == 0
    assert d.active_delta == 0
    assert d.passive_srs == "incorrect"
    assert d.active_srs is None


def test_active_review_correct_delta():
    """Active correct: advances both levels, times_used_correctly, and active SRS card."""
    d = compute_delta("active_review_correct")
    assert d.passive_delta == 1
    assert d.active_delta == 1
    assert d.times_used_correctly_delta == 1
    assert d.passive_srs is None
    assert d.active_srs == "correct"


def test_active_review_incorrect_delta():
    """Active incorrect: only penalises active SRS card, no level deltas."""
    d = compute_delta("active_review_incorrect")
    assert d.passive_delta == 0
    assert d.active_delta == 0
    assert d.passive_srs is None
    assert d.active_srs == "incorrect"


# ---------------------------------------------------------------------------
# GET /srs/due
# ---------------------------------------------------------------------------

async def test_due_returns_empty_list_for_new_user(client: AsyncClient, db_pool):
    word_id, _, language = await _get_word(db_pool)
    headers, _ = await _register_and_get_user(client, db_pool, _email())

    resp = await client.get(SRS_DUE, params={"language": language}, headers=headers)

    assert resp.status_code == 200
    assert resp.json() == []


async def test_due_returns_card_after_marking_word_learning(client: AsyncClient, db_pool):
    """status_marked_learning creates a passive SRS card due NOW → appears in /srs/due."""
    word_id, _, language = await _get_word(db_pool)
    headers, _ = await _register_and_get_user(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    resp = await client.get(SRS_DUE, params={"language": language}, headers=headers)

    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1
    card = cards[0]
    assert card["item_id"] == word_id
    assert card["item_type"] == "word"
    assert card["direction"] == "passive"
    assert "card_id" in card
    assert "display_text" in card


async def test_due_card_display_text_is_word_surface_form(client: AsyncClient, db_pool):
    """display_text must come from word_table.word, not stored on srs_cards."""
    word_id, word_text, language = await _get_word(db_pool)
    headers, _ = await _register_and_get_user(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    cards = (await client.get(SRS_DUE, params={"language": language}, headers=headers)).json()
    assert cards[0]["display_text"] == word_text


async def test_due_excludes_known_items(client: AsyncClient, db_pool):
    """Items with status='known' must not appear in due cards even if due_date <= NOW."""
    word_id, _, language = await _get_word(db_pool)
    headers, _ = await _register_and_get_user(client, db_pool, _email())

    # Create the SRS card, then promote to known
    await client.put(f"/api/v1/words/word/{word_id}/status", json={"status": "learning"}, headers=headers)
    await client.put(f"/api/v1/words/word/{word_id}/status", json={"status": "known"},    headers=headers)

    resp = await client.get(SRS_DUE, params={"language": language}, headers=headers)

    assert resp.status_code == 200
    assert resp.json() == []


async def test_due_requires_language_query_param(client: AsyncClient, db_pool):
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    resp = await client.get(SRS_DUE, headers=headers)
    assert resp.status_code == 422


async def test_due_limit_param_is_respected(client: AsyncClient, db_pool):
    rows = await db_pool.fetch("SELECT word_id, language FROM word_table LIMIT 5")
    if len(rows) < 2:
        pytest.skip("Need at least 2 words in word_table")

    language = rows[0]["language"]
    same_lang = [r for r in rows if r["language"] == language]
    if len(same_lang) < 2:
        pytest.skip("Need at least 2 words with the same language")

    headers, _ = await _register_and_get_user(client, db_pool, _email())
    for r in same_lang[:2]:
        await client.put(f"/api/v1/words/word/{r['word_id']}/status", json={"status": "learning"}, headers=headers)

    resp = await client.get(SRS_DUE, params={"language": language, "limit": 1}, headers=headers)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# POST /srs/review/{card_id}
# ---------------------------------------------------------------------------

async def test_submit_correct_answer_returns_success_response(client: AsyncClient, db_pool):
    word_id, _, language = await _get_word(db_pool)
    headers, _ = await _register_and_get_user(client, db_pool, _email())
    card_id = await _mark_learning_and_get_card_id(client, headers, language, word_id)

    resp = await client.post(f"/api/v1/srs/review/{card_id}", json={"correct": True}, headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"card_id": card_id, "success": True}


async def test_correct_answer_advances_sm2_interval_and_repetitions(client: AsyncClient, db_pool):
    """
    Correct answer on a 'create'-initialized card (interval=1.0, rep=0) should:
      new_interval = 1.0 * 2.5 = 2.5, repetitions = 1.
    """
    word_id, _, language = await _get_word(db_pool)
    headers, uid = await _register_and_get_user(client, db_pool, _email())
    card_id = await _mark_learning_and_get_card_id(client, headers, language, word_id)

    await client.post(f"/api/v1/srs/review/{card_id}", json={"correct": True}, headers=headers)

    card = await _get_srs_card(db_pool, uid, word_id, "word", "passive")
    assert card is not None
    assert card["repetitions"] == 1
    assert card["interval_days"] > 1.0


async def test_incorrect_answer_resets_sm2_to_one_day(client: AsyncClient, db_pool):
    """
    After one correct then one incorrect answer:
      interval = 1.0, repetitions = 0.
    """
    word_id, _, language = await _get_word(db_pool)
    headers, uid = await _register_and_get_user(client, db_pool, _email())
    card_id = await _mark_learning_and_get_card_id(client, headers, language, word_id)

    # Advance first so there's something to reset
    await client.post(f"/api/v1/srs/review/{card_id}", json={"correct": True}, headers=headers)
    # Now penalise (submit_answer does not require due_date <= NOW)
    await client.post(f"/api/v1/srs/review/{card_id}", json={"correct": False}, headers=headers)

    card = await _get_srs_card(db_pool, uid, word_id, "word", "passive")
    assert card["interval_days"] == 1.0
    assert card["repetitions"] == 0


async def test_submit_answer_for_another_users_card_returns_404(client: AsyncClient, db_pool):
    """Users must not be able to submit answers for cards they don't own."""
    word_id, _, language = await _get_word(db_pool)
    headers_a, _ = await _register_and_get_user(client, db_pool, _email())
    headers_b, _ = await _register_and_get_user(client, db_pool, _email())

    card_id = await _mark_learning_and_get_card_id(client, headers_a, language, word_id)

    resp = await client.post(f"/api/v1/srs/review/{card_id}", json={"correct": True}, headers=headers_b)

    assert resp.status_code == 404
