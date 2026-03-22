"""
routers/reading.py

REST API for the interactive reading feature.

Endpoints:
  GET  /api/v1/books/{doc_id}/pages/{page_number}/word-statuses
       — word → status map for highlighting while reading
  POST /api/v1/books/{doc_id}/selections
       — save a custom learning unit (token selection)
  GET  /api/v1/books/{doc_id}/pages/{page_number}/selections
       — list saved selections anchored to a page
  GET  /api/v1/books/{doc_id}/selections
       — list all selections for a document
  PATCH /api/v1/reading/selections/{selection_id}
       — update note / status
  DELETE /api/v1/reading/selections/{selection_id}
       — delete a selection
  POST /api/v1/reading/translate
       — translate a sentence (LLM, cached)
  POST /api/v1/reading/explain
       — explain selected text in sentence context (LLM, cached)
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    DueSelectionItem,
    ExplainRequest,
    ExplainResponse,
    ReadingSelectionCreate,
    ReadingSelectionPatch,
    ReadingSelectionRead,
    ReadingSelectionAnchor,
    ReviewRequest,
    TranslateRequest,
    TranslateResponse,
)
from ..services import book_service, progression_service, reading_service, reading_llm_service

router = APIRouter(tags=["reading"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anchors_from_row(raw) -> list[ReadingSelectionAnchor]:
    """Parse anchors from DB (may be a string, list, or asyncpg Record)."""
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raw = []
    return [
        ReadingSelectionAnchor(
            block_id=a["block_id"],
            token_index=a["token_index"],
            surface=a["surface"],
        )
        for a in raw
    ]


def _row_to_selection(row: dict) -> ReadingSelectionRead:
    return ReadingSelectionRead(
        selection_id=str(row["selection_id"]),
        doc_id=str(row["doc_id"]),
        canonical=row["canonical"],
        surface_text=row["surface_text"],
        sentence_text=row["sentence_text"],
        anchors=_anchors_from_row(row["anchors"]),
        note=row.get("note"),
        status=row["status"],
        review_count=row.get("review_count", 0),
        next_review_at=row.get("next_review_at"),
        created_at=row["created_at"],
    )


async def _require_doc(pool, doc_id: str, user_id: str):
    doc = await book_service.get_document(pool, doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Book not found")
    return doc


# ---------------------------------------------------------------------------
# Word statuses for a page
# ---------------------------------------------------------------------------

@router.get("/books/{doc_id}/pages/{page_number}/word-statuses")
async def get_page_word_statuses(
    doc_id: str,
    page_number: int,
    language: str = "de",
    user=Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict[str, str]:
    """
    Return {word_lowercase: status} for every user-tagged word visible on this page.
    Words not in the user's vocabulary are absent (frontend treats absence as unknown).
    """
    await _require_doc(pool, doc_id, str(user["user_id"]))
    return await reading_service.get_word_statuses_for_page(
        pool, str(user["user_id"]), doc_id, page_number, language,
    )


# ---------------------------------------------------------------------------
# Selections — save and list
# ---------------------------------------------------------------------------

@router.post(
    "/books/{doc_id}/selections",
    response_model=ReadingSelectionRead,
    status_code=201,
)
async def save_selection(
    doc_id: str,
    body: ReadingSelectionCreate,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """
    Save a custom learning unit (one or more selected tokens from reading text).

    The caller supplies:
      canonical    — normalized form for deduplication
      surface_text — exact text as selected
      sentence_text — surrounding sentence (context container)
      anchors      — [{block_id, token_index, surface}]
      note         — optional user note
    """
    await _require_doc(pool, doc_id, str(user["user_id"]))
    row = await reading_service.save_selection(
        pool,
        user_id=str(user["user_id"]),
        doc_id=doc_id,
        canonical=body.canonical,
        surface_text=body.surface_text,
        sentence_text=body.sentence_text,
        anchors=[a.model_dump() for a in body.anchors],
        note=body.note,
    )

    # Feed the main progression system if this selection maps to a catalog item.
    # Equivalent to the user marking the word/phrase as 'learning' from the vocab view:
    # creates a passive SRS card and increments passive_level.
    catalog = await reading_service.find_catalog_item(pool, doc_id, body.canonical)
    if catalog:
        item_id, item_type = catalog
        await progression_service.apply_progression(
            pool, str(user["user_id"]), item_id, item_type, "status_marked_learning",
        )

    return _row_to_selection(row)


@router.get(
    "/books/{doc_id}/pages/{page_number}/selections",
    response_model=list[ReadingSelectionRead],
)
async def list_page_selections(
    doc_id: str,
    page_number: int,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """
    Return all selections that anchor to at least one block on this page.
    Used to highlight already-saved tokens when rendering the page.
    """
    await _require_doc(pool, doc_id, str(user["user_id"]))
    page = await book_service.get_page_detail(pool, doc_id, page_number)
    if not page:
        return []
    block_ids = [b["block_id"] for b in page["blocks"]]
    rows = await reading_service.list_selections_for_page(
        pool, str(user["user_id"]), doc_id, block_ids,
    )
    return [_row_to_selection(r) for r in rows]


@router.get(
    "/books/{doc_id}/selections",
    response_model=list[ReadingSelectionRead],
)
async def list_all_selections(
    doc_id: str,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """Return all saved selections for a document (for the review/library view)."""
    await _require_doc(pool, doc_id, str(user["user_id"]))
    rows = await reading_service.list_all_selections(
        pool, str(user["user_id"]), doc_id,
    )
    return [_row_to_selection(r) for r in rows]


# ---------------------------------------------------------------------------
# Selections — due across all books (must be before /{selection_id} routes)
# ---------------------------------------------------------------------------

@router.get("/reading/selections/due", response_model=list[DueSelectionItem])
async def list_due_selections(
    limit: int = 30,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """
    Return selections due for review across all the user's books.

    Due = status='learning' AND (next_review_at IS NULL OR next_review_at <= NOW()).
    NULL next_review_at means newly saved (never reviewed) — returned first.
    """
    rows = await reading_service.get_due_selections(pool, str(user["user_id"]), limit)
    return [
        DueSelectionItem(
            selection_id=str(r["selection_id"]),
            doc_id=str(r["doc_id"]),
            doc_title=r["doc_title"],
            canonical=r["canonical"],
            surface_text=r["surface_text"],
            sentence_text=r["sentence_text"],
            note=r.get("note"),
            review_count=r["review_count"],
            next_review_at=r.get("next_review_at"),
            created_at=r["created_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Selections — review a single unit
# ---------------------------------------------------------------------------

@router.post(
    "/reading/selections/{selection_id}/review",
    response_model=ReadingSelectionRead,
)
async def review_selection(
    selection_id: str,
    body: ReviewRequest,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """
    Record a review event for a custom learning unit.

    outcome='got_it'         — mark as recalled; increments review_count and
                               schedules next review per the interval table
    outcome='still_learning' — reset review_count, due immediately again
    outcome='mastered'       — move to 'mastered' status, exits review rotation
    """
    row = await reading_service.record_review(
        pool, selection_id, str(user["user_id"]), body.outcome,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Selection not found")

    # Mirror the review outcome onto the catalog item's passive SRS card if one exists.
    # 'mastered' carries no passive signal — the reading SRS simply exits rotation.
    _review_event = {
        "got_it":        "passive_review_correct",
        "still_learning": "passive_review_incorrect",
    }.get(body.outcome)

    if _review_event:
        catalog = await reading_service.find_catalog_item(
            pool, str(row["doc_id"]), row["canonical"],
        )
        if catalog:
            item_id, item_type = catalog
            await progression_service.apply_progression(
                pool, str(user["user_id"]), item_id, item_type, _review_event,
            )

    return _row_to_selection(row)


# ---------------------------------------------------------------------------
# Selections — update and delete
# ---------------------------------------------------------------------------

@router.patch(
    "/reading/selections/{selection_id}",
    response_model=ReadingSelectionRead,
)
async def update_selection(
    selection_id: str,
    body: ReadingSelectionPatch,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """Update the note and/or status of a saved selection."""
    row = await reading_service.update_selection(
        pool,
        selection_id=selection_id,
        user_id=str(user["user_id"]),
        note=body.note,
        status=body.status,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Selection not found")
    return _row_to_selection(row)


@router.delete("/reading/selections/{selection_id}", status_code=204)
async def delete_selection(
    selection_id: str,
    user=Depends(get_current_user),
    pool=Depends(get_pool),
):
    """Delete a saved selection."""
    deleted = await reading_service.delete_selection(
        pool, selection_id, str(user["user_id"]),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Selection not found")


# ---------------------------------------------------------------------------
# LLM — sentence translation
# ---------------------------------------------------------------------------

@router.post("/reading/translate", response_model=TranslateResponse)
async def translate(
    body: TranslateRequest,
    user=Depends(get_current_user),  # noqa: ARG001  (auth guard only)
    pool=Depends(get_pool),
):
    """
    Translate a sentence into English.
    Results are cached permanently in llm_cache keyed by (sentence, language).
    """
    translation = await reading_llm_service.translate_sentence(
        body.sentence, body.language, pool=pool,
    )
    return TranslateResponse(translation=translation)


# ---------------------------------------------------------------------------
# LLM — contextual explanation
# ---------------------------------------------------------------------------

@router.post("/reading/explain", response_model=ExplainResponse)
async def explain(
    body: ExplainRequest,
    user=Depends(get_current_user),  # noqa: ARG001  (auth guard only)
    pool=Depends(get_pool),
):
    """
    Explain a selected word/phrase in the context of its full sentence.
    Results are cached permanently in llm_cache keyed by (selection, sentence, language).
    """
    explanation = await reading_llm_service.explain_in_context(
        body.selection, body.sentence, body.language, pool=pool,
    )
    return ExplainResponse(explanation=explanation)
