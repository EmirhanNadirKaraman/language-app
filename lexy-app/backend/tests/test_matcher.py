"""
Tests for POST /api/v1/sentences/match.

These tests do not touch the database. A local fixture creates a client
that stubs out the DB pool lifecycle so the tests remain self-contained.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

MATCH = "/api/v1/sentences/match"


@pytest.fixture
async def matcher_client():
    """App client with DB pool creation stubbed out."""
    from backend.main import app

    with (
        patch("backend.database.create_pool", new_callable=AsyncMock),
        patch("backend.database.close_pool", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


async def test_response_contains_sentence_and_phrases(matcher_client: AsyncClient):
    resp = await matcher_client.post(MATCH, json={"sentence": "Ich lerne Deutsch."})

    assert resp.status_code == 200
    data = resp.json()
    assert data["sentence"] == "Ich lerne Deutsch."
    assert isinstance(data["phrases"], list)
    assert len(data["phrases"]) > 0


async def test_each_phrase_has_required_fields(matcher_client: AsyncClient):
    resp = await matcher_client.post(MATCH, json={"sentence": "Ich lerne Deutsch."})

    for phrase in resp.json()["phrases"]:
        assert "dictionary_entry" in phrase
        assert "sentence_phrase" in phrase
        assert "logic" in phrase
        assert "match_type" in phrase
        assert "indices" in phrase
        assert isinstance(phrase["sentence_phrase"], list)
        assert isinstance(phrase["indices"], list)


# ---------------------------------------------------------------------------
# Basic matching behaviour
# ---------------------------------------------------------------------------


async def test_verb_phrase_detected(matcher_client: AsyncClient):
    """'lerne' should produce a verb-type phrase with indices."""
    resp = await matcher_client.post(
        MATCH, json={"sentence": "Ich lade meine Freunde ein."}
    )
    phrases = resp.json()["phrases"]

    # At least one phrase should come from a VERB token
    verb_phrases = [p for p in phrases if "VERB" in p["logic"] or "->" in p["logic"]]
    assert len(verb_phrases) > 0


async def test_separable_verb_blueprint(matcher_client: AsyncClient):
    """'einladen' is a separable verb — the blueprint should include 'ein'."""
    resp = await matcher_client.post(
        MATCH, json={"sentence": "Ich lade meine Freunde zum Essen ein."}
    )
    phrases = resp.json()["phrases"]

    verb_entries = [p["dictionary_entry"] for p in phrases if "->" in p["logic"]]
    # At least one verb entry should reference einladen / ein
    assert any("ein" in e.lower() for e in verb_entries)


async def test_empty_sentence_returns_empty_phrases(matcher_client: AsyncClient):
    resp = await matcher_client.post(MATCH, json={"sentence": "   "})

    assert resp.status_code == 200
    assert resp.json()["phrases"] == []


async def test_missing_sentence_field_returns_422(matcher_client: AsyncClient):
    resp = await matcher_client.post(MATCH, json={})
    assert resp.status_code == 422
