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
    return {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}


def _coerce_settings(value) -> dict:
    """
    Normalize settings coming back from Postgres into a plain dict.

    Handles:
    - None
    - dict-like objects
    - JSON strings
    - anything malformed by falling back to {}
    """
    if not value:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    try:
        return dict(value)
    except Exception:
        return {}


async def get_preferences(pool: asyncpg.Pool, user_id: str) -> dict:
    """Return the user's current preferences, with defaults applied."""
    row = await pool.fetchrow(
        "SELECT settings FROM users WHERE user_id = $1::uuid",
        user_id,
    )
    raw = _coerce_settings(row["settings"]) if row else {}
    return apply_defaults(raw)


async def update_preferences(
    pool: asyncpg.Pool,
    user_id: str,
    updates: dict,
) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            current = _coerce_settings(row["settings"]) if row else {}
            merged = {**current, **{k: v for k, v in updates.items() if k in DEFAULTS}}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(merged),
                user_id,
            )
    return apply_defaults(merged)


ChannelAction = Literal["follow", "like", "dislike", "clear"]


def apply_channel_action(
    prefs: dict,
    channel_id: str,
    channel_name: str,
    action: ChannelAction,
) -> dict:
    followed = set(prefs.get("followed_channels") or [])
    liked = set(prefs.get("liked_channels") or [])
    disliked = set(prefs.get("disliked_channels") or [])
    names = dict(prefs.get("channel_names") or {})

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
    else:
        followed.discard(channel_id)
        liked.discard(channel_id)
        disliked.discard(channel_id)

    if action != "clear":
        names[channel_id] = channel_name
    elif (
        channel_id in names
        and channel_id not in followed
        and channel_id not in liked
        and channel_id not in disliked
    ):
        names.pop(channel_id, None)

    return {
        **prefs,
        "followed_channels": sorted(followed),
        "liked_channels": sorted(liked),
        "disliked_channels": sorted(disliked),
        "channel_names": names,
    }


GenreAction = Literal["like", "dislike", "clear"]


def apply_genre_action(prefs: dict, genre: str, action: GenreAction) -> dict:
    liked = set(prefs.get("liked_genres") or [])
    disliked = set(prefs.get("disliked_genres") or [])

    if action == "like":
        liked.add(genre)
        disliked.discard(genre)
    elif action == "dislike":
        disliked.add(genre)
        liked.discard(genre)
    else:
        liked.discard(genre)
        disliked.discard(genre)

    return {
        **prefs,
        "liked_genres": sorted(liked),
        "disliked_genres": sorted(disliked),
    }


async def channel_preference_action(
    pool: asyncpg.Pool,
    user_id: str,
    channel_id: str,
    channel_name: str,
    action: ChannelAction,
) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            current = apply_defaults(_coerce_settings(row["settings"]) if row else {})
            updated = apply_channel_action(current, channel_id, channel_name, action)
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
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            current = apply_defaults(_coerce_settings(row["settings"]) if row else {})
            updated = apply_genre_action(current, genre, action)
            to_save = {k: v for k, v in updated.items() if k in DEFAULTS}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(to_save),
                user_id,
            )
    return apply_defaults(to_save)