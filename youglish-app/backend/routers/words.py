import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import WordKnowledgeRead, WordLookupResult, WordStatusUpdate
from ..services import progression_service, usage_events_service, word_service

router = APIRouter(prefix="/words", tags=["words"])


@router.get("/by-text", response_model=WordLookupResult | None)
async def get_word_by_text(
    word: str = Query(..., min_length=1),
    language: str = Query(...),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await word_service.lookup_word_by_text(
        pool, str(current_user["user_id"]), word, language
    )


@router.get("/knowledge", response_model=list[WordKnowledgeRead])
async def get_knowledge(
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await word_service.get_user_knowledge(pool, str(current_user["user_id"]))


@router.post("/word/{word_id}/transcript-click", status_code=204)
async def record_transcript_click(
    word_id: int = Path(..., ge=1),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """
    Record a transcript/subtitle word click as a passive exposure event.

    Fires progression_service 'transcript_clicked': increments passive_level by 1
    and creates an SRS passive card if one does not already exist.
    Does not advance an already-scheduled SRS card (a click is not a review answer).
    """
    user_id = str(current_user["user_id"])
    await progression_service.apply_progression(pool, user_id, word_id, "word", "transcript_clicked")
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
    # item_type is validated by Literal — FastAPI returns 422 automatically for unknown values
    user_id = str(current_user["user_id"])
    try:
        result = await word_service.upsert_word_status(pool, user_id, item_type, item_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Apply passive/active progression (awaited — primary knowledge-state update)
    _progression_event = {
        "learning": "status_marked_learning",
        "known":    "status_marked_known",
        "unknown":  "status_marked_unknown",
    }
    await progression_service.apply_progression(
        pool, user_id, item_id, item_type,
        _progression_event[body.status],
    )

    # Record analytics event
    _outcome_map = {"known": "correct", "learning": "used", "unknown": "seen"}
    asyncio.create_task(
        usage_events_service.record_event(
            pool, user_id, item_id, item_type,
            context="status_change",
            outcome=_outcome_map.get(body.status, "seen"),
        )
    )
    return result
