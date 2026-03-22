"""
Grammar rules as SRS items tests.

Source of truth: youglish-app/features/grammar-rules-srs/tests.md

Covers:
  Integration (real DB):
    Happy path:
      - PUT grammar_rule/{id}/status 'learning' → 200 with item_type='grammar_rule',
        status='learning'
      - After PUT, passive SRS card exists with default SM-2 values
      - No active SRS card is created (grammar rules are passive-only)
      - GET /srs/due?language=de returns a card for the grammar rule
      - Returned card has display_text = grammar_rule_table.title (not slug or ID)
      - Returned card has item_type='grammar_rule' and direction='passive'
    Edge cases:
      - PUT with 'known' → rule excluded from /srs/due
      - PUT with 'unknown' → no SRS card created
      - Double PUT with 'learning' → idempotent (exactly one card)
      - German rule NOT returned for /srs/due?language=fr
"""
import uuid

import pytest
from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
SRS_DUE  = "/api/v1/srs/due"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email() -> str:
    return f"test+{uuid.uuid4().hex[:10]}@example.com"


async def _register_and_login(client: AsyncClient, db_pool, email: str) -> tuple[dict, str]:
    await client.post(REGISTER, json={"email": email, "password": "password123"})
    r = await client.post(LOGIN, json={"email": email, "password": "password123"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    uid = str(await db_pool.fetchval("SELECT user_id FROM users WHERE email = $1", email))
    return headers, uid


async def _get_german_rule(db_pool) -> tuple[int, str, str]:
    """Return (rule_id, slug, title) for a seeded German grammar rule."""
    row = await db_pool.fetchrow(
        "SELECT rule_id, slug, title FROM grammar_rule_table WHERE language = 'de' LIMIT 1"
    )
    if row is None:
        pytest.skip("No grammar rules seeded for language='de'")
    return row["rule_id"], row["slug"], row["title"]


async def _get_passive_card(db_pool, uid: str, rule_id: int) -> dict | None:
    row = await db_pool.fetchrow(
        """
        SELECT interval_days, ease_factor, repetitions
          FROM srs_cards
         WHERE user_id = $1::uuid AND item_id = $2
           AND item_type = 'grammar_rule' AND direction = 'passive'
        """,
        uid, rule_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_put_grammar_rule_learning_returns_200(client: AsyncClient, db_pool):
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, _ = await _register_and_login(client, db_pool, _email())

    resp = await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["item_type"] == "grammar_rule"
    assert data["status"] == "learning"
    assert data["item_id"] == rule_id


async def test_put_grammar_rule_learning_creates_passive_srs_card(
    client: AsyncClient, db_pool
):
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    card = await _get_passive_card(db_pool, uid, rule_id)
    assert card is not None
    assert card["interval_days"] == 1.0
    assert card["ease_factor"] == 2.5
    assert card["repetitions"] == 0


async def test_put_grammar_rule_learning_no_active_card_created(
    client: AsyncClient, db_pool
):
    """Grammar rules are passive-only — no active SRS card must be created."""
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    active_card = await db_pool.fetchrow(
        """
        SELECT card_id FROM srs_cards
         WHERE user_id = $1::uuid AND item_id = $2
           AND item_type = 'grammar_rule' AND direction = 'active'
        """,
        uid, rule_id,
    )
    assert active_card is None


async def test_grammar_rule_appears_in_srs_due_with_title_as_display_text(
    client: AsyncClient, db_pool
):
    """GET /srs/due returns the grammar rule card; display_text must equal the title."""
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, _ = await _register_and_login(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    resp = await client.get(SRS_DUE, params={"language": "de"}, headers=headers)
    assert resp.status_code == 200

    rule_cards = [
        c for c in resp.json()
        if c["item_type"] == "grammar_rule" and c["item_id"] == rule_id
    ]
    assert len(rule_cards) >= 1
    assert rule_cards[0]["display_text"] == title
    assert rule_cards[0]["direction"] == "passive"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

async def test_put_grammar_rule_known_excludes_from_srs_due(client: AsyncClient, db_pool):
    """Promoting to 'known' must remove the rule from /srs/due."""
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, _ = await _register_and_login(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "learning"},
        headers=headers,
    )
    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "known"},
        headers=headers,
    )

    resp = await client.get(SRS_DUE, params={"language": "de"}, headers=headers)
    assert resp.status_code == 200
    rule_cards = [
        c for c in resp.json()
        if c["item_type"] == "grammar_rule" and c["item_id"] == rule_id
    ]
    assert rule_cards == []


async def test_put_grammar_rule_unknown_creates_no_srs_card(client: AsyncClient, db_pool):
    """status_marked_unknown has no SRS action — no card must be created."""
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "unknown"},
        headers=headers,
    )

    card = await db_pool.fetchrow(
        "SELECT card_id FROM srs_cards WHERE user_id = $1::uuid AND item_id = $2 AND item_type = 'grammar_rule'",
        uid, rule_id,
    )
    assert card is None


async def test_double_put_grammar_rule_learning_is_idempotent(
    client: AsyncClient, db_pool
):
    """Pressing 'Add to study' twice must not create a duplicate SRS card."""
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, uid = await _register_and_login(client, db_pool, _email())

    for _ in range(2):
        await client.put(
            f"/api/v1/words/grammar_rule/{rule_id}/status",
            json={"status": "learning"},
            headers=headers,
        )

    count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM srs_cards WHERE user_id = $1::uuid AND item_id = $2 AND item_type = 'grammar_rule'",
        uid, rule_id,
    )
    assert count == 1


async def test_german_grammar_rule_not_in_due_for_french(client: AsyncClient, db_pool):
    """A German grammar rule must NOT appear when querying /srs/due?language=fr."""
    rule_id, slug, title = await _get_german_rule(db_pool)
    headers, _ = await _register_and_login(client, db_pool, _email())

    await client.put(
        f"/api/v1/words/grammar_rule/{rule_id}/status",
        json={"status": "learning"},
        headers=headers,
    )

    resp = await client.get(SRS_DUE, params={"language": "fr"}, headers=headers)
    assert resp.status_code == 200
    rule_cards = [
        c for c in resp.json()
        if c["item_type"] == "grammar_rule" and c["item_id"] == rule_id
    ]
    assert rule_cards == []
