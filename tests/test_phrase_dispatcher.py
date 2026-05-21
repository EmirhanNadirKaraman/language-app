"""
Stage 1 / second-language plan (2026-05-21).

phrase_finder.extract_phrases(doc, language) is the new dispatch entry
point. German routes to the existing extractor; everything else is
words-only for v1 and returns an empty list.

Tests live in the root tests/ tree (alongside subtitle/learning unit
tests) because phrase_finder lives in subtitle-scraper/, not the
backend tree.

We deliberately do NOT mutate sys.path at module level. The repo also
has a `pipeline.py` at root (the legacy in-memory pipeline), and other
test files (notably tests/test_scraper_channels.py) take care to
insert subtitle-scraper/ at sys.path[0] inside their own fixtures.
Persistent sys.path mutation here would push scraper past root in the
combined-run path and break those tests' import resolution.

Both phrase_finder and the scraper pipeline are loaded by explicit
file path via importlib.util — same module-name keys (`phrase_finder`,
`subtitle_scraper_pipeline`) cached for the test session.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_SCRAPER = Path(__file__).resolve().parent.parent / "subtitle-scraper"


def _load_by_path(name: str, file_path: Path):
    """Load `file_path` as a module under `name` without touching sys.path.

    Re-uses the cached module if already loaded in this session so the
    eager-loaded German spaCy model + verb dictionary aren't paid for twice.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load phrase_finder explicitly so this file doesn't depend on whether
# subtitle-scraper/ is on sys.path. The module under name 'phrase_finder'
# is the same key the scraper pipeline imports — by registering it first
# we share one cached German model across both modules.
pf = _load_by_path("phrase_finder", _SCRAPER / "phrase_finder.py")


@pytest.fixture(scope="module")
def german_doc():
    """A real German spaCy Doc — uses the module-loaded `nlp` so the
    test inherits the eager-loaded German model (Stage 1 keeps that
    eager; Stage 1b will revisit lazy)."""
    return pf.nlp("Ich lade meine Freunde zum Essen ein.")


# ---------------------------------------------------------------------------
# German path — byte-identical to the pre-Stage-1 call
# ---------------------------------------------------------------------------

def test_de_dispatch_matches_extract_german_logic(german_doc):
    """extract_phrases(doc, 'de') must return the same structure
    extract_german_logic(doc) does. Without this guarantee the dispatcher
    is a regression for the German hot path."""
    direct = pf.extract_german_logic(german_doc)
    dispatched = pf.extract_phrases(german_doc, "de")
    assert dispatched == direct
    assert len(dispatched) > 0, "Sanity: the test sentence should produce phrases"


def test_de_separable_verb_blueprint_preserved(german_doc):
    """Specific regression — 'einladen' separable verb pattern. Same
    assertion shape as tests/runtime / backend test_matcher equivalents."""
    phrases = pf.extract_phrases(german_doc, "de")
    verb_entries = [p["dictionary_entry"] for p in phrases if "->" in p["logic"]]
    assert any("ein" in e.lower() for e in verb_entries), (
        f"Expected an 'ein...'-prefixed verb entry; got {verb_entries!r}"
    )


# ---------------------------------------------------------------------------
# Non-German path — words-only v1, no extractor
# ---------------------------------------------------------------------------

def test_es_dispatch_returns_empty(german_doc):
    """Spanish has no extractor in v1 — words-only. Returns []."""
    assert pf.extract_phrases(german_doc, "es") == []


def test_fr_dispatch_returns_empty(german_doc):
    """French also has no extractor."""
    assert pf.extract_phrases(german_doc, "fr") == []


def test_unknown_language_returns_empty(german_doc):
    """Any unknown language code must not raise."""
    assert pf.extract_phrases(german_doc, "xx") == []


def test_empty_string_language_returns_empty(german_doc):
    """Edge case — empty string is treated like an unknown language."""
    assert pf.extract_phrases(german_doc, "") == []


def test_none_language_returns_empty(german_doc):
    """Edge case — None must not raise; treat as no extractor available.
    The dispatcher uses dict.get(language) which handles None naturally."""
    assert pf.extract_phrases(german_doc, None) == []


# ---------------------------------------------------------------------------
# Scraper integration — pipeline.insert_phrases is a no-op for L2
# ---------------------------------------------------------------------------

def _load_scraper_pipeline():
    """Load subtitle-scraper/pipeline.py by file path.

    The repo root also has a `pipeline.py` (the legacy in-memory pipeline);
    a bare `import pipeline` would resolve to whichever one Python's import
    machinery cached first. We load the scraper module under an explicit
    name and via importlib.util so this test is unambiguous about which
    `insert_phrases` it's exercising.

    NB: scraper's pipeline.py inserts its own directory into sys.path at
    module init (lines 27-29). When loaded via exec_module that mutation
    persists across the test session and pushes scraper past root in
    sys.path order — which breaks tests/test_scraper_channels.py' fixture
    that relies on inserting scraper at position 0 itself. We snapshot
    and restore sys.path around the exec so the side-effect is scoped to
    this helper.
    """
    if "subtitle_scraper_pipeline" in sys.modules:
        return sys.modules["subtitle_scraper_pipeline"]
    saved = list(sys.path)
    try:
        return _load_by_path("subtitle_scraper_pipeline", _SCRAPER / "pipeline.py")
    finally:
        sys.path[:] = saved


def test_insert_phrases_spanish_is_noop_and_does_not_crash(german_doc):
    """pipeline.insert_phrases(..., language='es') must return without
    touching the cursor at all — Spanish has no extractor in v1, so no
    phrase_blueprint / sentence_to_phrase INSERTs should fire.

    Uses a real German Doc to exercise the loop body (the dispatcher
    short-circuits inside extract_phrases, so any Doc shape works)."""
    from unittest.mock import MagicMock
    scraper = _load_scraper_pipeline()

    cursor = MagicMock()
    scraper.insert_phrases(cursor, [42], [german_doc], language="es")

    cursor.execute.assert_not_called()
    cursor.mogrify.assert_not_called()


def test_insert_phrases_unknown_language_is_noop(german_doc):
    from unittest.mock import MagicMock
    scraper = _load_scraper_pipeline()

    cursor = MagicMock()
    scraper.insert_phrases(cursor, [1, 2], [german_doc, german_doc], language="xx")

    cursor.execute.assert_not_called()

