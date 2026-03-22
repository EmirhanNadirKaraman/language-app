"""
Reading → progression tests.

Source of truth: youglish-app/features/reading-progression/tests.md

Covers:
  Unit (no DB):
    - _interval_days for all six schedule slots and the beyond-cap case
  Unit (DB):
    - find_catalog_item: resolves word, returns None for unknown canonical
    - record_review: got_it increments count + sets next_review_at,
                     still_learning resets count + sets next_review_at=NOW,
                     mastered sets status='mastered' + clears next_review_at
  Integration (real DB, HTTP):
    - save_selection with catalog-matched canonical → passive SRS card created
    - save_selection with no catalog match → selection saved, no SRS card
    - review got_it → SM-2 passive card advances (repetitions + 1)
    - review mastered → status='mastered', SRS card unchanged
    - get_due_selections returns newly-saved (NULL next_review_at)
    - get_due_selections excludes mastered
"""
import uuid

import pytest
from httpx import AsyncClient

from backend.services.reading_service import _interval_days, find_catalog_item

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


async def _get_word(db_pool) -> tuple[int, str, str]:
    row = await db_pool.fetchrow("SELECT word_id, word, language FROM word_table LIMIT 1")
    if row is None:
        pytest.skip("word_table is empty — run the subtitle pipeline first")
    return row["word_id"], row["word"], row["language"]


async def _create_doc(db_pool, uid: str, language: str) -> str:
    """Insert a minimal book_documents row owned by the test user.

    Deleted automatically when the user row is CASCADE-deleted by the cleanup fixture.
    """
    doc_id = str(await db_pool.fetchval(
        """
        INSERT INTO book_documents
            (user_id, title, filename, file_path, language, source_type, status)
        VALUES ($1::uuid, 'Test Book', 'test.pdf', '/tmp/test.pdf', $2, 'pdf', 'ready')
        RETURNING doc_id
        """,
        uid, language,
    ))
    return doc_id


async def _save_selection_direct(db_pool, uid: str, doc_id: str, canonical: str) -> str:
    """Insert a reading_selection row directly (bypasses HTTP + progression)."""
    sel_id = str(await db_pool.fetchval(
        """
        INSERT INTO reading_selections
            (user_id, doc_id, canonical, surface_text, sentence_text, anchors)
        VALUES ($1::uuid, $2::uuid, $3, $3, $3, '[]'::jsonb)
        RETURNING selection_id
        """,
        uid, doc_id, canonical,
    ))
    return sel_id


async def _get_passive_srs_card(db_pool, uid: str, item_id: int, item_type: str) -> dict | None:
    row = await db_pool.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions
          FROM srs_cards
         WHERE user_id = $1::uuid AND item_id = $2
           AND item_type = $3 AND direction = 'passive'
        """,
        uid, item_id, item_type,
    )
    return dict(row) if row else None


def _sel_body(word: str) -> dict:
    return {
        "canonical": word,
        "surface_text": word,
        "sentence_text": f"Test sentence with {word}.",
        "anchors": [],
        "note": None,
    }


# ---------------------------------------------------------------------------
# Unit tests — _interval_days (pure function, no DB)
# ---------------------------------------------------------------------------

def test_interval_days_first_review():
    assert _interval_days(0) == 1

def test_interval_days_second_review():
    assert _interval_days(1) == 2

def test_interval_days_third_review():
    assert _interval_days(2) == 4

def test_interval_days_fourth_review():
    assert _interval_days(3) == 7

def test_interval_days_fifth_review():
    assert _interval_days(4) == 14

def test_interval_days_sixth_review():
    assert _interval_days(5) == 30

def test_interval_days_beyond_sixth_is_capped_at_30():
    assert _interval_days(6) == 30
    assert _interval_days(100) == 30


# ---------------------------------------------------------------------------
# Unit tests — find_catalog_item (DB)
# ---------------------------------------------------------------------------

async def test_find_catalog_item_resolves_word(client: AsyncClient, db_pool):
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    result = await find_catalog_item(db_pool, doc_id, word)

    assert result is not None
    item_id, item_type = result
    assert item_id == word_id
    assert item_type == "word"


async def test_find_catalog_item_returns_none_for_unknown_canonical(
    client: AsyncClient, db_pool
):
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    result = await find_catalog_item(db_pool, doc_id, "xyzzy_nonexistent_12345")

    assert result is None


# ---------------------------------------------------------------------------
# Unit tests — record_review (DB, service layer)
# ---------------------------------------------------------------------------

async def test_record_review_got_it_increments_review_count(client: AsyncClient, db_pool):
    from backend.services.reading_service import record_review
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)
    sel_id = await _save_selection_direct(db_pool, uid, doc_id, word)

    result = await record_review(db_pool, sel_id, uid, "got_it")

    assert result is not None
    assert result["review_count"] == 1
    assert result["next_review_at"] is not None


async def test_record_review_still_learning_resets_count(client: AsyncClient, db_pool):
    from backend.services.reading_service import record_review
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)
    sel_id = await _save_selection_direct(db_pool, uid, doc_id, word)

    await record_review(db_pool, sel_id, uid, "got_it")
    result = await record_review(db_pool, sel_id, uid, "still_learning")

    assert result["review_count"] == 0
    assert result["next_review_at"] is not None  # due immediately


async def test_record_review_mastered_sets_status_and_clears_date(
    client: AsyncClient, db_pool
):
    from backend.services.reading_service import record_review
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)
    sel_id = await _save_selection_direct(db_pool, uid, doc_id, word)

    result = await record_review(db_pool, sel_id, uid, "mastered")

    assert result["status"] == "mastered"
    assert result["next_review_at"] is None


# ---------------------------------------------------------------------------
# Integration tests — HTTP
# ---------------------------------------------------------------------------

async def test_save_selection_with_word_match_creates_passive_srs_card(
    client: AsyncClient, db_pool
):
    """Catalog match on save fires status_marked_learning → passive SRS card created."""
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    resp = await client.post(
        f"/api/v1/books/{doc_id}/selections",
        json=_sel_body(word),
        headers=headers,
    )
    assert resp.status_code == 201

    card = await _get_passive_srs_card(db_pool, uid, word_id, "word")
    assert card is not None
    assert card["interval_days"] == 1.0
    assert card["ease_factor"] == 2.5
    assert card["repetitions"] == 0


async def test_save_selection_no_catalog_match_creates_no_srs_card(
    client: AsyncClient, db_pool
):
    """Uncatalogued canonical: selection is saved but no SRS card is created."""
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    resp = await client.post(
        f"/api/v1/books/{doc_id}/selections",
        json=_sel_body("xyzzy_not_in_word_table_phrase_abc"),
        headers=headers,
    )
    assert resp.status_code == 201

    count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM srs_cards WHERE user_id = $1::uuid",
        uid,
    )
    assert count == 0


async def test_review_got_it_advances_passive_srs_card(client: AsyncClient, db_pool):
    """got_it fires passive_review_correct → SM-2 repetitions increments."""
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    # Save via HTTP to get both the selection and the SRS card
    save_resp = await client.post(
        f"/api/v1/books/{doc_id}/selections",
        json=_sel_body(word),
        headers=headers,
    )
    assert save_resp.status_code == 201
    sel_id = save_resp.json()["selection_id"]

    card_before = await _get_passive_srs_card(db_pool, uid, word_id, "word")
    assert card_before is not None

    resp = await client.post(
        f"/api/v1/reading/selections/{sel_id}/review",
        json={"outcome": "got_it"},
        headers=headers,
    )
    assert resp.status_code == 200

    card_after = await _get_passive_srs_card(db_pool, uid, word_id, "word")
    assert card_after["repetitions"] == card_before["repetitions"] + 1
    assert card_after["interval_days"] > card_before["interval_days"]


async def test_review_mastered_does_not_change_srs_card(client: AsyncClient, db_pool):
    """mastered fires no progression event — SRS card state stays the same."""
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    save_resp = await client.post(
        f"/api/v1/books/{doc_id}/selections",
        json=_sel_body(word),
        headers=headers,
    )
    sel_id = save_resp.json()["selection_id"]

    card_before = await _get_passive_srs_card(db_pool, uid, word_id, "word")
    assert card_before is not None

    resp = await client.post(
        f"/api/v1/reading/selections/{sel_id}/review",
        json={"outcome": "mastered"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "mastered"

    card_after = await _get_passive_srs_card(db_pool, uid, word_id, "word")
    assert card_after["interval_days"] == card_before["interval_days"]
    assert card_after["repetitions"]   == card_before["repetitions"]


async def test_due_selections_includes_newly_saved(client: AsyncClient, db_pool):
    """Newly saved selection (next_review_at IS NULL) appears in the due list."""
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    await client.post(
        f"/api/v1/books/{doc_id}/selections",
        json=_sel_body(word),
        headers=headers,
    )

    resp = await client.get("/api/v1/reading/selections/due", headers=headers)
    assert resp.status_code == 200
    assert any(s["canonical"] == word for s in resp.json())


async def test_due_selections_excludes_mastered(client: AsyncClient, db_pool):
    """Mastered selections must not appear in the due list."""
    word_id, word, language = await _get_word(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())
    doc_id = await _create_doc(db_pool, uid, language)

    save_resp = await client.post(
        f"/api/v1/books/{doc_id}/selections",
        json=_sel_body(word),
        headers=headers,
    )
    sel_id = save_resp.json()["selection_id"]

    await client.post(
        f"/api/v1/reading/selections/{sel_id}/review",
        json={"outcome": "mastered"},
        headers=headers,
    )

    resp = await client.get("/api/v1/reading/selections/due", headers=headers)
    assert resp.status_code == 200
    assert not any(s["canonical"] == word for s in resp.json())
