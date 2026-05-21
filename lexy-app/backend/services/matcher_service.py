"""
Thin async wrapper around phrase_finder's language-gated dispatcher.

phrase_finder.py lives in subtitle-scraper/ and loads the German spaCy
model + verb dictionary at module-import time. Stage 1 of the
second-language plan (2026-05-21) added `extract_phrases(doc, language)`
there: German routes to the existing German-specific logic; any other
language (including the next planned target Spanish 'es') returns an
empty list — words-only v1.

`_pf` is a normal module reference; the model and dictionary stay
resident for the lifetime of the process. Lazy-loading the German
resources is deferred to Stage 1b (the trigram-index bootstrap is
intertwined with verb_blueprint_map; safer to defer than to risk
subtle import-order regressions in the German hot path).
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

_SCRAPER_PATH = str(Path(__file__).resolve().parents[3] / "subtitle-scraper")

if _SCRAPER_PATH not in sys.path:
    sys.path.insert(0, _SCRAPER_PATH)

import phrase_finder as _pf


def _extract(sentence: str, language: str) -> list[dict]:
    """nlp(sentence) → Doc → phrase extraction. Sync — run via executor.

    Non-German languages short-circuit to `[]` inside `extract_phrases` so
    we still pay the spaCy nlp() cost (cheap; the German model is already
    in memory). The cost is only avoided when scoring is wholly skipped
    upstream. That's fine for the matcher route, which is rare-call.
    """
    doc = _pf.nlp(sentence)
    return _pf.extract_phrases(doc, language)


async def match_sentence(sentence: str, language: str = "de") -> list[dict]:
    """Run nlp() + extract_phrases in a thread so the sync spaCy call
    doesn't block the event loop.

    `language` defaults to "de" for backward compatibility with the
    single-arg callers (POST /api/v1/sentences/match, existing tests).
    For non-German content pass the matching language; the result will
    be an empty list (Stage 1, words-only v1 for L2).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract, sentence, language)


def get_blueprint_map() -> dict[str, str]:
    """Expose the verb blueprint dict loaded at module import time.

    Used by phrase_service.seed_from_blueprint_map() at application startup
    to populate phrase_table without re-reading the file from disk.

    German-only by design — there is no Spanish/French equivalent yet.
    """
    return _pf.verb_blueprint_map


async def match_sentence_with_ids(
    pool: asyncpg.Pool,
    sentence: str,
    language: str = "de",
) -> list[dict]:
    """Match a sentence and attach a phrase_id to each result where available.

    phrase_id is None when the canonical blueprint is not in phrase_table —
    for example, single nouns or verbs that matched via trigram fuzzy fallback
    to an unseeded entry.

    A single batch query looks up all canonical forms so there is at most one
    round-trip to the DB regardless of sentence length.

    `language` now threads through to `match_sentence` so non-German content
    short-circuits cleanly (returns []). Pre-Stage-1 this method silently
    ran the German extractor on any input regardless of `language`.
    """
    phrases = await match_sentence(sentence, language)
    if not phrases:
        return phrases

    unique_canonicals = list({p["dictionary_entry"] for p in phrases})
    rows = await pool.fetch(
        """
        SELECT phrase_id, canonical
        FROM phrase_table
        WHERE canonical = ANY($1::text[]) AND language = $2
        """,
        unique_canonicals, language,
    )
    canonical_to_id: dict[str, int] = {r["canonical"]: r["phrase_id"] for r in rows}

    return [
        {**p, "phrase_id": canonical_to_id.get(p["dictionary_entry"])}
        for p in phrases
    ]
