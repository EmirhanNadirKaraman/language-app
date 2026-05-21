
import asyncpg


LOOKUP_CANDIDATE_CAP = 10


async def lookup_word_by_text(
    pool: asyncpg.Pool,
    user_id: str,
    word: str,
    language: str,
) -> dict:
    """
    Resolve a surface form to its word_table entries for the given user.

    Returns a `WordLookupResponse`-shape dict:
      {
        status:     "not_found" | "single" | "ambiguous",
        item:       <WordLookupResult dict> | None,
        candidates: [<WordLookupResult dict>...]
      }

    W3 fix (Hole 2): the pre-W3 query ended with `LIMIT 1`, which silently
    picked an arbitrary row when the same surface form mapped to multiple
    entries (e.g. *die Bank* = bench vs. financial institution → different
    `pos`/`lemma`). Mastery progress could attach to the wrong meaning
    invisibly. We now fetch up to LOOKUP_CANDIDATE_CAP rows and return them
    all when there's more than one; the caller (interactive picker) decides.

    Sort order (deterministic):
      1. exact case-insensitive `word` match first (typed surface wins)
      2. then by `lemma` ascending
      3. then by `word_id` ascending (stability tie-breaker)
    """
    rows = await pool.fetch(
        """
        SELECT
            w.word_id,
            w.word,
            w.lemma,
            w.pos,
            uwk.status                        AS current_status,
            COALESCE(uwk.passive_level, 0)    AS passive_level,
            COALESCE(uwk.active_level,  0)    AS active_level,
            sc_p.due_date                     AS passive_due,
            sc_a.due_date                     AS active_due
        FROM word_table w
        LEFT JOIN user_word_knowledge uwk
               ON uwk.item_id   = w.word_id
              AND uwk.item_type = 'word'
              AND uwk.user_id   = $2::uuid
        LEFT JOIN srs_cards sc_p
               ON sc_p.item_id   = w.word_id
              AND sc_p.item_type = 'word'
              AND sc_p.user_id   = $2::uuid
              AND sc_p.direction = 'passive'
        LEFT JOIN srs_cards sc_a
               ON sc_a.item_id   = w.word_id
              AND sc_a.item_type = 'word'
              AND sc_a.user_id   = $2::uuid
              AND sc_a.direction = 'active'
        WHERE w.word ILIKE $1 AND w.language = $3
        ORDER BY
            CASE WHEN LOWER(w.word) = LOWER($1) THEN 0 ELSE 1 END,
            w.lemma ASC,
            w.word_id ASC
        LIMIT $4
        """,
        word,
        user_id,
        language,
        LOOKUP_CANDIDATE_CAP,
    )

    candidates = [
        {
            "word_id":        r["word_id"],
            "word":           r["word"],
            "lemma":          r["lemma"],
            "pos":            r["pos"] or "",
            "current_status": r["current_status"],
            "passive_level":  r["passive_level"],
            "active_level":   r["active_level"],
            "passive_due":    r["passive_due"],
            "active_due":     r["active_due"],
        }
        for r in rows
    ]

    if not candidates:
        return {"status": "not_found", "item": None, "candidates": []}
    if len(candidates) == 1:
        return {"status": "single", "item": candidates[0], "candidates": candidates}
    return {"status": "ambiguous", "item": None, "candidates": candidates}


async def _lookup_first_match(
    pool: asyncpg.Pool,
    user_id: str,
    word: str,
    language: str,
) -> dict | None:
    """
    Compatibility helper for non-interactive callers (e.g. `learn_word_anyway`'s
    post-create read) that just want the canonical entry. Picks `item` when
    available, falls back to the first candidate, else None. Internal — the
    public API surfaces the full response so the picker can disambiguate.
    """
    resp = await lookup_word_by_text(pool, user_id, word, language)
    if resp["item"] is not None:
        return resp["item"]
    if resp["candidates"]:
        return resp["candidates"][0]
    return None


async def learn_word_anyway(
    pool: asyncpg.Pool,
    user_id: str,
    text: str,
    language: str,
) -> dict:
    """
    Create (or reuse) a word_table row for `text` and mark it as 'learning'
    for the user atomically. Hole 1 / W2 fix: lets a user adopt a word that
    the scraper has never indexed, so the click-→-mark-→-review loop works
    end-to-end without waiting on a pipeline run.

    Behaviour:
      - text is trimmed; raises ValueError on empty input. Callers validate
        length again at the route layer (Pydantic).
      - word_table is sparsely populated for unscraped words: pos='X'
        (spaCy's universal "other" tag), tag='', lemma=text. A future
        enrichment pass (e.g. when the scraper sees the word in context)
        may patch the row in place — we don't fabricate POS/lemma now.
      - The unique key on (word, language, pos) means re-running with the
        same input no-ops at the INSERT level. We still re-fetch the
        existing row's word_id and run apply_progression so the user
        always ends up in the 'learning' state regardless of prior status.
      - Progression: 'status_marked_learning' with status_override='learning'
        creates both passive AND active SRS cards (#0b) without inflating
        active_level / times_used_correctly (rule is exposure-only).

    Returns the lookup-shape dict (same keys as `lookup_word_by_text`) so
    the frontend can re-render the picker without a second round-trip.
    """
    from . import progression_service  # local import — avoids cycle at module load

    text = text.strip()
    if not text:
        raise ValueError("text must be non-empty")

    async with pool.acquire() as conn:
        async with conn.transaction():
            # INSERT returns the new row's word_id; on conflict we fall back
            # to a SELECT to find the existing one. We don't UPDATE existing
            # rows — if the scraper later enriches POS/lemma it should win
            # over our 'X' placeholder.
            row = await conn.fetchrow(
                """
                INSERT INTO word_table (word, language, pos, tag, lemma)
                VALUES ($1, $2, 'X', '', $1)
                ON CONFLICT (word, language, pos) DO NOTHING
                RETURNING word_id
                """,
                text, language,
            )
            if row is None:
                # Existing row — fetch its id. ILIKE matches the lookup
                # behaviour so capitalisation differences don't fork rows.
                row = await conn.fetchrow(
                    """
                    SELECT word_id FROM word_table
                     WHERE word ILIKE $1 AND language = $2
                     ORDER BY word_id ASC
                     LIMIT 1
                    """,
                    text, language,
                )
                if row is None:
                    # Should be unreachable — the INSERT either succeeded or
                    # the row exists for ILIKE-equivalent surface. Defensive.
                    raise RuntimeError("learn_word_anyway: row vanished after conflict")
            word_id = row["word_id"]

        # progression_service.apply_progression opens its own transaction
        # inside the same connection. Keeping the conn allocation visible
        # here ensures the INSERT + progression share a session even though
        # they're separate tx — equivalent to the existing words.py route.
    await progression_service.apply_progression(
        pool, user_id, word_id, "word",
        "status_marked_learning",
        status_override="learning",
    )

    # Read back the canonical row for the response. We just inserted with
    # pos='X' so we use the internal first-match helper rather than the
    # full discriminated response — the caller (POST /learn-anyway) expects
    # a single WordLookupResult shape.
    result = await _lookup_first_match(pool, user_id, text, language)
    if result is None:
        raise RuntimeError("learn_word_anyway: lookup failed after insert")
    return result


async def get_user_knowledge(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    """Return all word/phrase knowledge rows for a user, newest first."""
    rows = await pool.fetch(
        """
        SELECT item_id, item_type, status, passive_level, active_level, notes, last_seen
        FROM user_word_knowledge
        WHERE user_id = $1::uuid
        ORDER BY last_seen DESC NULLS LAST
        """,
        user_id,
    )
    return [dict(r) for r in rows]


