"""
Passive vs active knowledge progression — single source of truth.

All knowledge-state changes funnel through apply_progression(). The rule table
(compute_delta) is a pure Python dict, fully unit-testable without a database.

Tracks
------
passive  — user can recognise/understand the word in context
           grows from: reading, exposure, status changes, SRS passive reviews
active   — user can produce/use the word correctly
           grows from: guided chat correct use, SRS active reviews, manual 'known'

Status promotion (automatic)
-----------------------------
passive_level >= PASSIVE_PROMOTION_THRESHOLD (5)  AND status == 'unknown'
  → auto-promote to 'learning'
active_level  >= ACTIVE_MASTERY_THRESHOLD    (3)  AND status != 'known'
  → auto-promote to 'known'

Implemented event hooks (wired to existing code paths)
-------------------------------------------------------
  guided_counted        — guided chat, target_used AND target_counted
  guided_used           — guided chat, target_used AND NOT target_counted
  guided_not_used       — guided chat, NOT target_used
  status_marked_learning — user set status → 'learning'
  status_marked_known    — user set status → 'known'
  status_marked_unknown  — user set status → 'unknown'

Planned but deferred (no code path fires these yet)
---------------------------------------------------
  transcript_seen, transcript_clicked
  free_chat_matched, free_chat_used_correctly, free_chat_mixed_lang
  passive_review_correct/incorrect, active_review_correct/incorrect

SRS actions
-----------
  'correct'  — advance existing card (SM-2), or create + advance if missing
  'incorrect' — penalise existing card (SM-2), or no-op if missing
  'create'   — insert card with defaults if missing, no-op if exists
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncpg

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

PASSIVE_PROMOTION_THRESHOLD = 5   # passive_level >= 5 → 'unknown' becomes 'learning'
ACTIVE_MASTERY_THRESHOLD = 3      # active_level >= 3 → any status becomes 'known'


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProgressionDelta:
    passive_delta: int = 0
    active_delta: int = 0
    times_seen_delta: int = 0
    times_used_correctly_delta: int = 0
    passive_srs: str | None = None   # 'correct' | 'incorrect' | 'create' | None
    active_srs: str | None = None    # 'correct' | 'incorrect' | 'create' | None


# The single source of truth: event name → what changes in the knowledge model.
# Add future events here; everything else stays the same.
_RULES: dict[str, ProgressionDelta] = {
    # --- Guided chat ---
    # target_counted=True: natural, correct German usage → both tracks advance
    "guided_counted": ProgressionDelta(
        passive_delta=1, active_delta=1,
        times_used_correctly_delta=1,
        passive_srs="correct", active_srs="correct",
    ),
    # target_used=True, target_counted=False: tried but not in natural/correct German
    # → passive recognition grows (you engaged), active production does not advance
    "guided_used": ProgressionDelta(
        passive_delta=1,
        passive_srs="correct",
    ),
    # target not used at all → penalise active SRS only
    "guided_not_used": ProgressionDelta(
        active_srs="incorrect",
    ),

    # --- Manual status changes ---
    # Marking 'learning': user has seen the word, wants to practise it
    "status_marked_learning": ProgressionDelta(
        passive_delta=1, times_seen_delta=1,
        passive_srs="create",
    ),
    # Marking 'known': user claims mastery of both tracks
    "status_marked_known": ProgressionDelta(
        passive_delta=3, active_delta=1,
        times_used_correctly_delta=1,
        passive_srs="correct", active_srs="correct",
    ),
    # Marking 'unknown': reset intention, but keep accumulated level data
    "status_marked_unknown": ProgressionDelta(),

    # --- Future: transcript ---
    # "transcript_seen":    ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="correct"),
    # "transcript_clicked": ProgressionDelta(passive_delta=2, times_seen_delta=1, passive_srs="correct"),

    # --- Future: free chat (once word_matches is populated) ---
    # "free_chat_matched":        ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="correct"),
    # "free_chat_used_correctly": ProgressionDelta(passive_delta=1, active_delta=1, times_used_correctly_delta=1, passive_srs="correct", active_srs="correct"),
    # "free_chat_mixed_lang":     ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="correct"),

    # --- Future: SRS reviews ---
    # "passive_review_correct":   ProgressionDelta(passive_srs="correct"),
    # "passive_review_incorrect":  ProgressionDelta(passive_srs="incorrect"),
    # "active_review_correct":    ProgressionDelta(passive_delta=1, active_delta=1, times_used_correctly_delta=1, active_srs="correct"),
    # "active_review_incorrect":  ProgressionDelta(active_srs="incorrect"),
}


def compute_delta(event: str) -> ProgressionDelta:
    """
    Pure function — maps an event name to a ProgressionDelta.

    Raises ValueError for unknown events so callers notice typos immediately.
    """
    try:
        return _RULES[event]
    except KeyError:
        raise ValueError(f"Unknown progression event: {event!r}. Valid events: {sorted(_RULES)}")


# ---------------------------------------------------------------------------
# DB application
# ---------------------------------------------------------------------------

async def apply_progression(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    event: str,
) -> None:
    """
    Apply the progression delta for *event* inside a single transaction.

    Steps:
      1. If any level/counter changes, upsert user_word_knowledge (increments only;
         status is not changed here — only by promotion logic below).
      2. Check whether the new levels trigger automatic status promotion.
      3. Update SRS cards in the affected direction(s).
    """
    delta = compute_delta(event)

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = None

            if (delta.passive_delta or delta.active_delta
                    or delta.times_seen_delta or delta.times_used_correctly_delta):
                row = await conn.fetchrow(
                    """
                    INSERT INTO user_word_knowledge
                        (user_id, item_id, item_type, status,
                         passive_level, active_level,
                         times_seen, times_used_correctly, last_seen)
                    VALUES ($1::uuid, $2, $3, 'unknown',
                            $4, $5, $6, $7, NOW())
                    ON CONFLICT (user_id, item_id, item_type) DO UPDATE SET
                        passive_level        = user_word_knowledge.passive_level        + $4,
                        active_level         = user_word_knowledge.active_level         + $5,
                        times_seen           = user_word_knowledge.times_seen           + $6,
                        times_used_correctly = user_word_knowledge.times_used_correctly + $7,
                        last_seen            = NOW()
                    RETURNING passive_level, active_level, status
                    """,
                    user_id, item_id, item_type,
                    delta.passive_delta, delta.active_delta,
                    delta.times_seen_delta, delta.times_used_correctly_delta,
                )

                await _maybe_promote(conn, user_id, item_id, item_type, row)

            if delta.passive_srs:
                await _update_srs(conn, user_id, item_id, item_type, "passive", delta.passive_srs)
            if delta.active_srs:
                await _update_srs(conn, user_id, item_id, item_type, "active", delta.active_srs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _maybe_promote(
    conn: asyncpg.Connection,
    user_id: str,
    item_id: int,
    item_type: str,
    row: asyncpg.Record,
) -> None:
    """Promote status if levels cross thresholds. Active mastery takes precedence."""
    passive_level = row["passive_level"]
    active_level = row["active_level"]
    current_status = row["status"]

    if active_level >= ACTIVE_MASTERY_THRESHOLD and current_status != "known":
        await conn.execute(
            """
            UPDATE user_word_knowledge
               SET status = 'known', last_seen = NOW()
             WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
            """,
            user_id, item_id, item_type,
        )
    elif passive_level >= PASSIVE_PROMOTION_THRESHOLD and current_status == "unknown":
        await conn.execute(
            """
            UPDATE user_word_knowledge
               SET status = 'learning', last_seen = NOW()
             WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
            """,
            user_id, item_id, item_type,
        )


async def _update_srs(
    conn: asyncpg.Connection,
    user_id: str,
    item_id: int,
    item_type: str,
    direction: str,
    action: str,          # 'correct' | 'incorrect' | 'create'
) -> None:
    """
    Apply SM-2 scheduling or create an SRS card for the given direction.

    'create'   — insert with defaults; no-op if card already exists
    'correct'  — create (if missing) and advance interval (SM-2 correct branch)
    'incorrect' — penalise existing card; no-op if missing
    """
    if action == "create":
        await conn.execute(
            """
            INSERT INTO srs_cards
                (user_id, item_id, item_type, direction,
                 due_date, interval_days, ease_factor, repetitions)
            VALUES ($1::uuid, $2, $3, $4,
                    NOW(), 1.0, 2.5, 0)
            ON CONFLICT (user_id, item_id, item_type, direction) DO NOTHING
            """,
            user_id, item_id, item_type, direction,
        )
        return

    card = await conn.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions
          FROM srs_cards
         WHERE user_id   = $1::uuid
           AND item_id   = $2
           AND item_type = $3
           AND direction = $4
        """,
        user_id, item_id, item_type, direction,
    )

    if card is None:
        if action == "correct":
            # First correct review: create card and schedule it one day out
            await conn.execute(
                """
                INSERT INTO srs_cards
                    (user_id, item_id, item_type, direction,
                     due_date, interval_days, ease_factor, repetitions, last_review)
                VALUES ($1::uuid, $2, $3, $4,
                        NOW() + INTERVAL '1 day', 1.0, 2.5, 1, NOW())
                ON CONFLICT (user_id, item_id, item_type, direction) DO NOTHING
                """,
                user_id, item_id, item_type, direction,
            )
        # 'incorrect' with no card → nothing to penalise
        return

    if action == "correct":
        new_interval = card["interval_days"] * card["ease_factor"]
        new_ease = min(card["ease_factor"] + 0.05, 3.0)
        new_reps = card["repetitions"] + 1
    else:  # 'incorrect'
        new_interval = 1.0
        new_ease = max(card["ease_factor"] - 0.15, 1.3)
        new_reps = 0

    await conn.execute(
        """
        UPDATE srs_cards
           SET interval_days = $1,
               ease_factor   = $2,
               repetitions   = $3,
               due_date      = NOW() + ($1::float * INTERVAL '1 day'),
               last_review   = NOW()
         WHERE user_id   = $4::uuid
           AND item_id   = $5
           AND item_type = $6
           AND direction = $7
        """,
        new_interval, new_ease, new_reps,
        user_id, item_id, item_type, direction,
    )
