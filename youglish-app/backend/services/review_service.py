"""
review_service.py

SRS review session — uses the srs_cards table and SM-2 scheduling from
progression_service. Single source of truth for `/api/v1/srs/due` and
`/api/v1/srs/review/{card_id}`.

Two public functions:
  get_due_cards(pool, user_id, language, limit) -> list[dict]
    Returns due cards with display text resolved from word/phrase/grammar tables.

  submit_answer(pool, user_id, card_id, correct) -> dict
    Applies SM-2 advancement via progression_service, records analytics event.
"""
from __future__ import annotations

import asyncio

import asyncpg

from . import llm_service, progression_service, usage_events_service


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
            END AS display_text,
            -- grammar_rule's short_explanation is used as the 'answer' side
            -- of a grammar review; word/phrase get an LLM gloss instead (below).
            gr.short_explanation AS grammar_explanation
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

    # Enrich each card with prompt_text + answer_text (#0a-1).
    #
    # word / phrase:
    #   gloss = LLM-translated short English (cached permanently)
    # grammar_rule:
    #   gloss = the rule's short_explanation (already English, no LLM call)
    #
    # Glosses for word/phrase are batched via asyncio.gather so a 30-card review
    # session with all cache misses still runs in one parallel LLM round-trip.
    rows_with_gloss: list[dict] = []
    gloss_tasks: list[tuple[int, asyncio.Task]] = []

    for idx, row in enumerate(rows):
        card = dict(row)
        if card["item_type"] == "grammar_rule":
            # Grammar rules ship with their own English explanation; no LLM needed.
            card["_gloss"] = card.get("grammar_explanation") or card["display_text"]
            rows_with_gloss.append(card)
        else:
            # word / phrase — schedule an LLM gloss lookup (cache-first).
            card["_gloss"] = None  # filled in below
            rows_with_gloss.append(card)
            gloss_tasks.append((
                idx,
                asyncio.create_task(
                    llm_service.translate_item_gloss(
                        card["display_text"], card["item_type"], language, pool=pool,
                    )
                ),
            ))

    if gloss_tasks:
        results = await asyncio.gather(*(t for _, t in gloss_tasks), return_exceptions=True)
        for (idx, _task), result in zip(gloss_tasks, results):
            if isinstance(result, BaseException):
                # Be defensive: a gloss failure must not break the review session.
                # Fall back to display_text so prompt/answer fields are still populated.
                rows_with_gloss[idx]["_gloss"] = rows_with_gloss[idx]["display_text"]
            else:
                rows_with_gloss[idx]["_gloss"] = result

    out: list[dict] = []
    for card in rows_with_gloss:
        gloss = card.pop("_gloss")
        card.pop("grammar_explanation", None)
        display = card["display_text"]
        if card["direction"] == "passive":
            card["prompt_text"] = display
            card["answer_text"] = gloss
        else:  # active
            card["prompt_text"] = gloss
            card["answer_text"] = display
        out.append(card)
    return out


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


# ---------------------------------------------------------------------------
# Active production review (#0a-2)
# ---------------------------------------------------------------------------

def _normalize_for_match(s: str) -> str:
    """Lower-case + collapse whitespace + strip terminal punctuation.

    The fast-path comparator: identical-after-normalize answers skip the LLM.
    Intentionally narrow — anything more lenient (typo tolerance, stem matching)
    is left to the LLM evaluator.
    """
    import re
    return re.sub(r"\s+", " ", (s or "").strip().lower()).rstrip(".!?,;:")


async def submit_production_answer(
    pool: asyncpg.Pool,
    user_id: str,
    card_id: int,
    answer: str,
) -> dict:
    """Score a user's typed German answer against an active SRS card.

    Flow:
      1. Validate ownership + that the card is an active card.
      2. Reject grammar_rule cards (they're passive-only by design).
      3. Resolve the target text + lemma from the relevant content table.
      4. Fast path: normalized exact match → correct, no LLM call.
      5. Slow path: call llm_service.evaluate_production.
      6. Route the result through the normal SRS event pipeline
         (active_review_correct / active_review_incorrect) so progression /
         SM-2 / analytics all run exactly as they would for a self-graded review.
      7. Return feedback for the frontend's after-submit panel.

    Returns:
        {
          "card_id": int,
          "correct": bool,
          "expected": str,    # the target_text the user should have produced
          "submitted": str,   # what the user actually typed (echoed back)
          "feedback": str,    # one-sentence explanation
        }

    Raises:
        ValueError("card_not_found")   — wrong owner or no such card
        ValueError("passive_card")     — card is direction='passive'
        ValueError("grammar_rule")     — card targets a grammar rule
        ValueError("target_missing")   — content row gone after card was issued
    """
    card = await pool.fetchrow(
        """
        SELECT item_id, item_type, direction
          FROM srs_cards
         WHERE card_id = $1
           AND user_id = $2::uuid
        """,
        card_id, user_id,
    )
    if card is None:
        raise ValueError("card_not_found")
    if card["direction"] != "active":
        raise ValueError("passive_card")
    if card["item_type"] == "grammar_rule":
        raise ValueError("grammar_rule")

    item_id   = card["item_id"]
    item_type = card["item_type"]

    # Resolve target text + lemma + language.
    if item_type == "word":
        target_row = await pool.fetchrow(
            "SELECT word AS target_text, lemma AS target_lemma, language "
            "FROM word_table WHERE word_id = $1",
            item_id,
        )
    else:   # phrase
        target_row = await pool.fetchrow(
            "SELECT surface_form AS target_text, canonical AS target_lemma, language "
            "FROM phrase_table WHERE phrase_id = $1",
            item_id,
        )

    if target_row is None:
        raise ValueError("target_missing")

    target_text  = target_row["target_text"]
    target_lemma = target_row["target_lemma"]
    language     = target_row["language"]

    # Fast path: normalized exact match. Skip LLM call.
    if _normalize_for_match(answer) == _normalize_for_match(target_text):
        correct = True
        feedback = "Exact match."
        corrected_form = target_text
    else:
        eval_result = await llm_service.evaluate_production(
            target_text, target_lemma, answer, language,
        )
        correct        = eval_result["correct"]
        feedback       = eval_result["feedback"]
        corrected_form = eval_result["corrected_form"] or target_text

    # Route through the standard SRS event pipeline so SM-2 advances exactly
    # as it would for a self-graded answer. progression_service is the single
    # writer; no special-casing needed.
    event = "active_review_correct" if correct else "active_review_incorrect"
    await progression_service.apply_progression(pool, user_id, item_id, item_type, event)

    asyncio.create_task(
        usage_events_service.record_event(
            pool, user_id, item_id, item_type,
            context="srs_review",
            outcome="correct" if correct else "incorrect",
            metadata={"direction": "active", "produced": True},
        )
    )

    return {
        "card_id":   card_id,
        "correct":   correct,
        "expected":  corrected_form,
        "submitted": answer,
        "feedback":  feedback,
    }
