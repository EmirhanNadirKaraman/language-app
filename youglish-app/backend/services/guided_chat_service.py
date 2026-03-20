"""
Guided chat: target selection and progress updates.

Target selection priority:
  1. Soonest-due active SRS card (srs_cards, direction='active', due_date <= now)
  2. Any 'learning' word not yet in srs_cards for active direction
  3. Random word from word_table not yet in user_word_knowledge

Progress update reuses:
  - srs_cards SM-2 scheduling (interval_days, ease_factor)
  - upsert_word_status from word_service for status promotion
"""
import asyncpg

from . import word_service

# active_level threshold before a word is promoted to 'known'
MASTERY_THRESHOLD = 3


async def get_next_target(
    pool: asyncpg.Pool, user_id: str, language: str
) -> dict | None:
    """
    Return {item_id, item_type, word, lemma} for the next practice target,
    or None if word_table has no entries for this language.
    """
    async with pool.acquire() as conn:
        # Priority 1: soonest-due active SRS card
        row = await conn.fetchrow(
            """
            SELECT sc.item_id, sc.item_type, wt.word, wt.lemma
            FROM srs_cards sc
            JOIN word_table wt
              ON wt.word_id = sc.item_id AND sc.item_type = 'word'
            WHERE sc.user_id    = $1::uuid
              AND sc.direction  = 'active'
              AND sc.due_date  <= NOW()
              AND wt.language   = $2
            ORDER BY sc.due_date ASC
            LIMIT 1
            """,
            user_id, language,
        )
        if row:
            return dict(row)

        # Priority 2: learning word without an active SRS card yet
        row = await conn.fetchrow(
            """
            SELECT uwk.item_id, uwk.item_type, wt.word, wt.lemma
            FROM user_word_knowledge uwk
            JOIN word_table wt
              ON wt.word_id = uwk.item_id AND uwk.item_type = 'word'
            WHERE uwk.user_id   = $1::uuid
              AND uwk.status    = 'learning'
              AND wt.language   = $2
              AND NOT EXISTS (
                  SELECT 1 FROM srs_cards sc
                  WHERE sc.user_id   = $1::uuid
                    AND sc.item_id   = uwk.item_id
                    AND sc.item_type = uwk.item_type
                    AND sc.direction = 'active'
              )
            ORDER BY uwk.last_seen DESC NULLS LAST
            LIMIT 1
            """,
            user_id, language,
        )
        if row:
            return dict(row)

        # Priority 3: random word not yet tagged by this user
        row = await conn.fetchrow(
            """
            SELECT wt.word_id AS item_id, 'word'::text AS item_type,
                   wt.word, wt.lemma
            FROM word_table wt
            WHERE wt.language = $2
              AND NOT EXISTS (
                  SELECT 1 FROM user_word_knowledge uwk
                  WHERE uwk.user_id   = $1::uuid
                    AND uwk.item_id   = wt.word_id
                    AND uwk.item_type = 'word'
              )
            ORDER BY random()
            LIMIT 1
            """,
            user_id, language,
        )
        return dict(row) if row else None


async def update_progress(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    *,
    target_counted: bool,
) -> None:
    """
    Update mastery progress after a guided turn.

    target_counted=True  → increment active_level + times_used_correctly,
                           advance SRS card (SM-2 correct),
                           promote to 'known' if active_level >= MASTERY_THRESHOLD.
    target_counted=False → touch last_seen only,
                           penalise SRS card (SM-2 incorrect) if card exists.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if target_counted:
                row = await conn.fetchrow(
                    """
                    INSERT INTO user_word_knowledge
                        (user_id, item_id, item_type, status,
                         active_level, times_used_correctly, last_seen)
                    VALUES ($1::uuid, $2, $3, 'learning', 1, 1, NOW())
                    ON CONFLICT (user_id, item_id, item_type) DO UPDATE SET
                        active_level         = user_word_knowledge.active_level + 1,
                        times_used_correctly = user_word_knowledge.times_used_correctly + 1,
                        last_seen            = NOW()
                    RETURNING active_level
                    """,
                    user_id, item_id, item_type,
                )
                new_level = row["active_level"]

                await _update_active_srs(conn, user_id, item_id, item_type, correct=True)

                if new_level >= MASTERY_THRESHOLD:
                    # Reuse the shared status-promotion path (runs on pool, not conn,
                    # so outside this transaction — acceptable: active_level is committed)
                    await conn.execute(
                        """
                        INSERT INTO user_word_knowledge
                            (user_id, item_id, item_type, status, last_seen)
                        VALUES ($1::uuid, $2, $3, 'known', NOW())
                        ON CONFLICT (user_id, item_id, item_type) DO UPDATE SET
                            status    = 'known',
                            last_seen = NOW()
                        """,
                        user_id, item_id, item_type,
                    )
            else:
                # Touch last_seen; penalise SRS if card exists
                await conn.execute(
                    """
                    INSERT INTO user_word_knowledge
                        (user_id, item_id, item_type, status, last_seen)
                    VALUES ($1::uuid, $2, $3, 'unknown', NOW())
                    ON CONFLICT (user_id, item_id, item_type) DO UPDATE SET
                        last_seen = NOW()
                    """,
                    user_id, item_id, item_type,
                )
                await _update_active_srs(conn, user_id, item_id, item_type, correct=False)


async def _update_active_srs(
    conn: asyncpg.Connection,
    user_id: str,
    item_id: int,
    item_type: str,
    *,
    correct: bool,
) -> None:
    """Create or update the active-direction SRS card using SM-2 rules."""
    card = await conn.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions
        FROM srs_cards
        WHERE user_id = $1::uuid
          AND item_id = $2
          AND item_type = $3
          AND direction = 'active'
        """,
        user_id, item_id, item_type,
    )

    if card is None:
        if correct:
            await conn.execute(
                """
                INSERT INTO srs_cards
                    (user_id, item_id, item_type, direction,
                     due_date, interval_days, ease_factor, repetitions, last_review)
                VALUES ($1::uuid, $2, $3, 'active',
                        NOW() + INTERVAL '1 day', 1.0, 2.5, 1, NOW())
                ON CONFLICT DO NOTHING
                """,
                user_id, item_id, item_type,
            )
        return

    if correct:
        new_interval = card["interval_days"] * card["ease_factor"]
        new_ease     = min(card["ease_factor"] + 0.05, 3.0)
        new_reps     = card["repetitions"] + 1
    else:
        new_interval = 1.0
        new_ease     = max(card["ease_factor"] - 0.15, 1.3)
        new_reps     = 0

    await conn.execute(
        """
        UPDATE srs_cards SET
            interval_days = $1,
            ease_factor   = $2,
            repetitions   = $3,
            due_date      = NOW() + ($1::float * INTERVAL '1 day'),
            last_review   = NOW()
        WHERE user_id   = $4::uuid
          AND item_id   = $5
          AND item_type = $6
          AND direction = 'active'
        """,
        new_interval, new_ease, new_reps, user_id, item_id, item_type,
    )
