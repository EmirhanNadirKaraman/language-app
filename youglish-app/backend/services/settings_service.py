from __future__ import annotations

import json
from typing import Literal

import asyncpg


DEFAULTS: dict = {
    "liked_channels":         [],
    "followed_channels":      [],
    "disliked_channels":      [],
    "channel_names":          {},   # channel_id -> display name
    "passive_reps_for_known": 5,
    "active_reps_for_known":  3,
    "known_word_color":       "#388e3c",
    "learning_word_color":    "#f57c00",
    "unknown_word_color":     "#d32f2f",
    "reminders_enabled":      True,
    "dark_mode":              False,
    "auto_mark_known":        False,
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
    """Return the user's current preferences, with defaults applied.

    Category preferences (liked/disliked) are read from user_video_category
    and merged into the result alongside the JSON-stored settings.
    """
    row = await pool.fetchrow(
        "SELECT settings FROM users WHERE user_id = $1::uuid",
        user_id,
    )
    raw = _coerce_settings(row["settings"]) if row else {}
    prefs = apply_defaults(raw)

    cat_rows = await pool.fetch(
        "SELECT video_category, preference FROM user_video_category WHERE uid = $1",
        user_id,
    )
    prefs["liked_categories"]    = [r["video_category"] for r in cat_rows if r["preference"] == "liked"]
    prefs["disliked_categories"] = [r["video_category"] for r in cat_rows if r["preference"] == "disliked"]
    return prefs


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


CategoryAction = Literal["like", "dislike", "clear"]


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


async def category_preference_action(
    pool: asyncpg.Pool,
    user_id: str,
    category: str,
    action: CategoryAction,
) -> dict:
    """Like, dislike, or clear a video category preference.

    Writes to user_video_category (not the settings JSON blob).
    Returns the full preferences dict so the caller gets a consistent response.
    """
    if action == "clear":
        await pool.execute(
            "DELETE FROM user_video_category WHERE uid = $1 AND video_category = $2",
            user_id, category,
        )
    else:
        await pool.execute(
            """
            INSERT INTO user_video_category (uid, video_category, preference)
            VALUES ($1, $2, $3)
            ON CONFLICT (uid, video_category) DO UPDATE SET preference = EXCLUDED.preference
            """,
            user_id, category, action,
        )
    return await get_preferences(pool, user_id)