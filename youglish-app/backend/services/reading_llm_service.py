"""
reading_llm_service.py

LLM functions for the interactive reading feature.

  translate_sentence   -- translate a sentence into English (cached permanently)
  explain_in_context   -- explain a selected unit in the context of its sentence (cached)

Both functions follow the same caching pattern as llm_service.py:
  make_cache_key -> get_cached -> (call LLM) -> set_cached
"""
from __future__ import annotations

import os

import anthropic
import asyncpg

from . import llm_cache_service

_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_MOCK = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")
_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Sentence translation
# ---------------------------------------------------------------------------

_TRANSLATE_TOOL: anthropic.types.ToolParam = {
    "name": "translate_sentence",
    "description": "Translate a sentence into natural English.",
    "input_schema": {
        "type": "object",
        "properties": {
            "translation": {
                "type": "string",
                "description": "A natural, fluent English translation of the sentence.",
            }
        },
        "required": ["translation"],
    },
}


async def translate_sentence(
    sentence: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> str:
    """
    Translate a sentence from `language` into English.

    Cached permanently by (sentence, language) -- the same sentence always
    gets the same translation, so re-selecting it is instant.
    """
    if _MOCK:
        return f"[Mock translation of {language} sentence: \"{sentence[:60]}\"]"

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "reading_translate", _MODEL,
            {"sentence": sentence, "language": language},
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached["translation"]

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=(
            f"You are a precise translator. Translate the following {language} sentence into "
            f"natural, fluent English. Preserve the meaning faithfully. "
            f"You MUST call the translate_sentence tool."
        ),
        tools=[_TRANSLATE_TOOL],
        tool_choice={"type": "tool", "name": "translate_sentence"},
        messages=[{"role": "user", "content": f"Translate: {sentence}"}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    translation: str = tool_block.input["translation"]

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(
            pool, cache_key, "reading_translate", _MODEL,
            {"translation": translation},
        )

    return translation


# ---------------------------------------------------------------------------
# Contextual explanation
# ---------------------------------------------------------------------------

_EXPLAIN_TOOL: anthropic.types.ToolParam = {
    "name": "explain_in_context",
    "description": "Explain the meaning and usage of a selected word or phrase within its sentence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "explanation": {
                "type": "string",
                "description": (
                    "2-3 sentences explaining the selected text specifically in this sentence. "
                    "Cover: (1) what it means here, (2) its grammatical role or structure, "
                    "(3) any useful pattern or usage note for learners."
                ),
            }
        },
        "required": ["explanation"],
    },
}


async def explain_in_context(
    selection: str,
    sentence: str,
    language: str,
    *,
    pool: asyncpg.Pool | None = None,
) -> str:
    """
    Explain `selection` in the context of `sentence`.

    Cached permanently by (canonical_selection, sentence, language).
    The selection is lowercased before hashing to avoid duplicate cache
    entries for the same unit with different capitalisation.
    """
    if _MOCK:
        return (
            f"[Mock explanation: \"{selection}\" is used in this sentence to express "
            f"a key concept. In {language}, this construction typically follows "
            f"the pattern shown here. Pay attention to the grammatical case used.]"
        )

    cache_key: str | None = None
    if pool is not None:
        cache_key = llm_cache_service.make_cache_key(
            "reading_explain", _MODEL,
            {
                "selection": selection.lower(),
                "sentence": sentence,
                "language": language,
            },
        )
        cached = await llm_cache_service.get_cached(pool, cache_key)
        if cached is not None:
            return cached["explanation"]

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=(
            f"You are a {language} language learning assistant helping an intermediate learner "
            f"understand a word or phrase in context. "
            f"Be concise (2-3 sentences), practical, and focused on meaning-in-context. "
            f"Mention grammatical structure only when it matters for understanding. "
            f"You MUST call the explain_in_context tool."
        ),
        tools=[_EXPLAIN_TOOL],
        tool_choice={"type": "tool", "name": "explain_in_context"},
        messages=[{
            "role": "user",
            "content": (
                f"Sentence: {sentence}\n\n"
                f"Selected: \"{selection}\"\n\n"
                f"Explain what \"{selection}\" means and how it works in this sentence."
            ),
        }],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    explanation: str = tool_block.input["explanation"]

    if pool is not None and cache_key is not None:
        await llm_cache_service.set_cached(
            pool, cache_key, "reading_explain", _MODEL,
            {"explanation": explanation},
        )

    return explanation
