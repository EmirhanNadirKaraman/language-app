from __future__ import annotations

import json
from typing import Literal

import asyncpg


# Scalar / JSONB preferences live in users.settings. Channel preferences
# (followed/liked/disliked) moved to user_channel_preference in migration 027
# (T1.4, 2026-05-20) but are still surfaced in the same dict shape so the API
# response and downstream consumers (recommendation_service, etc.) don't have
# to change. channel_names — the display-name cache — STAYS in JSONB by
# design; it's not a preference, just a lookup table.
DEFAULTS: dict = {
    "channel_names":          {},   # channel_id -> display name (JSONB)
    "passive_reps_for_known": 5,
    "active_reps_for_known":  3,
    "known_word_color":       "#388e3c",
    "learning_word_color":    "#f57c00",
    "unknown_word_color":     "#d32f2f",
    "reminders_enabled":      True,
    # theme_mode is the source of truth (T1.3, 2026-05-20); dark_mode is kept
    # in sync for legacy clients that haven't migrated yet. New users default
    # to "system" so iOS / OS dark mode wins out of the box; existing users
    # who explicitly chose dark/light have that choice preserved via the
    # compat derivation in get_preferences/_normalize_theme_updates.
    "theme_mode":             "system",
    "dark_mode":              False,
    "auto_mark_known":        False,
}

# Channel-preference fields: surfaced in the returned prefs dict (and accepted
# by /settings/preferences PUT) but stored relationally rather than in JSONB.
CHANNEL_PREF_FIELDS = ("followed_channels", "liked_channels", "disliked_channels")
_KIND_BY_FIELD = {
    "followed_channels": "followed",
    "liked_channels":    "liked",
    "disliked_channels": "disliked",
}

VALID_THEME_MODES = {"system", "light", "dark"}


def _normalize_theme_compat(raw: dict) -> dict:
    """
    Bridge legacy `dark_mode`-only saves and the new `theme_mode` field.

    Rules:
      - If `theme_mode` is already set, it wins. dark_mode is mirrored from it.
      - Else if `dark_mode` is set, derive theme_mode:
            dark_mode=True  -> "dark"
            dark_mode=False -> "light"
        (explicit user choice is preserved as "light"/"dark", NOT silently
        upgraded to "system" — see T1.3 spec)
      - Else neither set: theme_mode defaults to "system" via DEFAULTS.

    Operates on a copy. Returns the merged shape so apply_defaults can layer
    its DEFAULTS on top without overwriting derived values.
    """
    if not raw:
        return raw
    out = dict(raw)
    has_theme = "theme_mode" in out and out["theme_mode"] in VALID_THEME_MODES
    has_dark = "dark_mode" in out and isinstance(out["dark_mode"], bool)
    if has_theme:
        # theme_mode wins; mirror dark_mode for any legacy reader.
        out["dark_mode"] = out["theme_mode"] == "dark"
    elif has_dark:
        # Legacy save — derive theme_mode from the explicit boolean.
        out["theme_mode"] = "dark" if out["dark_mode"] else "light"
    return out


def apply_defaults(raw: dict) -> dict:
    raw = _normalize_theme_compat(raw)
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
    except (TypeError, ValueError):
        # dict(value) raises TypeError for non-iterable inputs and ValueError
        # for malformed key/value pairs. Anything else is a real bug — let it
        # propagate so we hear about it.
        return {}


async def _fetch_channel_prefs(pool_or_conn, user_id: str) -> dict[str, list[str]]:
    """
    Return {followed_channels, liked_channels, disliked_channels} as sorted
    lists of youtube_channel_ids, read from `user_channel_preference`.

    Accepts either a Pool or a Connection so callers inside a transaction
    can pass `conn` and stay in the same tx.
    """
    rows = await pool_or_conn.fetch(
        """
        SELECT youtube_channel_id, preference_kind
          FROM user_channel_preference
         WHERE user_id = $1::uuid
         ORDER BY youtube_channel_id
        """,
        user_id,
    )
    followed, liked, disliked = [], [], []
    for r in rows:
        kind = r["preference_kind"]
        cid = r["youtube_channel_id"]
        if kind == "followed":
            followed.append(cid)
        elif kind == "liked":
            liked.append(cid)
        elif kind == "disliked":
            disliked.append(cid)
    return {
        "followed_channels": followed,
        "liked_channels":    liked,
        "disliked_channels": disliked,
    }


async def get_preferences(pool: asyncpg.Pool, user_id: str) -> dict:
    """Return the user's current preferences, with defaults applied.

    Channel preferences come from `user_channel_preference` (T1.4).
    Category preferences come from `user_video_category` (since #5d).
    Scalars + display-name caches come from `users.settings` JSONB.
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
    # Map to frontend field names for compatibility
    prefs["liked_genres"]    = prefs["liked_categories"]
    prefs["disliked_genres"] = prefs["disliked_categories"]

    # Channel prefs from the relational table (T1.4 / migration 027).
    prefs.update(await _fetch_channel_prefs(pool, user_id))
    return prefs


async def _replace_channel_prefs(conn, user_id: str, field: str, channel_ids: list[str]) -> None:
    """
    Replace all rows of a given preference kind for the user with the given
    list. Mirrors the previous JSONB shape semantics (PUT is a full replace,
    not a merge) used by the `/settings/preferences` PUT endpoint.

    Conflict policy here: replace-all on the given kind only. Cross-kind
    conflicts (liked vs disliked) are NOT enforced here — that's the
    `channel_preference_action` path. The PUT endpoint accepts the client's
    arrays as authoritative.
    """
    kind = _KIND_BY_FIELD[field]
    await conn.execute(
        """
        DELETE FROM user_channel_preference
         WHERE user_id = $1::uuid AND preference_kind = $2
        """,
        user_id, kind,
    )
    # Dedup the input — defensive against legacy clients sending duplicates.
    for cid in sorted(set(channel_ids)):
        await conn.execute(
            """
            INSERT INTO user_channel_preference (user_id, youtube_channel_id, preference_kind)
            VALUES ($1::uuid, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            user_id, cid, kind,
        )


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
            # Normalise theme fields BEFORE the merge so a legacy client that
            # sends only dark_mode still updates theme_mode (and vice versa).
            normalised_updates = _normalize_theme_compat(updates)

            # JSONB scalars: only keys actually in DEFAULTS persist.
            merged = {**current, **{k: v for k, v in normalised_updates.items() if k in DEFAULTS}}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(merged),
                user_id,
            )

            # Channel prefs: route to the relational table (T1.4).
            for field in CHANNEL_PREF_FIELDS:
                if field in normalised_updates and normalised_updates[field] is not None:
                    await _replace_channel_prefs(conn, user_id, field, normalised_updates[field])

            # Handle category preferences separately (stored in user_video_category table)
            if "liked_categories" in updates or "disliked_categories" in updates:
                # Delete all existing preferences for this user
                await conn.execute(
                    "DELETE FROM user_video_category WHERE uid = $1",
                    user_id,
                )
                # Re-insert the new preferences
                liked = updates.get("liked_categories") or []
                disliked = updates.get("disliked_categories") or []
                for category in liked:
                    await conn.execute(
                        """
                        INSERT INTO user_video_category (uid, video_category, preference)
                        VALUES ($1, $2, 'liked')
                        """,
                        user_id, category,
                    )
                for category in disliked:
                    await conn.execute(
                        """
                        INSERT INTO user_video_category (uid, video_category, preference)
                        VALUES ($1, $2, 'disliked')
                        """,
                        user_id, category,
                    )

    # Apply defaults and then fetch category preferences from DB (same as get_preferences)
    prefs = apply_defaults(merged)
    cat_rows = await pool.fetch(
        "SELECT video_category, preference FROM user_video_category WHERE uid = $1",
        user_id,
    )
    prefs["liked_categories"]    = [r["video_category"] for r in cat_rows if r["preference"] == "liked"]
    prefs["disliked_categories"] = [r["video_category"] for r in cat_rows if r["preference"] == "disliked"]
    # Map to frontend field names for compatibility
    prefs["liked_genres"]    = prefs["liked_categories"]
    prefs["disliked_genres"] = prefs["disliked_categories"]
    # Channel prefs from the relational table (T1.4 / migration 027).
    prefs.update(await _fetch_channel_prefs(pool, user_id))
    return prefs


ChannelAction = Literal["follow", "like", "dislike", "clear"]


def apply_channel_action(
    prefs: dict,
    channel_id: str,
    channel_name: str,
    action: ChannelAction,
) -> dict:
    """
    Pure transform: returns the prefs dict updated for the given channel
    action. Since T1.4 (2026-05-20), channel preferences live in
    `user_channel_preference` — this helper still operates on a dict shape
    so unit tests and call sites that pass an in-memory dict (no DB) keep
    working. The `channel_preference_action` async wrapper bridges this
    transform to the relational store.

    Conflict policy (preserved from pre-T1.4):
      - follow:  add to followed; remove from disliked
      - like:    add to liked;    remove from disliked
      - dislike: add to disliked; remove from followed AND liked
      - clear:   remove from all three
      (followed coexists with liked; only liked vs disliked is mutually
      exclusive)

    channel_names — display-name cache — set on any non-clear; popped on
    clear ONLY when the channel has no remaining presence.
    """
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
    """
    Apply a follow/like/dislike/clear action atomically.

    Since T1.4 (migration 027): channel-presence rows live in
    `user_channel_preference`; only `channel_names` (display-name cache)
    is updated in the JSONB blob.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Compute the new in-memory shape using existing channel rows.
            row = await conn.fetchrow(
                "SELECT settings FROM users WHERE user_id = $1::uuid FOR UPDATE",
                user_id,
            )
            settings_raw = _coerce_settings(row["settings"]) if row else {}
            current_channel_state = await _fetch_channel_prefs(conn, user_id)
            current = {
                **apply_defaults(settings_raw),
                **current_channel_state,
            }
            updated = apply_channel_action(current, channel_id, channel_name, action)

            # 2. Persist channel_names (JSONB) only — channel-presence keys
            #    are filtered out via the DEFAULTS allowlist.
            settings_to_save = {k: v for k, v in updated.items() if k in DEFAULTS}
            await conn.execute(
                "UPDATE users SET settings = $1::jsonb WHERE user_id = $2::uuid",
                json.dumps(settings_to_save),
                user_id,
            )

            # 3. Persist channel-presence rows: replace each kind for this
            #    channel based on the action's effect on (followed, liked,
            #    disliked) sets — the `updated` dict already encodes the
            #    target state, so we delete the channel's rows of each kind
            #    and re-insert only the kinds the channel now belongs to.
            await conn.execute(
                """
                DELETE FROM user_channel_preference
                 WHERE user_id = $1::uuid AND youtube_channel_id = $2
                """,
                user_id, channel_id,
            )
            target_kinds: list[str] = []
            if channel_id in set(updated["followed_channels"]):
                target_kinds.append("followed")
            if channel_id in set(updated["liked_channels"]):
                target_kinds.append("liked")
            if channel_id in set(updated["disliked_channels"]):
                target_kinds.append("disliked")
            for kind in target_kinds:
                await conn.execute(
                    """
                    INSERT INTO user_channel_preference (user_id, youtube_channel_id, preference_kind)
                    VALUES ($1::uuid, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    user_id, channel_id, kind,
                )

    # Return the full prefs dict with refreshed channel state so the caller
    # (and the HTTP response) sees the post-action shape in one structure.
    final = apply_defaults(settings_to_save)
    final.update(await _fetch_channel_prefs(pool, user_id))
    return final


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