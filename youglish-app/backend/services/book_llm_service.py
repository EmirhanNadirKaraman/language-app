"""
book_llm_service.py

Selective LLM repair for OCR-extracted text blocks.

Design rules:
  - Only triggered explicitly (per-block or batch on low-confidence blocks).
  - Never sends an entire page or document — only the target block with minimal context.
  - Preserves original OCR text; stores the suggestion separately for user approval.
  - Uses the existing llm_cache_service to avoid re-querying for identical inputs.
  - Prompt enforces correction-only: no paraphrasing, no added content.
  - Returns structured output via tool use (not raw text).
"""
from __future__ import annotations

import logging
import os

import anthropic
import asyncpg

from . import llm_cache_service

logger = logging.getLogger(__name__)

_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_MODEL  = "claude-haiku-4-5-20251001"
_MOCK   = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are an OCR correction assistant. Your only job is to fix genuine OCR transcription errors.

Rules:
- Fix garbled characters, missing spaces, merged words, and visually similar letter
  substitutions (e.g. rn→m, cl→d, 0→O, 1→l).
- Do NOT rephrase, reorder, summarize, or add any content.
- Do NOT fix style, punctuation preferences, or spelling that might just be archaic.
- If the text looks correct and has no OCR errors, return it unchanged.
- You MUST call the fix_ocr_text tool — never respond with raw text.
"""

_FIX_TOOL: anthropic.types.ToolParam = {
    "name": "fix_ocr_text",
    "description": "Return the OCR-corrected version of the block text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "corrected_text": {
                "type": "string",
                "description": "The corrected text. Identical to input if no OCR errors found.",
            },
        },
        "required": ["corrected_text"],
    },
}


def _build_user_message(prev_text: str | None, block_text: str, next_text: str | None) -> str:
    parts = []
    if prev_text:
        parts.append(f"[PRECEDING CONTEXT]\n{prev_text}\n")
    parts.append(f"[BLOCK TO CORRECT]\n{block_text}")
    if next_text:
        parts.append(f"\n[FOLLOWING CONTEXT]\n{next_text}")
    return "\n".join(parts)


async def _call_llm(user_message: str) -> str:
    if _MOCK:
        return user_message  # echo back unchanged in mock mode

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=_SYSTEM,
        tools=[_FIX_TOOL],
        tool_choice={"type": "tool", "name": "fix_ocr_text"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "fix_ocr_text":
            return block.input.get("corrected_text", "")

    # Fallback: return the raw text content if tool use somehow wasn't called
    for block in response.content:
        if hasattr(block, "text"):
            return block.text.strip()

    raise RuntimeError("LLM returned no usable output")


# ── Public API ────────────────────────────────────────────────────────────────

async def repair_block(
    pool: asyncpg.Pool,
    block: dict,
    prev_clean_text: str | None = None,
    next_clean_text: str | None = None,
) -> str:
    """
    Request an LLM correction for a single OCR block.

    The result is a suggested corrected_text string. The caller is responsible
    for persisting it (via book_service.save_llm_correction).

    Uses cache so identical blocks are never re-sent to the LLM.

    Args:
        pool:            asyncpg connection pool (for cache lookup/write).
        block:           block dict with at least {block_id, ocr_text, clean_text}.
        prev_clean_text: clean_text of the preceding block for context.
        next_clean_text: clean_text of the following block for context.

    Returns:
        The suggested corrected text string.
    """
    # Use the raw OCR text as correction input; fall back to clean_text
    source_text = block.get("ocr_text") or block.get("clean_text") or ""
    if not source_text.strip():
        return ""

    cache_key = llm_cache_service.make_cache_key(
        "book_ocr_repair",
        _MODEL,
        {
            "text": source_text,
            "prev": prev_clean_text or "",
            "next": next_clean_text or "",
        },
    )

    cached = await llm_cache_service.get_cached(pool, cache_key)
    if cached is not None:
        logger.debug("book_llm_service: cache hit for block %s", block.get("block_id"))
        return cached.get("text", "")

    user_message = _build_user_message(prev_clean_text, source_text, next_clean_text)
    corrected    = await _call_llm(user_message)

    await llm_cache_service.set_cached(
        pool, cache_key, "book_ocr_repair", _MODEL, {"text": corrected}
    )
    return corrected


async def repair_block_by_id(
    pool: asyncpg.Pool,
    block_id: int,
    doc_id: str,
) -> str:
    """
    Convenience wrapper: fetch the block + its neighbours, run repair, persist suggestion.
    Returns the corrected_text string.
    """
    from . import book_service

    block = await book_service.get_block(pool, block_id, doc_id)
    if not block:
        raise ValueError(f"Block {block_id} not found in document {doc_id}")

    # Fetch adjacent blocks for context
    neighbours = await pool.fetch(
        """
        SELECT block_id, block_index, clean_text
          FROM book_blocks
         WHERE page_id = $1 AND block_type != 'ignored'
         ORDER BY block_index
        """,
        block["page_id"],
    )
    idx_map = {r["block_id"]: i for i, r in enumerate(neighbours)}
    pos = idx_map.get(block_id)

    prev_text = neighbours[pos - 1]["clean_text"] if (pos is not None and pos > 0) else None
    next_text = neighbours[pos + 1]["clean_text"] if (pos is not None and pos < len(neighbours) - 1) else None

    corrected = await repair_block(pool, block, prev_text, next_text)
    await book_service.save_llm_correction(pool, block_id, doc_id, corrected)
    return corrected
