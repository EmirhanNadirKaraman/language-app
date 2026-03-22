"""
Insight cards and prep view service.

Surfaces two analytics-backed insight cards for the home screen:
  1. frequent_unknowns — items with 'unknown' status that appear most often
  2. recent_mistakes   — items most recently answered incorrectly

Both cards use the combined priority score from prioritization_service to rank
within their candidate pool, so the primary target reflects the full signal set
(due, mistake recency, frequency, learning status) rather than a single raw metric.

Prep view
---------
get_prep_data() returns translation + grammar explanation (always, from LLM cache
or generated fresh) plus examples/templates only if already cached.  Missing
examples are signalled via has_examples=False so the frontend shows a
"Generate examples" button that calls llm_service.prep_generate_examples().

For phrase items, prep_data also includes linked_grammar_rules — a list of
GrammarRuleRef dicts resolved from the phrase's phrase_type via grammar_service.
"""
from __future__ import annotations

import asyncio

import asyncpg

from .prioritization_service import get_prioritized_items
from .usage_events_service import most_frequent_unknown_items, recently_failed_items
from .recommendation_service import enrich_items
from .phrase_service import enrich_phrases
from . import llm_service, grammar_service


_CARD_CONFIGS: dict[str, dict] = {
    "frequent_unknowns": {
        "title": "Keeps coming up",
        "explanation": "You've encountered these before but they haven't clicked yet.",
    },
    "recent_mistakes": {
        "title": "Recent mistakes",
        "explanation": "You got these wrong recently — a good time to revisit.",
    },
}


async def _build_card(
    card_type: str,
    raw_rows: list[dict],
    score_map: dict,
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
) -> dict:
    config = _CARD_CONFIGS[card_type]

    scored = []
    for row in raw_rows:
        item_id = row["item_id"]
        pitem = score_map.get(item_id)
        score = pitem.score if pitem else 0.0
        signals = (
            pitem.signals if pitem
            else {"is_due": 0.0, "mistake_recency": 0.0, "freq_rank": 0.0, "is_learning": 0.0}
        )
        reasons = pitem.reasons if pitem else []
        scored.append({
            "item_id":   item_id,
            "item_type": row["item_type"],
            "score":     score,
            "signals":   signals,
            "reasons":   reasons,
            "raw":       row,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:3]

    if not top:
        return {**config, "card_type": card_type, "items": []}

    word_ids   = [c["item_id"] for c in top if c["item_type"] == "word"]
    phrase_ids = [c["item_id"] for c in top if c["item_type"] == "phrase"]

    async def _empty() -> dict:
        return {}

    word_enrichment, phrase_enrichment = await asyncio.gather(
        enrich_items(pool, user_id, word_ids, language)     if word_ids   else _empty(),
        enrich_phrases(pool, user_id, phrase_ids, language) if phrase_ids else _empty(),
    )
    enrichment = {**word_enrichment, **phrase_enrichment}

    items = []
    for c in top:
        meta = enrichment.get(c["item_id"])
        if meta is None:
            continue

        extra: dict = {}
        if card_type == "frequent_unknowns":
            extra["event_count"] = c["raw"].get("event_count", 0)
        elif card_type == "recent_mistakes":
            extra["fail_count"] = c["raw"].get("fail_count", 0)
            last_failed = c["raw"].get("last_failed")
            if last_failed is not None:
                extra["last_failed"] = last_failed.isoformat()

        items.append({
            "item_id":        c["item_id"],
            "item_type":      c["item_type"],
            "display_text":   meta["display_text"],
            "secondary_text": meta["secondary_text"],
            "score":          c["score"],
            "reasons":        c["reasons"],
            "signals":        c["signals"],
            "extra":          extra,
        })

    return {**config, "card_type": card_type, "items": items}


async def get_insight_cards(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
) -> dict:
    """Return two insight cards for the home-screen Insights section."""
    freq_rows, mistake_rows, word_priority, phrase_priority = await asyncio.gather(
        most_frequent_unknown_items(pool, user_id, limit=20),
        recently_failed_items(pool, user_id, limit=20),
        get_prioritized_items(pool, user_id, item_type="word",   limit=200),
        get_prioritized_items(pool, user_id, item_type="phrase", limit=200),
    )

    score_map = {item.item_id: item for item in word_priority}
    score_map.update({item.item_id: item for item in phrase_priority})

    freq_card, mistake_card = await asyncio.gather(
        _build_card("frequent_unknowns", freq_rows,    score_map, pool, user_id, language),
        _build_card("recent_mistakes",   mistake_rows, score_map, pool, user_id, language),
    )

    return {"cards": [freq_card, mistake_card], "language": language}


async def get_item_display_text(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    language: str,
) -> str | None:
    """Return display_text for a single item, or None if not found."""
    if item_type == "word":
        enrichment = await enrich_items(pool, user_id, [item_id], language)
    elif item_type == "phrase":
        enrichment = await enrich_phrases(pool, user_id, [item_id], language)
    else:
        return None
    meta = enrichment.get(item_id)
    return meta["display_text"] if meta else None


async def get_prep_data(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    language: str,
) -> dict | None:
    """
    Return prep view data for a single item.

    Translation + grammar explanation are always included (fetched from LLM
    cache or generated fresh on first visit).  Examples/templates are returned
    only if already cached — missing examples surface as has_examples=False.

    For phrase items, linked_grammar_rules contains rules matched by phrase_type.
    For word items, linked_grammar_rules contains rules matched by lemma.
    """
    if item_type == "word":
        enrichment = await enrich_items(pool, user_id, [item_id], language)
    elif item_type == "phrase":
        enrichment = await enrich_phrases(pool, user_id, [item_id], language)
    else:
        return None

    meta = enrichment.get(item_id)
    if meta is None:
        return None

    display_text = meta["display_text"]

    # For phrases: fetch linked grammar rules concurrently with item info + examples
    if item_type == "phrase":
        phrase_type = meta.get("secondary_text", "")  # phrase_service stores phrase_type here
        item_info, cached_examples, linked_rules = await asyncio.gather(
            llm_service.prep_item_info(display_text, item_type, language, pool=pool),
            llm_service.get_examples_if_cached(display_text, item_type, language, pool=pool),
            grammar_service.get_rules_for_phrase_type(pool, phrase_type, language),
        )
    else:
        lemma = meta.get("lemma") or display_text
        item_info, cached_examples, linked_rules = await asyncio.gather(
            llm_service.prep_item_info(display_text, item_type, language, pool=pool),
            llm_service.get_examples_if_cached(display_text, item_type, language, pool=pool),
            grammar_service.get_rules_for_lemma(pool, lemma, language),
        )

    has_examples = cached_examples is not None
    example   = cached_examples["example"]           if has_examples else None
    templates = cached_examples.get("templates", []) if has_examples else []

    return {
        "item_id":              item_id,
        "item_type":            item_type,
        "display_text":         display_text,
        "translation":          item_info["translation"],
        "grammar_structure":    item_info.get("grammar_structure"),
        "grammar_explanation":  item_info["grammar_explanation"],
        "example":              example,
        "templates":            templates,
        "has_examples":         has_examples,
        "linked_grammar_rules": linked_rules,
    }
