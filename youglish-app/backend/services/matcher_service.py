"""
Thin async wrapper around phrase_finder.extract_german_logic.

phrase_finder.py lives in subtitle-scraper/ and loads both the spaCy model
and the verb dictionary at module-import time (module-level globals). It
resolves its data path from `__file__`, so importing it only requires
adding subtitle-scraper/ to sys.path — no cwd mutation.

`_pf` is a normal module reference; the model and dictionary stay resident
for the lifetime of the process.
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

_SCRAPER_PATH = str(Path(__file__).resolve().parents[3] / "subtitle-scraper")

if _SCRAPER_PATH not in sys.path:
    sys.path.insert(0, _SCRAPER_PATH)

import phrase_finder as _pf


def _extract(sentence: str) -> list[dict]:
    """nlp(sentence) → Doc → phrase extraction. Sync — run via executor.

    `extract_german_logic` expects a spaCy Doc (it iterates tokens and reads
    `token.i`). Passing a string causes AttributeError mid-loop. We do the
    nlp() conversion here so callers can pass plain text.
    """
    doc = _pf.nlp(sentence)
    return _pf.extract_german_logic(doc)


async def match_sentence(sentence: str) -> list[dict]:
    """Run nlp() + extract_german_logic in a thread so the sync spaCy call
    doesn't block the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract, sentence)


def get_blueprint_map() -> dict[str, str]:
    """Expose the verb blueprint dict loaded at module import time.

    Used by phrase_service.seed_from_blueprint_map() at application startup
    to populate phrase_table without re-reading the file from disk.
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
    """
    phrases = await match_sentence(sentence)
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
