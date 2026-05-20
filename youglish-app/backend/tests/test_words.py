"""
Word knowledge tests — upsert behaviour on first and subsequent calls.

These tests require at least one row in word_table (populated by the
subtitle ingestion pipeline). They will be skipped if the table is empty.
"""
import uuid

import pytest
from httpx import AsyncClient
from ._email_helper import cleanup_pattern, make_test_email

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
KNOWLEDGE = "/api/v1/words/knowledge"
BY_TEXT = "/api/v1/words/by-text"


def make_email() -> str:
    return make_test_email()


async def _registered_token(client: AsyncClient) -> str:
    """Register a fresh user and return its JWT."""
    email = make_email()
    await client.post(REGISTER, json={"email": email, "password": "password123"})
    resp = await client.post(LOGIN, json={"email": email, "password": "password123"})
    return resp.json()["access_token"]


async def _get_word_id(db_pool) -> int:
    """Return any word_id from word_table, or skip the test if table is empty."""
    word_id = await db_pool.fetchval("SELECT word_id FROM word_table LIMIT 1")
    if word_id is None:
        pytest.skip("word_table is empty — run the subtitle pipeline first")
    return word_id


# ---------------------------------------------------------------------------
# GET /knowledge
# ---------------------------------------------------------------------------


async def test_knowledge_is_empty_for_new_user(client: AsyncClient):
    token = await _registered_token(client)
    resp = await client.get(KNOWLEDGE, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# PUT /{item_type}/{item_id}/status — insert on first call
# ---------------------------------------------------------------------------


async def test_first_status_update_creates_row(client: AsyncClient, db_pool):
    word_id = await _get_word_id(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["item_id"] == word_id
    assert data["item_type"] == "word"
    assert data["status"] == "learning"
    # status update + progression now run in a single transaction, so the
    # response reflects the post-progression state. status_marked_learning has
    # passive_delta=1.
    assert data["passive_level"] == 1
    assert data["active_level"] == 0


async def test_first_status_update_appears_in_knowledge_list(client: AsyncClient, db_pool):
    word_id = await _get_word_id(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    knowledge = await client.get(KNOWLEDGE, headers=headers)
    items = knowledge.json()
    assert len(items) == 1
    assert items[0]["item_id"] == word_id
    assert items[0]["status"] == "learning"


# ---------------------------------------------------------------------------
# PUT /{item_type}/{item_id}/status — update on second call
# ---------------------------------------------------------------------------


async def test_second_status_update_changes_status(client: AsyncClient, db_pool):
    word_id = await _get_word_id(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/words/word/{word_id}/status"

    await client.put(url, json={"status": "learning"}, headers=headers)
    resp = await client.put(url, json={"status": "known"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "known"


async def test_second_status_update_does_not_create_duplicate(client: AsyncClient, db_pool):
    word_id = await _get_word_id(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/words/word/{word_id}/status"

    await client.put(url, json={"status": "learning"}, headers=headers)
    await client.put(url, json={"status": "known"}, headers=headers)

    knowledge = await client.get(KNOWLEDGE, headers=headers)
    matching = [i for i in knowledge.json() if i["item_id"] == word_id]
    assert len(matching) == 1  # still exactly one row


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_invalid_status_returns_422(client: AsyncClient, db_pool):
    word_id = await _get_word_id(db_pool)
    token = await _registered_token(client)

    resp = await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "mastered"},  # not a valid status
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_invalid_item_type_returns_422(client: AsyncClient, db_pool):
    word_id = await _get_word_id(db_pool)
    token = await _registered_token(client)

    resp = await client.put(
        f"/api/v1/words/bogus_type/{word_id}/status",
        json={"status": "learning"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /by-text — progress fields
# ---------------------------------------------------------------------------


async def _get_word_text_and_language(db_pool) -> tuple[str, str]:
    """Return (word, language) for any word in word_table, skipping if empty."""
    row = await db_pool.fetchrow("SELECT word, language FROM word_table LIMIT 1")
    if row is None:
        pytest.skip("word_table is empty — run the subtitle pipeline first")
    return row["word"], row["language"]


async def test_by_text_returns_progress_fields_for_unknown_word(client: AsyncClient, db_pool):
    """A word with no knowledge row returns zero levels and null due dates."""
    word, language = await _get_word_text_and_language(db_pool)
    token = await _registered_token(client)

    resp = await client.get(
        BY_TEXT,
        params={"word": word, "language": language},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passive_level"] == 0
    assert data["active_level"] == 0
    assert data["passive_due"] is None
    assert data["active_due"] is None


async def test_by_text_returns_nonzero_levels_after_status_update(client: AsyncClient, db_pool):
    """After marking a word 'learning', passive_level should be > 0."""
    word, language = await _get_word_text_and_language(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # First get the word_id
    lookup = await client.get(BY_TEXT, params={"word": word, "language": language}, headers=headers)
    assert lookup.status_code == 200
    word_id = lookup.json()["word_id"]

    # Mark it as learning (fires status_marked_learning → passive_delta=1)
    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    # Re-fetch and check levels advanced
    resp = await client.get(BY_TEXT, params={"word": word, "language": language}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["passive_level"] > 0
    assert data["current_status"] == "learning"


async def test_by_text_returns_null_for_unknown_word_not_in_db(client: AsyncClient):
    """A word that doesn't exist in word_table returns null."""
    token = await _registered_token(client)

    resp = await client.get(
        BY_TEXT,
        params={"word": "xyzzy_no_such_word_123", "language": "de"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() is None


# ---------------------------------------------------------------------------
# PUT status=known — contract: confidence, not fabricated active mastery.
# Mirrors the actual frontend call. Pinned to lock the behaviour.
# ---------------------------------------------------------------------------

async def _get_word_for_lookup(db_pool) -> tuple[int, str, str]:
    """Return (word_id, word_text, language) for a row that supports by-text lookup."""
    row = await db_pool.fetchrow(
        "SELECT word_id, word, language FROM word_table LIMIT 1"
    )
    if row is None:
        pytest.skip("word_table is empty")
    return row["word_id"], row["word"], row["language"]


async def test_put_known_writes_status_known(client: AsyncClient, db_pool):
    """Status field is written inside apply_progression's transaction via
    status_override — a single atomic write covering status + SRS + levels."""
    word_id, word, language = await _get_word_for_lookup(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "known"},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "known"

    # Round-trip via /by-text to confirm persisted state.
    lookup = await client.get(BY_TEXT, params={"word": word, "language": language}, headers=headers)
    assert lookup.json()["current_status"] == "known"


async def test_put_known_does_not_create_active_srs_card(client: AsyncClient, db_pool):
    """Manual known must NOT schedule active production review."""
    word_id, _, _ = await _get_word_for_lookup(db_pool)
    token = await _registered_token(client)
    uid = await db_pool.fetchval(
        "SELECT user_id FROM users WHERE email LIKE $1 ORDER BY user_id DESC LIMIT 1", cleanup_pattern()
    )

    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "known"},
        headers={"Authorization": f"Bearer {token}"},
    )

    active = await db_pool.fetchrow(
        "SELECT card_id FROM srs_cards WHERE user_id=$1::uuid AND item_id=$2 "
        "AND item_type='word' AND direction='active'",
        uid, word_id,
    )
    assert active is None


async def test_put_known_does_not_increment_active_level(client: AsyncClient, db_pool):
    """Manual known must not inflate active_level — that's reserved for production evidence."""
    word_id, _, _ = await _get_word_for_lookup(db_pool)
    token = await _registered_token(client)
    uid = await db_pool.fetchval(
        "SELECT user_id FROM users WHERE email LIKE $1 ORDER BY user_id DESC LIMIT 1", cleanup_pattern()
    )

    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "known"},
        headers={"Authorization": f"Bearer {token}"},
    )

    row = await db_pool.fetchrow(
        "SELECT active_level, times_used_correctly FROM user_word_knowledge "
        "WHERE user_id=$1::uuid AND item_id=$2 AND item_type='word'",
        uid, word_id,
    )
    # Row is created by apply_progression (via status_override) — assert level fields stay zero.
    if row is not None:
        assert row["active_level"] == 0
        assert row["times_used_correctly"] == 0


async def test_put_known_after_learning_does_not_advance_active_card(client: AsyncClient, db_pool):
    """If a learning word already has an active SRS card (from #0b), marking
    it known must NOT advance it as if the user answered correctly."""
    word_id, _, _ = await _get_word_for_lookup(db_pool)
    token = await _registered_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    uid = await db_pool.fetchval(
        "SELECT user_id FROM users WHERE email LIKE $1 ORDER BY user_id DESC LIMIT 1", cleanup_pattern()
    )

    # First mark learning → creates active card at interval=1.0, reps=0.
    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "learning"},
        headers=headers,
    )
    before = await db_pool.fetchrow(
        "SELECT interval_days, repetitions, ease_factor, due_date FROM srs_cards "
        "WHERE user_id=$1::uuid AND item_id=$2 AND item_type='word' AND direction='active'",
        uid, word_id,
    )
    assert before is not None

    # Now mark known. Must NOT advance the active card.
    await client.put(
        f"/api/v1/words/word/{word_id}/status",
        json={"status": "known"},
        headers=headers,
    )

    after = await db_pool.fetchrow(
        "SELECT interval_days, repetitions, ease_factor, due_date FROM srs_cards "
        "WHERE user_id=$1::uuid AND item_id=$2 AND item_type='word' AND direction='active'",
        uid, word_id,
    )
    assert after is not None
    assert after["repetitions"]   == before["repetitions"]
    assert after["interval_days"] == before["interval_days"]
    assert after["ease_factor"]   == before["ease_factor"]
    assert after["due_date"]      == before["due_date"]
