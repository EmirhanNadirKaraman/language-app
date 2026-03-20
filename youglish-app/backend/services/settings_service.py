"""
User settings / preferences — read and write users.settings JSONB.

Architecture
------------
Pure:
  apply_defaults(raw: dict) -> dict
    Merges raw settings over DEFAULTS; unknown keys are silently dropped.
    DEFAULTS is the single source of truth for all valid keys and their values.

DB:
  get_preferences(pool, user_id) -> dict
  update_preferences(pool, user_id, updates: dict) -> dict
    Merges only non-None updates. Uses SELECT … FOR UPDATE to prevent
    concurrent partial overwrites. Returns the full applied result.

Extending
---------
To add a new preference: add it to DEFAULTS. No migration needed — the
column already exists as JSONB DEFAULT '{}'.

Future integration points (deferred, no code changes needed here yet):
  - recommendation_service: call get_preferences, pass liked_genres /
    liked_channels as weights to score_video / score_sentence.
  - progression_service: read passive/active_reps_for_known and pass to
    _maybe_promote instead of the module-level PASSIVE/ACTIVE thresholds.
  - SubtitleDisplay / TranscriptPanel: colors flow via usePreferences hook
    in React — already wired in the frontend.
"""
from __future__ import annotations

import json

import asyncpg


DEFAULTS: dict = {
    "liked_genres":           [],
    "liked_channels":         [],
    "passive_reps_for_known": 5,
    "active_reps_for_known":  3,
    "known_word_color":       "#388e3c",
    "learning_word_color":    "#f57c00",
    "unknown_word_color":     "#d32f2f",
}


def apply_defaults(raw: dict) -> dict:
    """
    Pure function. Merge raw settings over DEFAULTS.

    - Known keys in raw override their defaults.
    - Unknown keys in raw are silently dropped (safe across schema changes —
      old keys left over from deleted features can't cause KeyErrors).
    - All keys in DEFAULTS are always present in the result.
    """
    return {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}


async def get_preferences(pool: asyncpg.Pool, user_id: str) -> dict:
    """Return the user's current preferences, with defaults applied."""
    row = await pool.fetchrow(
        "SELECT settings FROM users WHERE user_id = $1::uuid",
        user_id,
    )
    raw = dict(row["settings"]) if row and row["settings"] else {}
    return apply_defaults(raw)


async def update_preferences(
    pool: asyncpg.Pool,
    user_id: str,
    updates: dict,
) -> dict:
    """
    Merge updates into the user's stored settings and persist.

    Only keys that exist in DEFAULTS are written; all other keys are ignored.
    Uses SELECT … FOR UPDATE to prevent lost updates under concurrent requests.
    Returns the full merged result with defaults applied.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            current = dict(row["settings"]) if row and row["settings"] else {}
            merged = {**current, **{k: v for k, v in updates.items() if k in DEFAULTS}}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(merged),
                user_id,
            )
    return apply_defaults(merged)
