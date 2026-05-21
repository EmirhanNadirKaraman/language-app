import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    WordKnowledgeRead,
    WordLearnAnywayRequest,
    WordLookupResponse,
    WordLookupResult,
    WordStatusUpdate,
)
from ..services import progression_service, usage_events_service, word_service

logger = logging.getLogger(__name__)


class TranscriptClickBody(BaseModel):
    # Optional for backwards-compat with older clients. When supplied, the
    # backend dedups repeated clicks on (user, word, sentence, UTC day).
    # When omitted, progression fires every time as it did pre-T1.1.
    sentence_id: int | None = Field(default=None, ge=1)

router = APIRouter(prefix="/words", tags=["words"])


@router.get("/by-text", response_model=WordLookupResponse)
async def get_word_by_text(
    word: str = Query(..., min_length=1),
    language: str = Query(...),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    # W3 (Hole 2): response is a discriminated shape:
    #   status='not_found' | 'single' | 'ambiguous'
    # See word_service.lookup_word_by_text for the contract.
    return await word_service.lookup_word_by_text(
        pool, str(current_user["user_id"]), word, language
    )


@router.post("/learn-anyway", response_model=WordLookupResult)
async def learn_anyway(
    body: WordLearnAnywayRequest,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Adopt a word that isn't in word_table yet. Creates a sparse word_table
    row (pos='X') and marks the user's relationship to it as 'learning'.
    See word_service.learn_word_anyway for the contract. Idempotent —
    re-calling with the same text/language refreshes the user's state to
    'learning' but doesn't duplicate the catalog row.
    """
    user_id = str(current_user["user_id"])
    try:
        return await word_service.learn_word_anyway(
            pool, user_id, body.text, body.language,
        )
    except ValueError as exc:
        # Pydantic catches empty/long text; ValueError here means a guard
        # inside the service tripped (e.g. text became empty after strip).
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/knowledge", response_model=list[WordKnowledgeRead])
async def get_knowledge(
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await word_service.get_user_knowledge(pool, str(current_user["user_id"]))


@router.post("/word/{word_id}/transcript-click", status_code=204)
async def record_transcript_click(
    body: TranscriptClickBody | None = None,
    word_id: int = Path(..., ge=1),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Record a transcript/subtitle word click as a passive exposure event.

    With `sentence_id` in the body, the event is deduped per (user, word,
    sentence, UTC day) — only the first click in that scope applies
    progression. Subsequent clicks return 204 as a no-op. Without
    `sentence_id`, progression fires every time (legacy behaviour).

    Fires progression_service 'transcript_clicked' on the first new event:
    increments passive_level by 1 and creates an SRS passive card if one does
    not already exist. Does not advance an already-scheduled SRS card.
    """
    user_id = str(current_user["user_id"])
    sentence_id = body.sentence_id if body else None

    if sentence_id is not None:
        inserted = await usage_events_service.record_transcript_click_event(
            pool, user_id, word_id, "word", sentence_id,
        )
        if not inserted:
            # Same word, same sentence, same UTC day — no-op. Progression
            # already fired on the first click of this scope.
            return
        await progression_service.apply_progression(
            pool, user_id, word_id, "word", "transcript_clicked",
        )
        return

    # Legacy path: no sentence_id supplied. Fire progression every time and
    # log a debug warning so we can find any caller that still skips dedup.
    logger.debug(
        "transcript-click without sentence_id (user=%s word_id=%s) — no dedup",
        user_id, word_id,
    )
    await progression_service.apply_progression(
        pool, user_id, word_id, "word", "transcript_clicked",
    )
    asyncio.create_task(
        usage_events_service.record_event(
            pool, user_id, word_id, "word",
            context="transcript",
            outcome="seen",
        )
    )


@router.put("/{item_type}/{item_id}/status", response_model=WordKnowledgeRead)
async def update_status(
    body: WordStatusUpdate,
    item_type: Literal["word", "phrase", "grammar_rule"] = Path(...),
    item_id: int = Path(..., ge=1),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    # item_type and status are validated by Literal — Pydantic returns 422 for bad values.
    user_id = str(current_user["user_id"])

    _progression_event = {
        "learning": "status_marked_learning",
        "known":    "status_marked_known",
        "unknown":  "status_marked_unknown",
    }

    # Single atomic write: status + level deltas + SRS card moves all happen
    # inside one transaction in apply_progression. No silent-failure window.
    result = await progression_service.apply_progression(
        pool, user_id, item_id, item_type,
        _progression_event[body.status],
        status_override=body.status,
    )

    # Analytics event — fire-and-forget; analytics failure must not fail the request.
    _outcome_map = {"known": "correct", "learning": "used", "unknown": "seen"}
    asyncio.create_task(
        usage_events_service.record_event(
            pool, user_id, item_id, item_type,
            context="status_change",
            outcome=_outcome_map.get(body.status, "seen"),
        )
    )
    return result
