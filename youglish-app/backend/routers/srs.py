from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..core.deps import get_current_user, rate_limit_llm
from ..database import get_pool
from ..models.schemas import (
    SRSAnswerRequest,
    SRSAnswerResponse,
    SRSProductionRequest,
    SRSProductionResponse,
    SRSReviewCard,
)
from ..services import review_service

router = APIRouter(prefix="/srs", tags=["srs"])


# ---------------------------------------------------------------------------
# Review session endpoints (real schema: srs_cards + user_word_knowledge)
# ---------------------------------------------------------------------------


@router.get("/due", response_model=list[SRSReviewCard])
async def get_due_cards(
    language: str = Query(..., min_length=2, max_length=5),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
):
    """Return due SRS cards with display text for the given language."""
    return await review_service.get_due_cards(
        pool, str(current_user["user_id"]), language, limit
    )


@router.post("/review/{card_id}", response_model=SRSAnswerResponse)
async def submit_review_answer(
    body: SRSAnswerRequest,
    card_id: int = Path(..., ge=1),
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
):
    """Submit a correct/incorrect answer for a single SRS card."""
    try:
        result = await review_service.submit_answer(
            pool, str(current_user["user_id"]), card_id, body.correct
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return SRSAnswerResponse(**result)


@router.post(
    "/review/{card_id}/produce",
    response_model=SRSProductionResponse,
    dependencies=[Depends(rate_limit_llm)],
)
async def submit_production_answer(
    body: SRSProductionRequest,
    card_id: int = Path(..., ge=1),
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
):
    """Submit a typed German answer for an active SRS card.

    Active cards must require either typed production (this endpoint) or an
    "I don't know" press (which uses the existing POST /review/{card_id}
    endpoint with correct=false). Self-grading is intentionally not exposed
    for active direction at the UI level.

    Rejects:
      - card not owned by the user → 404
      - passive card                → 400
      - grammar_rule card           → 400 (grammar is passive-only by design)
      - underlying target row gone  → 404
    """
    try:
        result = await review_service.submit_production_answer(
            pool, str(current_user["user_id"]), card_id, body.answer,
        )
    except ValueError as exc:
        message = str(exc)
        if message in ("card_not_found", "target_missing"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
        if message in ("passive_card", "grammar_rule"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        raise
    return SRSProductionResponse(**result)
