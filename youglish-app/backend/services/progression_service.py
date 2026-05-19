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
active_level  >= ACTIVE_MASTERY_THRESHOLD    (3)  AND status != 'known'
  → auto-promote to 'known'   (active mastery wins)
passive_level >= PASSIVE_PROMOTION_THRESHOLD (5)  AND status == 'learning'
  → auto-promote to 'known'   (Hole 9 — passively mastered items exit 'learning')
passive_level >= PASSIVE_PROMOTION_THRESHOLD (5)  AND status == 'unknown'
  → auto-promote to 'learning'

Both passive transitions share the per-user setting users.settings.passive_reps_for_known
(default 5). Default per-call ordering: 'unknown' crosses the threshold first,
becomes 'learning'; a subsequent passive event becomes 'known'.

Implemented event hooks (wired to existing code paths)
-------------------------------------------------------
  guided_counted         — guided chat, target_used AND target_counted
  guided_used            — guided chat, target_used AND NOT target_counted
  guided_not_used        — guided chat, NOT target_used
  status_marked_learning — user set status → 'learning'
  status_marked_known    — user set status → 'known'
  status_marked_unknown  — user set status → 'unknown'
  passive_review_correct  — SRS passive card answered correctly
  passive_review_incorrect — SRS passive card answered incorrectly
  active_review_correct   — SRS active card answered correctly
  active_review_incorrect — SRS active card answered incorrectly

Implemented event hooks (continued)
------------------------------------
  transcript_clicked     — user left-clicked a word in subtitle/transcript panel

Planned but deferred (no code path fires these yet)
---------------------------------------------------
  transcript_seen

SRS actions
-----------
  'correct'  — advance existing card (SM-2), or create + advance if missing
  'incorrect' — penalise existing card (SM-2), or no-op if missing
  'create'   — insert card with defaults if missing, no-op if exists
  'reset'    — ensure card exists AND force due_date=NOW+1d, interval=1, reps=0
               (ease_factor preserved on existing cards). Used by manual
               demotion known → learning (Hole 26).

Manual demotion (Hole 26)
-------------------------
When the router calls apply_progression with status_override demoting the item
(known → learning / known → unknown / learning → unknown), the additive rule
table is the WRONG model — we'd add evidence to a self-correction. Instead a
dedicated demotion branch resets levels and reschedules cards:

  known → learning:  passive_level := 1, active_level := 0, both SRS 'reset'
  known → unknown:   passive_level := 0, active_level := 0, both SRS 'incorrect'
  learning → unknown: passive_level := 0, active_level := 0, both SRS 'incorrect'

times_seen and times_used_correctly are NOT touched — they record history.
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from backend.services import settings_service

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
    # Marking 'learning': user has seen the word, wants to practise it.
    # Creates BOTH passive and active SRS cards so the active-direction queue
    # isn't permanently empty for users who don't open guided chat.
    "status_marked_learning": ProgressionDelta(
        passive_delta=1, times_seen_delta=1,
        passive_srs="create", active_srs="create",
    ),
    # Marking 'known' is USER CONFIDENCE — a self-classification, NOT proof of
    # production. The status field is written inside apply_progression's
    # transaction when the router passes status_override='known'. Here we ONLY
    # advance the passive SRS card (defensible: the user is claiming passive
    # recognition).
    #
    # Intentional choices:
    #   - passive_delta=0      → leave passive_level unchanged. The level field
    #                            reflects accumulated *evidence*; manual marking is
    #                            self-classification, not new exposure evidence.
    #                            (Option A from the design note — no fabrication.)
    #   - active_delta=0       → manual known must NOT inflate active mastery.
    #                            Active level only grows from real production
    #                            events: guided_counted, free_chat_used_correctly,
    #                            active_review_correct.
    #   - times_used_correctly_delta=0 → that counter tracks correct production,
    #                            not confidence clicks.
    #   - passive_srs="correct" → advance the passive card (or create it at 1 day
    #                            if missing). Filtered from /srs/due by the
    #                            status='known' check anyway.
    #   - active_srs=None      → DO NOT create or advance the active SRS card.
    #                            Fabricating active progress is the bug this rule
    #                            change closes.
    "status_marked_known": ProgressionDelta(
        passive_srs="correct",
    ),
    # Marking 'unknown' is the user saying "I don't know this anymore" — the SRS
    # schedule should bring it back soon. We knock down whichever cards already
    # exist via the SM-2 incorrect branch (which sets interval=1 day, ease-0.15,
    # reps=0). Levels are intentionally left alone (no fabrication, mirroring
    # status_marked_known's choice).
    #
    # Important: action='incorrect' in _update_srs is a no-op when the card is
    # missing (see line ~333). So this rule will NEVER create an active card
    # just because the user clicked Unknown — it only resets cards that the
    # user already had from earlier activity.
    "status_marked_unknown": ProgressionDelta(
        passive_srs="incorrect", active_srs="incorrect",
    ),

    # --- Transcript interaction ---
    # transcript_clicked: user left-clicked a word in the subtitle/transcript.
    # passive_delta=1 (same weight as other passive exposure events).
    # passive_srs="create": adds to review queue if not already there, but does NOT
    # advance an existing scheduled card — a click is not a review answer.
    "transcript_clicked": ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="create"),
    # transcript_seen (future): fires for every word visible in the subtitle display.
    # Deferred — too noisy without playback-timing + deduplication infrastructure.
    # "transcript_seen": ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="create"),

    # --- Free chat (server-side token matching against user's learning vocab) ---
    # matched:        word appeared in user's message, language context unknown / not yet classified
    # used_correctly: word appeared and language_detected == 'de' (correct German production)
    # mixed_lang:     word appeared and language_detected == 'mixed' (passive credit only)
    "free_chat_matched":        ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="correct"),
    "free_chat_used_correctly": ProgressionDelta(passive_delta=1, active_delta=1, times_used_correctly_delta=1, passive_srs="correct", active_srs="correct"),
    "free_chat_mixed_lang":     ProgressionDelta(passive_delta=1, times_seen_delta=1, passive_srs="correct"),

    # --- SRS reviews ---
    # A controlled review is stronger evidence than a subtitle click — both
    # should grow the "Understood" passive_level metric. Previously
    # passive_review_correct had passive_delta=0, which meant successful reviews
    # never moved the dots while subtitle clicks did. Inconsistent; fixed.
    "passive_review_correct":  ProgressionDelta(passive_delta=1, passive_srs="correct"),
    "passive_review_incorrect": ProgressionDelta(passive_srs="incorrect"),
    "active_review_correct":   ProgressionDelta(passive_delta=1, active_delta=1, times_used_correctly_delta=1, active_srs="correct"),
    "active_review_incorrect": ProgressionDelta(active_srs="incorrect"),
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
    *,
    status_override: str | None = None,
) -> dict | None:
    """
    Apply the progression delta for *event* inside a single transaction.

    Steps (all inside one `async with conn.transaction()`):
      1. If status_override is provided OR there are level/counter changes,
         upsert user_word_knowledge. When status_override is set, the status
         column is written in the same statement — making the router-level
         "set status then apply progression" sequence atomic.
      2. If level deltas applied, check whether new levels trigger automatic
         status promotion.
      3. Update SRS cards in the affected direction(s).

    Returns the post-transaction user_word_knowledge row as a dict when a write
    happened (status_override or level deltas), or None otherwise. Callers that
    don't need the row (e.g. SRS reviews) can ignore the return value.

    status_override
    ---------------
    Used by routers/words.py:update_status to fold the explicit status flip
    into the same transaction as the rule's level/SRS changes. Single writer
    to user_word_knowledge.status — eliminates the silent-failure window
    between two separate transactions.
    """
    delta = compute_delta(event)
    prefs = await settings_service.get_preferences(pool, user_id)
    passive_threshold = prefs["passive_reps_for_known"]
    active_threshold = prefs["active_reps_for_known"]

    has_level_changes = bool(
        delta.passive_delta or delta.active_delta
        or delta.times_seen_delta or delta.times_used_correctly_delta
    )
    needs_uwk_write = has_level_changes or status_override is not None

    async with pool.acquire() as conn:
        async with conn.transaction():
            # ----- Manual demotion (Hole 26) ----------------------------------
            # If status_override demotes the row's existing status, we ignore
            # the additive rule and reset levels + reschedule cards. Detect by
            # reading prior status inside the same transaction.
            if status_override is not None:
                prior_status = await conn.fetchval(
                    """
                    SELECT status FROM user_word_knowledge
                     WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
                    """,
                    user_id, item_id, item_type,
                )
                if _is_demotion(prior_status, status_override):
                    return await _apply_demotion(
                        conn, user_id, item_id, item_type, status_override,
                    )

            row = None

            if needs_uwk_write:
                # status_override is written on both INSERT (initial status) and
                # UPDATE (overwrite existing status). When None, default 'unknown'
                # is used for INSERT and the existing status is preserved on UPDATE.
                if status_override is not None:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO user_word_knowledge
                            (user_id, item_id, item_type, status,
                             passive_level, active_level,
                             times_seen, times_used_correctly, last_seen)
                        VALUES ($1::uuid, $2, $3, $4,
                                $5, $6, $7, $8, NOW())
                        ON CONFLICT (user_id, item_id, item_type) DO UPDATE SET
                            status               = $4,
                            passive_level        = user_word_knowledge.passive_level        + $5,
                            active_level         = user_word_knowledge.active_level         + $6,
                            times_seen           = user_word_knowledge.times_seen           + $7,
                            times_used_correctly = user_word_knowledge.times_used_correctly + $8,
                            last_seen            = NOW()
                        RETURNING passive_level, active_level, status
                        """,
                        user_id, item_id, item_type, status_override,
                        delta.passive_delta, delta.active_delta,
                        delta.times_seen_delta, delta.times_used_correctly_delta,
                    )
                else:
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

                if has_level_changes:
                    await _maybe_promote(conn, user_id, item_id, item_type, row,
                                         passive_threshold, active_threshold)

            if delta.passive_srs:
                await _update_srs(conn, user_id, item_id, item_type, "passive", delta.passive_srs)
            if delta.active_srs:
                await _update_srs(conn, user_id, item_id, item_type, "active", delta.active_srs)

            # Re-fetch the final row so callers (e.g. the HTTP route) see post-
            # promotion status without an extra round-trip. Only when a write
            # happened — otherwise return None.
            if needs_uwk_write:
                final = await conn.fetchrow(
                    """
                    SELECT item_id, item_type, status,
                           passive_level, active_level,
                           times_seen, times_used_correctly,
                           notes, last_seen
                      FROM user_word_knowledge
                     WHERE user_id = $1::uuid
                       AND item_id = $2
                       AND item_type = $3
                    """,
                    user_id, item_id, item_type,
                )
                return dict(final) if final else None
            return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_STATUS_RANK = {"unknown": 0, "learning": 1, "known": 2}


def _is_demotion(prior_status: str | None, new_status: str) -> bool:
    """True iff new_status sits strictly lower on the unknown < learning < known scale.

    Pure helper — testable without a DB. If prior_status is None (row doesn't
    exist yet), nothing is being demoted.
    """
    if prior_status is None:
        return False
    return _STATUS_RANK.get(new_status, -1) < _STATUS_RANK.get(prior_status, -1)


async def _apply_demotion(
    conn: asyncpg.Connection,
    user_id: str,
    item_id: int,
    item_type: str,
    new_status: str,
) -> dict | None:
    """Manual demotion (Hole 26): user reclassified the item downward.

    Policy:
      known → learning: passive_level=1, active_level=0, both SRS 'reset'
      known → unknown:  passive_level=0, active_level=0, both SRS 'incorrect'
      learning → unknown: passive_level=0, active_level=0, both SRS 'incorrect'

    Why not negative deltas on the rule? Because the target value depends on
    the destination status, not on the prior level — a known item with
    active_level=12 should drop to 0 regardless of how high it climbed.
    Additive deltas can't express that without per-row computation.

    times_seen and times_used_correctly are preserved — they record what
    actually happened. The user is correcting their classification, not
    rewriting history.

    Auto-promotion (_maybe_promote) is NOT called. With the chosen targets
    (passive ≤ 1, active = 0) no threshold can be crossed at any setting in
    the schema range (1-20), and even at threshold=1 the demotion is the
    user's explicit override.
    """
    if new_status == "learning":
        new_passive, new_active = 1, 0
        passive_action, active_action = "reset", "reset"
    elif new_status == "unknown":
        new_passive, new_active = 0, 0
        passive_action, active_action = "incorrect", "incorrect"
    else:
        # Demotion only fires when new_status is 'learning' or 'unknown' per
        # _is_demotion. This branch is unreachable, but defensive.
        raise ValueError(f"_apply_demotion called with non-demotion status: {new_status!r}")

    await conn.execute(
        """
        UPDATE user_word_knowledge SET
            status        = $4,
            passive_level = $5,
            active_level  = $6,
            last_seen     = NOW()
         WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
        """,
        user_id, item_id, item_type, new_status, new_passive, new_active,
    )

    await _update_srs(conn, user_id, item_id, item_type, "passive", passive_action)
    await _update_srs(conn, user_id, item_id, item_type, "active", active_action)

    row = await conn.fetchrow(
        """
        SELECT item_id, item_type, status,
               passive_level, active_level,
               times_seen, times_used_correctly,
               notes, last_seen
          FROM user_word_knowledge
         WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
        """,
        user_id, item_id, item_type,
    )
    return dict(row) if row else None


async def _maybe_promote(
    conn: asyncpg.Connection,
    user_id: str,
    item_id: int,
    item_type: str,
    row: asyncpg.Record,
    passive_threshold: int = PASSIVE_PROMOTION_THRESHOLD,
    active_threshold: int = ACTIVE_MASTERY_THRESHOLD,
) -> None:
    """Promote status if levels cross thresholds.

    Order of precedence (only one branch fires per call):
      1. active_level >= active_threshold AND status != 'known'  → 'known'
      2. passive_level >= passive_threshold AND status == 'learning' → 'known'   (Hole 9)
      3. passive_level >= passive_threshold AND status == 'unknown'  → 'learning'

    Branch (2) is the Hole 9 fix: 'learning' was a one-way trap — a user could
    pass passive_review_correct dozens of times and the dots would grow but
    status would stay 'learning' forever. Now passive mastery crosses the same
    threshold the user already configured as 'reps for known'. Active SRS cards
    are not touched here; only the status field flips.
    """
    passive_level = row["passive_level"]
    active_level = row["active_level"]
    current_status = row["status"]

    if active_level >= active_threshold and current_status != "known":
        await conn.execute(
            """
            UPDATE user_word_knowledge
               SET status = 'known', last_seen = NOW()
             WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
            """,
            user_id, item_id, item_type,
        )
    elif passive_level >= passive_threshold and current_status == "learning":
        await conn.execute(
            """
            UPDATE user_word_knowledge
               SET status = 'known', last_seen = NOW()
             WHERE user_id = $1::uuid AND item_id = $2 AND item_type = $3
            """,
            user_id, item_id, item_type,
        )
    elif passive_level >= passive_threshold and current_status == "unknown":
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
    # Grammar rules are passive-only: a rule like "trennbare Verben" isn't
    # something the user "produces" — it's recognised and applied. Skip active
    # card creation for this item type.
    if item_type == "grammar_rule" and direction == "active":
        return

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

    if action == "reset":
        # Hole 26: manual demotion known → learning. Ensure the card exists
        # and force a near-future review. Ease is preserved on existing cards
        # (we're rescheduling, not penalising — that distinguishes 'reset'
        # from 'incorrect'). On INSERT path the default ease 2.5 is used.
        await conn.execute(
            """
            INSERT INTO srs_cards
                (user_id, item_id, item_type, direction,
                 due_date, interval_days, ease_factor, repetitions)
            VALUES ($1::uuid, $2, $3, $4,
                    NOW() + INTERVAL '1 day', 1.0, 2.5, 0)
            ON CONFLICT (user_id, item_id, item_type, direction) DO UPDATE SET
                due_date      = NOW() + INTERVAL '1 day',
                interval_days = 1.0,
                repetitions   = 0
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
