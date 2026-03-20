"""
Passive/active progression tests.

Unit tests (no DB) — test compute_delta:
  - correct delta values for every implemented event
  - unknown event raises ValueError

Integration tests (real DB) — test apply_progression:
  - guided_counted updates passive_level + active_level + times_used_correctly
  - guided_counted creates active SRS card
  - guided_counted creates passive SRS card
  - guided_counted repeated → auto-promotion to 'known' at ACTIVE_MASTERY_THRESHOLD
  - guided_used updates passive_level only, does NOT create active SRS card
  - guided_not_used penalises active SRS card
  - guided_not_used does NOT touch levels
  - status_marked_learning creates passive SRS card
  - status_marked_known boosts both levels and creates both SRS cards
  - passive auto-promotion: passive_level >= PASSIVE_PROMOTION_THRESHOLD → 'learning'
"""
import uuid

import pytest

from backend.services.progression_service import (
    ACTIVE_MASTERY_THRESHOLD,
    PASSIVE_PROMOTION_THRESHOLD,
    ProgressionDelta,
    apply_progression,
    compute_delta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_word_ids: list[int] = []


async def _get_word_id(pool, offset: int = 0) -> int:
    if not _word_ids:
        rows = await pool.fetch("SELECT word_id FROM word_table LIMIT 5")
        if not rows:
            pytest.skip("word_table is empty — run the subtitle pipeline first")
        _word_ids.extend(r["word_id"] for r in rows)
    return _word_ids[offset % len(_word_ids)]


async def _make_user(pool) -> str:
    from backend.services.auth_service import register_user
    email = f"test+{uuid.uuid4().hex[:10]}@example.com"
    user = await register_user(pool, email, "password123")
    return str(user["user_id"])


async def _get_uwk(pool, user_id: str, item_id: int) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT passive_level, active_level, times_seen, times_used_correctly, status
          FROM user_word_knowledge
         WHERE user_id = $1::uuid AND item_id = $2 AND item_type = 'word'
        """,
        user_id, item_id,
    )
    return dict(row) if row else None


async def _get_srs(pool, user_id: str, item_id: int, direction: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions, due_date
          FROM srs_cards
         WHERE user_id = $1::uuid AND item_id = $2 AND item_type = 'word' AND direction = $3
        """,
        user_id, item_id, direction,
    )
    return dict(row) if row else None


async def _apply(pool, user_id, item_id, event):
    await apply_progression(pool, user_id, item_id, "word", event)


# ---------------------------------------------------------------------------
# Unit tests — pure function, no DB
# ---------------------------------------------------------------------------

def test_compute_delta_guided_counted():
    d = compute_delta("guided_counted")
    assert d.passive_delta == 1
    assert d.active_delta == 1
    assert d.times_used_correctly_delta == 1
    assert d.times_seen_delta == 0
    assert d.passive_srs == "correct"
    assert d.active_srs == "correct"


def test_compute_delta_guided_used():
    d = compute_delta("guided_used")
    assert d.passive_delta == 1
    assert d.active_delta == 0
    assert d.times_used_correctly_delta == 0
    assert d.passive_srs == "correct"
    assert d.active_srs is None


def test_compute_delta_guided_not_used():
    d = compute_delta("guided_not_used")
    assert d.passive_delta == 0
    assert d.active_delta == 0
    assert d.passive_srs is None
    assert d.active_srs == "incorrect"


def test_compute_delta_status_marked_learning():
    d = compute_delta("status_marked_learning")
    assert d.passive_delta == 1
    assert d.active_delta == 0
    assert d.times_seen_delta == 1
    assert d.passive_srs == "create"
    assert d.active_srs is None


def test_compute_delta_status_marked_known():
    d = compute_delta("status_marked_known")
    assert d.passive_delta == 3
    assert d.active_delta == 1
    assert d.times_used_correctly_delta == 1
    assert d.passive_srs == "correct"
    assert d.active_srs == "correct"


def test_compute_delta_status_marked_unknown():
    d = compute_delta("status_marked_unknown")
    assert d == ProgressionDelta()  # all zeros, no SRS


def test_compute_delta_unknown_event_raises():
    with pytest.raises(ValueError, match="Unknown progression event"):
        compute_delta("definitely_not_a_real_event")


def test_compute_delta_returns_frozen_dataclass():
    d = compute_delta("guided_counted")
    with pytest.raises(Exception):
        d.passive_delta = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration tests — real DB
# ---------------------------------------------------------------------------

async def test_guided_counted_updates_levels(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_counted")

    row = await _get_uwk(db_pool, uid, wid)
    assert row is not None
    assert row["passive_level"] == 1
    assert row["active_level"] == 1
    assert row["times_used_correctly"] == 1


async def test_guided_counted_creates_active_srs_card(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_counted")

    card = await _get_srs(db_pool, uid, wid, "active")
    assert card is not None
    assert card["repetitions"] == 1


async def test_guided_counted_creates_passive_srs_card(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_counted")

    card = await _get_srs(db_pool, uid, wid, "passive")
    assert card is not None
    assert card["repetitions"] == 1


async def test_guided_counted_promotes_to_known_at_threshold(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    for _ in range(ACTIVE_MASTERY_THRESHOLD):
        await _apply(db_pool, uid, wid, "guided_counted")

    row = await _get_uwk(db_pool, uid, wid)
    assert row["status"] == "known"
    assert row["active_level"] == ACTIVE_MASTERY_THRESHOLD


async def test_guided_counted_srs_advances_on_repeat(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_counted")
    card_after_1 = await _get_srs(db_pool, uid, wid, "active")

    await _apply(db_pool, uid, wid, "guided_counted")
    card_after_2 = await _get_srs(db_pool, uid, wid, "active")

    assert card_after_2["interval_days"] > card_after_1["interval_days"]
    assert card_after_2["repetitions"] == 2


async def test_guided_used_updates_passive_only(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_used")

    row = await _get_uwk(db_pool, uid, wid)
    assert row["passive_level"] == 1
    assert row["active_level"] == 0
    assert row["times_used_correctly"] == 0


async def test_guided_used_does_not_create_active_srs_card(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_used")

    card = await _get_srs(db_pool, uid, wid, "active")
    assert card is None


async def test_guided_not_used_does_not_touch_levels(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_not_used")

    row = await _get_uwk(db_pool, uid, wid)
    # Row may not even exist if there were no prior events
    if row is not None:
        assert row["passive_level"] == 0
        assert row["active_level"] == 0


async def test_guided_not_used_penalises_existing_active_card(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    # Create a card with ease > 1.3 so we can detect penalisation
    await _apply(db_pool, uid, wid, "guided_counted")
    card_before = await _get_srs(db_pool, uid, wid, "active")
    assert card_before is not None

    await _apply(db_pool, uid, wid, "guided_not_used")
    card_after = await _get_srs(db_pool, uid, wid, "active")

    assert card_after["interval_days"] == 1.0    # reset to 1 on incorrect
    assert card_after["repetitions"] == 0
    assert card_after["ease_factor"] < card_before["ease_factor"]


async def test_guided_not_used_noop_when_no_card(db_pool):
    """guided_not_used with no existing card should not raise or create anything."""
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "guided_not_used")  # should not raise

    card = await _get_srs(db_pool, uid, wid, "active")
    assert card is None


async def test_status_marked_learning_creates_passive_card(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "status_marked_learning")

    card = await _get_srs(db_pool, uid, wid, "passive")
    assert card is not None
    assert card["repetitions"] == 0    # 'create' action — not advanced yet


async def test_status_marked_learning_does_not_create_active_card(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "status_marked_learning")

    card = await _get_srs(db_pool, uid, wid, "active")
    assert card is None


async def test_status_marked_known_creates_both_cards(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "status_marked_known")

    assert await _get_srs(db_pool, uid, wid, "passive") is not None
    assert await _get_srs(db_pool, uid, wid, "active") is not None


async def test_status_marked_known_boosts_both_levels(db_pool):
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    await _apply(db_pool, uid, wid, "status_marked_known")

    row = await _get_uwk(db_pool, uid, wid)
    assert row["passive_level"] == 3
    assert row["active_level"] == 1
    assert row["times_used_correctly"] == 1


async def test_passive_promotion_to_learning(db_pool):
    """Accumulating passive exposures auto-promotes from 'unknown' to 'learning'."""
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    # Each guided_used gives passive_delta=1; hit PASSIVE_PROMOTION_THRESHOLD
    for _ in range(PASSIVE_PROMOTION_THRESHOLD):
        await _apply(db_pool, uid, wid, "guided_used")

    row = await _get_uwk(db_pool, uid, wid)
    assert row["passive_level"] == PASSIVE_PROMOTION_THRESHOLD
    assert row["status"] == "learning"


async def test_active_mastery_overrides_passive_promotion(db_pool):
    """If active_level hits mastery while status is 'unknown', word goes straight to 'known'."""
    uid = await _make_user(db_pool)
    wid = await _get_word_id(db_pool)

    for _ in range(ACTIVE_MASTERY_THRESHOLD):
        await _apply(db_pool, uid, wid, "guided_counted")

    row = await _get_uwk(db_pool, uid, wid)
    assert row["status"] == "known"   # not just 'learning'
