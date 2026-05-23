"""
TODO #38 / route B — frequency-ranked, language-aware autocomplete.

search_service.suggest now does a case-insensitive PREFIX match over
word_table scoped to the active language, ranked by the precomputed
`frequency` column (migration 032). Replaces the old phrase_blueprint-only,
German-only, language-ignoring behaviour that returned [] for Spanish.

Tests insert synthetic rows under a 'zzqx' prefix (no real corpus word
starts with that) so they're isolated and easy to clean up.
"""
from __future__ import annotations

import pytest

from backend.services import search_service


_PREFIX = "zzqx"


@pytest.fixture
async def seeded_words(db_pool):
    """Insert frequency-ranked es + en words sharing the test prefix."""
    rows = [
        # (word, language, frequency)
        ("zzqxalto",   "es", 100),
        ("zzqxalta",   "es", 40),
        ("Zzqxalto",   "es", 5),    # casing variant of zzqxalto — should collapse
        ("zzqxbajo",   "es", 70),   # different prefix branch
        ("zzqxalto",   "en", 999),  # same surface, different language — must not leak into es
    ]
    ids = []
    for word, lang, freq in rows:
        wid = await db_pool.fetchval(
            """
            INSERT INTO word_table (word, language, pos, tag, lemma, frequency)
            VALUES ($1, $2, 'NOUN', 'NOUN', $1, $3)
            ON CONFLICT (word, language, pos) DO UPDATE SET frequency = EXCLUDED.frequency
            RETURNING word_id
            """,
            word, lang, freq,
        )
        ids.append(wid)
    yield
    await db_pool.execute("DELETE FROM word_table WHERE word LIKE $1 OR word LIKE $2",
                          f"{_PREFIX}%", f"{_PREFIX.capitalize()}%")


async def test_suggest_returns_frequency_ranked_words(db_pool, seeded_words):
    out = await search_service.suggest(db_pool, "zzqxa", "es")
    words = [r["word"] for r in out]
    # zzqxalto (100) before zzqxalta (40); zzqxbajo excluded (prefix 'zzqxa').
    assert words[:2] == ["zzqxalto", "zzqxalta"], words
    assert all(r["type"] == "word" for r in out)
    assert out[0]["score"] == 100.0


async def test_suggest_collapses_casing_to_highest_frequency(db_pool, seeded_words):
    out = await search_service.suggest(db_pool, "zzqxalto", "es")
    # Only one 'zzqxalto' entry, the freq-100 lowercase casing — not the
    # freq-5 'Zzqxalto'.
    matches = [r for r in out if r["word"].lower() == "zzqxalto"]
    assert len(matches) == 1
    assert matches[0]["word"] == "zzqxalto"
    assert matches[0]["score"] == 100.0


async def test_suggest_is_language_scoped(db_pool, seeded_words):
    """The en 'zzqxalto' (freq 999) must NOT appear in es suggestions even
    though it has the highest frequency overall."""
    es = await search_service.suggest(db_pool, "zzqxalto", "es")
    assert all(r["score"] != 999.0 for r in es), "English row leaked into es"

    en = await search_service.suggest(db_pool, "zzqxalto", "en")
    assert en and en[0]["score"] == 999.0


async def test_suggest_empty_query_returns_empty(db_pool):
    assert await search_service.suggest(db_pool, "", "es") == []
    assert await search_service.suggest(db_pool, "   ", "es") == []


async def test_suggest_no_language_returns_empty(db_pool, seeded_words):
    """Without a language we don't scan the whole multi-language table."""
    assert await search_service.suggest(db_pool, "zzqx", None) == []


async def test_suggest_respects_limit(db_pool, seeded_words):
    out = await search_service.suggest(db_pool, "zzqx", "es", limit=2)
    assert len(out) == 2
    # Highest-frequency first: zzqxalto (100), zzqxbajo (70).
    assert [r["word"] for r in out] == ["zzqxalto", "zzqxbajo"]


# ---------------------------------------------------------------------------
# kind = words | phrases | both (user-selected via SearchBar)
# ---------------------------------------------------------------------------

@pytest.fixture
async def seeded_de(db_pool):
    """German word rows + a German phrase_blueprint row sharing the prefix."""
    await db_pool.execute(
        """
        INSERT INTO word_table (word, language, pos, tag, lemma, frequency)
        VALUES ('zzqxgeben', 'de', 'VERB', 'VERB', 'zzqxgeben', 80)
        ON CONFLICT (word, language, pos) DO UPDATE SET frequency = EXCLUDED.frequency
        """
    )
    await db_pool.execute(
        """
        INSERT INTO phrase_blueprint (lookup_key, blueprint)
        VALUES ('zzqxgeben', 'zzqxgeben jdm. etw.')
        ON CONFLICT (lookup_key) DO NOTHING
        """
    )
    yield
    await db_pool.execute("DELETE FROM word_table WHERE word LIKE 'zzqx%'")
    await db_pool.execute("DELETE FROM phrase_blueprint WHERE lookup_key LIKE 'zzqx%'")


async def test_suggest_kind_words_excludes_phrases(db_pool, seeded_de):
    out = await search_service.suggest(db_pool, "zzqxgeb", "de", kind="words")
    assert out and all(r["type"] == "word" for r in out)
    assert any(r["word"] == "zzqxgeben" for r in out)


async def test_suggest_kind_phrases_returns_only_phrases(db_pool, seeded_de):
    # phrase_blueprint matching is whole-word (\m…\M), not prefix, so query
    # the full word — this is the pre-existing German phrase-suggest behaviour.
    out = await search_service.suggest(db_pool, "zzqxgeben", "de", kind="phrases")
    assert out and all(r["type"] == "phrase" for r in out)
    assert any("jdm. etw." in r["word"] for r in out)


async def test_suggest_kind_both_includes_each_type(db_pool, seeded_de):
    out = await search_service.suggest(db_pool, "zzqxgeben", "de", kind="both")
    types = {r["type"] for r in out}
    assert "word" in types and "phrase" in types
    # phrases lead in 'both'
    assert out[0]["type"] == "phrase"


async def test_suggest_phrases_empty_for_non_phrase_language(db_pool, seeded_words):
    """Spanish has no phrase source — kind='phrases' yields nothing,
    kind='both' degrades to words only."""
    assert await search_service.suggest(db_pool, "zzqx", "es", kind="phrases") == []
    both = await search_service.suggest(db_pool, "zzqxa", "es", kind="both")
    assert both and all(r["type"] == "word" for r in both)


async def test_suggest_invalid_kind_falls_back_to_words(db_pool, seeded_words):
    out = await search_service.suggest(db_pool, "zzqxa", "es", kind="bogus")
    assert out and all(r["type"] == "word" for r in out)
