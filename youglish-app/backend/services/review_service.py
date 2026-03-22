"""
review_service.py

SRS review session — the real implementation using the srs_cards table and
SM-2 scheduling from progression_service.

NOTE: The legacy srs_service.py references tables that do not exist
(word_strength, user_table, etc.) and cannot be used. All SRS logic here
uses the migration-001 schema: srs_cards + user_word_knowledge.

Two public functions:
  get_due_cards(pool, user_id, language, limit) -> list[dict]
    Returns due cards with display text resolved from word/phrase/grammar tables.

  submit_answer(pool, user_id, card_id, correct) -> dict
    Applies SM-2 advancement via progression_service, records analytics event.
"""
from __future__ import annotations

import asyncio

import asyncpg

from . import progression_service, usage_events_service


async def get_due_cards(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
    limit: int = 20,
) -> list[dict]:
    """
    Return up to `limit` SRS cards that are currently due for the given language.

    Display text is resolved by joining the item tables:
      word         → word_table.word
      phrase       → phrase_table.surface_form
      grammar_rule → grammar_rule_table.title

    The language filter is applied through those joins: cards whose item has no
    row in the language-specific table are excluded (COALESCE IS NOT NULL check).

    Ordered by due_date ASC so overdue cards are reviewed first.
    """
    rows = await pool.fetch(
        """
        SELECT
            sc.card_id,
            sc.item_id,
            sc.item_type,
            sc.direction,
            sc.due_date,
            sc.repetitions,
            COALESCE(uwk.passive_level, 0) AS passive_level,
            COALESCE(uwk.active_level,  0) AS active_level,
            CASE sc.item_type
                WHEN 'word'         THEN wt.word
                WHEN 'phrase'       THEN pt.surface_form
                WHEN 'grammar_rule' THEN gr.title
            END AS display_text
        FROM srs_cards sc
        LEFT JOIN user_word_knowledge uwk
               ON uwk.user_id   = sc.user_id
              AND uwk.item_id   = sc.item_id
              AND uwk.item_type = sc.item_type
        LEFT JOIN word_table wt
               ON sc.item_type = 'word'
              AND wt.word_id   = sc.item_id
              AND wt.language  = $3
        LEFT JOIN phrase_table pt
               ON sc.item_type  = 'phrase'
              AND pt.phrase_id  = sc.item_id
              AND pt.language   = $3
        LEFT JOIN grammar_rule_table gr
               ON sc.item_type = 'grammar_rule'
              AND gr.rule_id   = sc.item_id
              AND gr.language  = $3
        WHERE sc.user_id  = $1::uuid
          AND sc.due_date <= NOW()
          AND (uwk.status IS NULL OR uwk.status != 'known')
          AND (
              (sc.item_type = 'word'         AND wt.word_id   IS NOT NULL)
           OR (sc.item_type = 'phrase'       AND pt.phrase_id IS NOT NULL)
           OR (sc.item_type = 'grammar_rule' AND gr.rule_id   IS NOT NULL)
          )
        ORDER BY sc.due_date ASC
        LIMIT $2
        """,
        user_id,
        limit,
        language,
    )
    return [dict(r) for r in rows]


async def submit_answer(
    pool: asyncpg.Pool,
    user_id: str,
    card_id: int,
    correct: bool,
) -> dict:
    """
    Record a review answer for a single SRS card.

    Maps (direction, correct) → progression event and calls apply_progression(),
    which handles SM-2 card update + level increments + status promotion atomically.

    Analytics event recorded fire-and-forget so a logging failure never fails
    the review answer.

    Returns {"card_id": card_id, "success": True} or raises ValueError if not found.
    """
    card = await pool.fetchrow(
        """
        SELECT item_id, item_type, direction
          FROM srs_cards
         WHERE card_id = $1
           AND user_id = $2::uuid
        """,
        card_id,
        user_id,
    )
    if card is None:
        raise ValueError(f"SRS card {card_id} not found for this user")

    item_id   = card["item_id"]
    item_type = card["item_type"]
    direction = card["direction"]

    # Map to the progression event names wired in progression_service._RULES
    if direction == "passive":
        event = "passive_review_correct" if correct else "passive_review_incorrect"
    else:
        event = "active_review_correct" if correct else "active_review_incorrect"

    await progression_service.apply_progression(pool, user_id, item_id, item_type, event)

    # Analytics — fire-and-forget; never blocks or fails the response
    asyncio.create_task(
        usage_events_service.record_event(
            pool, user_id, item_id, item_type,
            context="srs_review",
            outcome="correct" if correct else "incorrect",
            metadata={"direction": direction},
        )
    )

    return {"card_id": card_id, "success": True}
