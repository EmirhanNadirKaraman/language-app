"""
W6 / Hole 11+16 backfill — find and create missing active SRS cards for
existing `status='learning'` items.

History
-------
Before #0b (2026-05-19), `status_marked_learning` only set
`passive_srs="create"`. Items marked learning between the project start
and the #0b fix have a passive card but no active card. The SRS review
UI hides the missing direction, so production practice never gets
scheduled for those items — they coast on passive review only.

This module is a one-shot remedial pass. New writes since #0b create
both directions already, so the audit count drops to zero once this
backfill runs.

Design choices
--------------
- Audit and backfill are pure SQL — no progression event, no usage
  event. We're fixing scheduling state, not recording evidence.
- `_update_srs("create")` semantics are mirrored verbatim:
  `due_date=NOW(), interval_days=1.0, ease_factor=2.5, repetitions=0`.
- Idempotent via the `srs_cards` unique key
  `(user_id, item_id, item_type, direction)` + `ON CONFLICT DO NOTHING`.
- `item_type='grammar_rule'` is excluded — grammar is passive-only
  (matches the guard in `progression_service._update_srs`).
- Status filter is exactly `'learning'` — known/unknown items don't
  belong in the active queue.
"""
from __future__ import annotations

import asyncpg


# Single source of the audit query. Used by both find_missing_active_cards
# (audit) and backfill_missing_active_cards (apply) so the two can never
# drift on which rows count.
_AUDIT_SQL = """
SELECT uwk.user_id, uwk.item_id, uwk.item_type
  FROM user_word_knowledge uwk
 WHERE uwk.status = 'learning'
   AND uwk.item_type IN ('word', 'phrase')
   AND NOT EXISTS (
       SELECT 1 FROM srs_cards sc
        WHERE sc.user_id   = uwk.user_id
          AND sc.item_id   = uwk.item_id
          AND sc.item_type = uwk.item_type
          AND sc.direction = 'active'
   )
"""


async def find_missing_active_cards(pool: asyncpg.Pool) -> list[dict]:
    """
    Return every (user_id, item_id, item_type) triple whose `learning` row
    has no matching active SRS card. Ordered by user_id then item_id for
    deterministic reporting.
    """
    rows = await pool.fetch(_AUDIT_SQL + "\n ORDER BY uwk.user_id, uwk.item_id")
    return [
        {
            "user_id":   str(r["user_id"]),
            "item_id":   r["item_id"],
            "item_type": r["item_type"],
        }
        for r in rows
    ]


async def backfill_missing_active_cards(pool: asyncpg.Pool, apply: bool = False) -> dict:
    """
    Audit (and optionally apply) the missing-active-card backfill.

    Returns:
        {
            "found":    int,    # number of rows that need an active card
            "inserted": int,    # number of rows actually inserted (0 when apply=False)
            "dry_run":  bool,
        }

    With `apply=False` (default), no rows are written. With `apply=True`,
    runs an `INSERT ... SELECT ... ON CONFLICT DO NOTHING` so the result
    is idempotent — re-running is safe and yields `inserted == 0` on the
    second pass.

    Crucially does NOT change:
      - user_word_knowledge.passive_level
      - user_word_knowledge.active_level
      - user_word_knowledge.status
      - user_word_knowledge.times_used_correctly
      - any existing srs_cards row (passive or active)
    """
    missing = await find_missing_active_cards(pool)
    found = len(missing)

    if not apply or found == 0:
        return {"found": found, "inserted": 0, "dry_run": not apply}

    # Mirror _update_srs("create") defaults: due NOW, interval 1d, ease 2.5,
    # reps 0. Wrap in a transaction so a partial failure doesn't leave half
    # the backfill committed.
    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.execute(
                """
                INSERT INTO srs_cards
                    (user_id, item_id, item_type, direction,
                     due_date, interval_days, ease_factor, repetitions)
                SELECT uwk.user_id, uwk.item_id, uwk.item_type, 'active',
                       NOW(), 1.0, 2.5, 0
                  FROM user_word_knowledge uwk
                 WHERE uwk.status = 'learning'
                   AND uwk.item_type IN ('word', 'phrase')
                   AND NOT EXISTS (
                       SELECT 1 FROM srs_cards sc
                        WHERE sc.user_id   = uwk.user_id
                          AND sc.item_id   = uwk.item_id
                          AND sc.item_type = uwk.item_type
                          AND sc.direction = 'active'
                   )
                ON CONFLICT (user_id, item_id, item_type, direction) DO NOTHING
                """,
            )
    # asyncpg returns "INSERT 0 N" — strip the trailing count.
    inserted = int(result.rsplit(" ", 1)[-1]) if result.startswith("INSERT") else 0
    return {"found": found, "inserted": inserted, "dry_run": False}
