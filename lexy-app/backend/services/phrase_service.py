"""
First-class phrase operations.

phrase_table stores canonical phrase blueprints (e.g. "freuen sich über etw.")
from the German verb dictionary used by phrase_finder.py.  Each blueprint gets
a stable phrase_id that flows through user_word_knowledge, srs_cards, and
word_usage_events exactly as word_ids do, with item_type='phrase'.

Seeding
-------
Call seed_from_blueprint_map() at startup (main.py lifespan) using the dict
already loaded by matcher_service.  ON CONFLICT DO NOTHING makes it idempotent.

Progress
--------
All progress tracking reuses the existing passive/active progression model:
  PUT /api/v1/words/phrase/{phrase_id}/status  → already wired in words.py
  progression_service.apply_progression(item_type='phrase') → already generic
  srs_cards (item_type='phrase')               → already generic

Phrase recommendations start empty until the user marks at least one phrase
as 'learning'.  Once signals exist, get_prioritized_items(item_type='phrase')
feeds into recommend_items() → enrich_phrases() exactly like words do.
"""
from __future__ import annotations

import asyncpg


# ---------------------------------------------------------------------------
# Phrase type inference (pure, no DB)
# ---------------------------------------------------------------------------

_PHRASE_TYPE_RULES: list[tuple[str, str]] = [
    ("sich",  "reflexive_verb"),
    ("jdm.",  "verb_pattern"),
    ("jdn.",  "verb_pattern"),
    ("etw.",  "verb_pattern"),
]


def _infer_phrase_type(blueprint: str) -> str:
    bl = blueprint.lower()
    for marker, ptype in _PHRASE_TYPE_RULES:
        if marker in bl:
            return ptype
    return "collocation"


def _surface_from_blueprint(blueprint: str) -> str:
    """Strip jdm./jdn./etw. placeholders for a cleaner display label."""
    placeholders = {"jdm.", "jdn.", "etw."}
    cleaned = [p for p in blueprint.split() if p not in placeholders]
    return " ".join(cleaned).strip() or blueprint


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def lookup_phrase_by_canonical(
    pool: asyncpg.Pool,
    canonical: str,
    language: str = "de",
) -> dict | None:
    """Return phrase metadata for a canonical blueprint, or None if not seeded."""
    row = await pool.fetchrow(
        """
        SELECT phrase_id, canonical, surface_form, phrase_type, language
        FROM phrase_table
        WHERE canonical = $1 AND language = $2
        """,
        canonical, language,
    )
    return dict(row) if row else None


async def get_phrases_for_language(
    pool: asyncpg.Pool,
    language: str,
    limit: int = 500,
) -> list[dict]:
    """Return all seeded phrases for a language, ordered by phrase_id."""
    rows = await pool.fetch(
        """
        SELECT phrase_id, canonical, surface_form, phrase_type, language
        FROM phrase_table
        WHERE language = $1
        ORDER BY phrase_id
        LIMIT $2
        """,
        language, limit,
    )
    return [dict(r) for r in rows]


async def enrich_phrases(
    pool: asyncpg.Pool,
    user_id: str,
    phrase_ids: list[int],
    language: str,
) -> dict[int, dict]:
    """
    Fetch display metadata and user progress for a list of phrase_ids.

    Mirrors recommendation_service.enrich_items() but for phrase_table.
    Returns phrase_id → enrichment dict.  Phrase IDs absent from phrase_table
    for the given language are silently omitted.
    """
    if not phrase_ids:
        return {}
    rows = await pool.fetch(
        """
        SELECT
            pt.phrase_id,
            pt.canonical,
            pt.surface_form,
            pt.phrase_type,
            uwk.status          AS current_status,
            uwk.passive_level,
            uwk.active_level,
            sc.due_date
        FROM phrase_table pt
        LEFT JOIN user_word_knowledge uwk
               ON uwk.item_id   = pt.phrase_id
              AND uwk.item_type = 'phrase'
              AND uwk.user_id   = $1::uuid
        LEFT JOIN srs_cards sc
               ON sc.item_id   = pt.phrase_id
              AND sc.item_type = 'phrase'
              AND sc.user_id   = $1::uuid
              AND sc.direction = 'passive'
        WHERE pt.phrase_id = ANY($2::int[])
          AND pt.language  = $3
        """,
        user_id, phrase_ids, language,
    )
    return {
        r["phrase_id"]: {
            "display_text":   r["surface_form"],
            "secondary_text": r["phrase_type"],
            "current_status": r["current_status"],
            "passive_level":  r["passive_level"] or 0,
            "active_level":   r["active_level"] or 0,
            "due_date":       r["due_date"],
        }
        for r in rows
    }


async def seed_from_blueprint_map(
    pool: asyncpg.Pool,
    blueprint_map: dict[str, str],
    language: str = "de",
) -> int:
    """
    Populate phrase_table from a verb blueprint dict (the one loaded by phrase_finder).

    Only seeds blueprints that contain a space (genuine multi-word phrases).
    Single-word lemma entries — e.g. "gehen\tgehen" — are skipped.
    ON CONFLICT DO NOTHING makes this safe to call on every startup.

    Returns the count of newly inserted rows.
    """
    seen: set[str] = set()
    to_insert: list[tuple[str, str, str]] = []

    for _lemma, blueprint in blueprint_map.items():
        if " " not in blueprint:
            continue  # single-word entry — not a learnable phrase
        if blueprint in seen:
            continue
        seen.add(blueprint)
        to_insert.append((
            blueprint,
            _surface_from_blueprint(blueprint),
            _infer_phrase_type(blueprint),
        ))

    if not to_insert:
        return 0

    inserted = 0
    async with pool.acquire() as conn:
        for canonical, surface_form, phrase_type in to_insert:
            result = await conn.execute(
                """
                INSERT INTO phrase_table (canonical, surface_form, phrase_type, language)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (canonical, language) DO NOTHING
                """,
                canonical, surface_form, phrase_type, language,
            )
            # asyncpg returns e.g. "INSERT 0 1" — count the newly inserted rows
            if result.endswith(" 1"):
                inserted += 1

    return inserted
