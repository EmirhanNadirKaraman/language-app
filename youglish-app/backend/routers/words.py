from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import WordKnowledgeRead, WordLookupResult, WordStatusUpdate
from ..services import word_service

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


@router.put("/{item_type}/{item_id}/status", response_model=WordKnowledgeRead)
async def update_status(
    body: WordStatusUpdate,
    item_type: Literal["word", "phrase", "grammar_rule"] = Path(...),
    item_id: int = Path(..., ge=1),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    # item_type is validated by Literal — FastAPI returns 422 automatically for unknown values
    try:
        result = await word_service.upsert_word_status(
            pool, str(current_user["user_id"]), item_type, item_id, body.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return result
