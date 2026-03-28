"""
Settings / preferences tests.

Unit tests (no DB) — test pure functions:
  apply_defaults:
    - empty raw → all defaults present
    - known key overrides default
    - unknown key in raw is silently dropped
    - partial override keeps other defaults
    - DEFAULTS dict is not mutated

Integration tests (real DB):
  - get_preferences for a new user returns defaults
  - update_preferences single field changes only that field
  - update_preferences multiple fields changes all of them
  - update_preferences unknown key is silently ignored
  - get then update then get: second get reflects the change

HTTP tests (FastAPI client):
  - GET /api/v1/settings/preferences returns 200 with all 7 keys
  - GET requires auth → 403
  - PUT returns 200 with all 7 keys
  - PUT requires auth → 403
  - PUT invalid hex color → 422
  - PUT reps below minimum → 422
  - PUT reps above maximum → 422
  - PUT empty body changes nothing
  - PUT only changes the specified field
"""
import uuid


from backend.services.settings_service import DEFAULTS, apply_defaults, get_preferences, update_preferences


# ---------------------------------------------------------------------------
# Unit tests — pure function, no DB
# ---------------------------------------------------------------------------

class TestApplyDefaults:
    def test_empty_raw_returns_all_defaults(self):
        result = apply_defaults({})
        assert result == DEFAULTS

    def test_known_key_overrides_default(self):
        result = apply_defaults({"known_word_color": "#000000"})
        assert result["known_word_color"] == "#000000"

    def test_other_defaults_still_present_after_override(self):
        result = apply_defaults({"known_word_color": "#000000"})
        for key in DEFAULTS:
            assert key in result

    def test_unknown_key_is_dropped(self):
        result = apply_defaults({"nonexistent_key": "some_value"})
        assert "nonexistent_key" not in result

    def test_partial_override_keeps_other_defaults(self):
        result = apply_defaults({"passive_reps_for_known": 7})
        assert result["passive_reps_for_known"] == 7
        assert result["active_reps_for_known"] == DEFAULTS["active_reps_for_known"]

    def test_defaults_dict_not_mutated(self):
        original_defaults = dict(DEFAULTS)
        apply_defaults({"liked_channels": ["ch1"]})
        assert DEFAULTS == original_defaults

    def test_all_keys_overridden(self):
        overrides = {
            "liked_channels":         ["channel1"],
            "followed_channels":      ["channel2"],
            "disliked_channels":      ["channel3"],
            "channel_names":          {"channel1": "Sports Channel"},
            "passive_reps_for_known": 10,
            "active_reps_for_known":  8,
            "known_word_color":       "#111111",
            "learning_word_color":    "#222222",
            "unknown_word_color":     "#333333",
            "reminders_enabled":      False,
        }
        result = apply_defaults(overrides)
        # apply_defaults returns all default keys with provided overrides applied
        assert set(result.keys()) == set(DEFAULTS.keys())
        for key, value in overrides.items():
            assert result[key] == value


# ---------------------------------------------------------------------------
# Integration tests — real DB
# ---------------------------------------------------------------------------

async def _create_user(pool) -> str:
    """Insert a fresh test user, return user_id string."""
    row = await pool.fetchrow(
        "INSERT INTO users (email, password_hash) VALUES ($1, 'x') RETURNING user_id",
        f"test+{uuid.uuid4().hex[:12]}@example.com",
    )
    return str(row["user_id"])


async def test_get_preferences_new_user_returns_defaults(db_pool):
    user_id = await _create_user(db_pool)
    result = await get_preferences(db_pool, user_id)
    assert result == DEFAULTS


async def test_update_preferences_single_field(db_pool):
    user_id = await _create_user(db_pool)
    result = await update_preferences(db_pool, user_id, {"known_word_color": "#1a237e"})
    assert result["known_word_color"] == "#1a237e"
    # All other fields unchanged
    assert result["learning_word_color"] == DEFAULTS["learning_word_color"]
    assert result["passive_reps_for_known"] == DEFAULTS["passive_reps_for_known"]


async def test_update_preferences_multiple_fields(db_pool):
    user_id = await _create_user(db_pool)
    result = await update_preferences(db_pool, user_id, {
        "liked_channels": ["channel1"],
        "passive_reps_for_known": 7,
    })
    assert result["liked_channels"] == ["channel1"]
    assert result["passive_reps_for_known"] == 7
    assert result["active_reps_for_known"] == DEFAULTS["active_reps_for_known"]


async def test_update_preferences_unknown_key_ignored(db_pool):
    user_id = await _create_user(db_pool)
    result = await update_preferences(db_pool, user_id, {
        "nonexistent_key": "should_be_dropped",
        "known_word_color": "#abcdef",
    })
    assert "nonexistent_key" not in result
    assert result["known_word_color"] == "#abcdef"


async def test_update_preferences_roundtrip(db_pool):
    user_id = await _create_user(db_pool)

    await update_preferences(db_pool, user_id, {"liked_channels": ["chan1", "chan2"]})
    fetched = await get_preferences(db_pool, user_id)

    assert fetched["liked_channels"] == ["chan1", "chan2"]


async def test_update_preserves_previous_updates(db_pool):
    user_id = await _create_user(db_pool)

    await update_preferences(db_pool, user_id, {"known_word_color": "#111111"})
    await update_preferences(db_pool, user_id, {"learning_word_color": "#222222"})

    fetched = await get_preferences(db_pool, user_id)
    assert fetched["known_word_color"] == "#111111"
    assert fetched["learning_word_color"] == "#222222"


# ---------------------------------------------------------------------------
# HTTP tests — FastAPI client
# ---------------------------------------------------------------------------

async def _auth_token(client) -> str:
    email = f"test+{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["access_token"]


ALL_PREFERENCE_KEYS = {
    "liked_categories", "disliked_categories",
    "liked_channels", "followed_channels", "disliked_channels", "channel_names",
    "passive_reps_for_known", "active_reps_for_known",
    "known_word_color", "learning_word_color", "unknown_word_color",
    "reminders_enabled",
}


async def test_get_returns_200_with_all_keys(client):
    token = await _auth_token(client)
    resp = await client.get(
        "/api/v1/settings/preferences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ALL_PREFERENCE_KEYS == set(body.keys())


async def test_get_requires_auth(client):
    resp = await client.get("/api/v1/settings/preferences")
    assert resp.status_code == 403


async def test_put_returns_200_with_all_keys(client):
    token = await _auth_token(client)
    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"known_word_color": "#1a237e"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ALL_PREFERENCE_KEYS == set(body.keys())
    assert body["known_word_color"] == "#1a237e"


async def test_put_requires_auth(client):
    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"known_word_color": "#000000"},
    )
    assert resp.status_code == 403


async def test_put_invalid_hex_color_returns_422(client):
    token = await _auth_token(client)
    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"known_word_color": "#zzzzzz"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_put_short_hex_color_returns_422(client):
    token = await _auth_token(client)
    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"known_word_color": "#fff"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_put_reps_below_min_returns_422(client):
    token = await _auth_token(client)
    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"passive_reps_for_known": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_put_reps_above_max_returns_422(client):
    token = await _auth_token(client)
    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"active_reps_for_known": 21},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_put_empty_body_changes_nothing(client):
    token = await _auth_token(client)

    get_resp = await client.get(
        "/api/v1/settings/preferences",
        headers={"Authorization": f"Bearer {token}"},
    )
    original = get_resp.json()

    put_resp = await client.put(
        "/api/v1/settings/preferences",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == original


async def test_put_only_changes_specified_field(client):
    token = await _auth_token(client)

    resp = await client.put(
        "/api/v1/settings/preferences",
        json={"passive_reps_for_known": 9},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()
    assert body["passive_reps_for_known"] == 9
    assert body["active_reps_for_known"] == DEFAULTS["active_reps_for_known"]
    assert body["known_word_color"] == DEFAULTS["known_word_color"]
