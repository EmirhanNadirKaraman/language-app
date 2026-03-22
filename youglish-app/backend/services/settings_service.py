"""
User settings / preferences — read and write users.settings JSONB.

Architecture
------------
Pure:
  apply_defaults(raw: dict) -> dict
    Merges raw settings over DEFAULTS; unknown keys are silently dropped.
    DEFAULTS is the single source of truth for all valid keys and their values.

  apply_channel_action(prefs, channel_id, channel_name, action) -> dict
  apply_genre_action(prefs, genre, action) -> dict
    Pure conflict-resolving state machines for preference actions.

DB:
  get_preferences(pool, user_id) -> dict
  update_preferences(pool, user_id, updates: dict) -> dict
    Merges only non-None updates. Uses SELECT … FOR UPDATE to prevent
    concurrent partial overwrites. Returns the full applied result.

  channel_preference_action(pool, user_id, channel_id, channel_name, action) -> dict
  genre_preference_action(pool, user_id, genre, action) -> dict
    Atomic read-modify-write using SELECT … FOR UPDATE.

Extending
---------
To add a new preference: add it to DEFAULTS. No migration needed — the
column already exists as JSONB DEFAULT '{}'.
"""
from __future__ import annotations

import json
from typing import Literal

import asyncpg


DEFAULTS: dict = {
    "liked_genres":           [],
    "liked_channels":         [],
    "disliked_genres":        [],
    "followed_channels":      [],
    "disliked_channels":      [],
    "channel_names":          {},   # channel_id -> display name
    "passive_reps_for_known": 5,
    "active_reps_for_known":  3,
    "known_word_color":       "#388e3c",
    "learning_word_color":    "#f57c00",
    "unknown_word_color":     "#d32f2f",
    "reminders_enabled":      True,
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


# ---------------------------------------------------------------------------
# Channel preference — pure state machine
# ---------------------------------------------------------------------------

ChannelAction = Literal["follow", "like", "dislike", "clear"]


def apply_channel_action(
    prefs: dict,
    channel_id: str,
    channel_name: str,
    action: ChannelAction,
) -> dict:
    """
    Pure function. Return new prefs dict after applying a channel preference
    action with full conflict resolution:

      follow  → add to followed; remove from disliked
      like    → add to liked; remove from disliked
      dislike → add to disliked; remove from followed AND liked
      clear   → remove from all three lists

    Clicking the active action again (toggle) has the same effect as "clear"
    for that action — the caller should pass "clear" in that case.

    channel_names dict is always updated with the latest display name.
    """
    followed  = set(prefs.get("followed_channels") or [])
    liked     = set(prefs.get("liked_channels") or [])
    disliked  = set(prefs.get("disliked_channels") or [])
    names     = dict(prefs.get("channel_names") or {})

    if action == "follow":
        followed.add(channel_id)
        disliked.discard(channel_id)
    elif action == "like":
        liked.add(channel_id)
        disliked.discard(channel_id)
    elif action == "dislike":
        disliked.add(channel_id)
        followed.discard(channel_id)
        liked.discard(channel_id)
    else:  # "clear"
        followed.discard(channel_id)
        liked.discard(channel_id)
        disliked.discard(channel_id)

    if action != "clear":
        names[channel_id] = channel_name
    elif channel_id in names and channel_id not in followed and channel_id not in liked and channel_id not in disliked:
        names.pop(channel_id, None)

    return {
        **prefs,
        "followed_channels": sorted(followed),
        "liked_channels":    sorted(liked),
        "disliked_channels": sorted(disliked),
        "channel_names":     names,
    }


# ---------------------------------------------------------------------------
# Genre preference — pure state machine
# ---------------------------------------------------------------------------

GenreAction = Literal["like", "dislike", "clear"]


def apply_genre_action(prefs: dict, genre: str, action: GenreAction) -> dict:
    """
    Pure function. Return new prefs dict after applying a genre preference
    action with full conflict resolution:

      like    → add to liked; remove from disliked
      dislike → add to disliked; remove from liked
      clear   → remove from both
    """
    liked    = set(prefs.get("liked_genres") or [])
    disliked = set(prefs.get("disliked_genres") or [])

    if action == "like":
        liked.add(genre)
        disliked.discard(genre)
    elif action == "dislike":
        disliked.add(genre)
        liked.discard(genre)
    else:  # "clear"
        liked.discard(genre)
        disliked.discard(genre)

    return {**prefs, "liked_genres": sorted(liked), "disliked_genres": sorted(disliked)}


# ---------------------------------------------------------------------------
# Atomic DB wrappers
# ---------------------------------------------------------------------------

async def channel_preference_action(
    pool: asyncpg.Pool,
    user_id: str,
    channel_id: str,
    channel_name: str,
    action: ChannelAction,
) -> dict:
    """Atomic read-modify-write for a channel preference action."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            current = apply_defaults(dict(row["settings"]) if row and row["settings"] else {})
            updated = apply_channel_action(current, channel_id, channel_name, action)
            # Only persist DEFAULTS-known keys
            to_save = {k: v for k, v in updated.items() if k in DEFAULTS}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(to_save),
                user_id,
            )
    return apply_defaults(to_save)


async def genre_preference_action(
    pool: asyncpg.Pool,
    user_id: str,
    genre: str,
    action: GenreAction,
) -> dict:
    """Atomic read-modify-write for a genre preference action."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            current = apply_defaults(dict(row["settings"]) if row and row["settings"] else {})
            updated = apply_genre_action(current, genre, action)
            to_save = {k: v for k, v in updated.items() if k in DEFAULTS}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(to_save),
                user_id,
            )
    return apply_defaults(to_save)
