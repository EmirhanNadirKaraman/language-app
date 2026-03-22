from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    CheckAnswerRequest,
    ClozeQuestionResult,
    ClozeQuestionsRequest,
    MagicSentencesRequest,
    MagicSentencesResponse,
    SRSAnswerRequest,
    SRSAnswerResponse,
    SRSReviewCard,
)
from ..services import review_service, srs_service

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


# ---------------------------------------------------------------------------
# Legacy endpoints below — reference tables from an older schema that do not
# exist in this project's migrations. Kept to avoid routing changes but will
# fail at runtime if called.
# ---------------------------------------------------------------------------


@router.post("/check-answer", status_code=status.HTTP_200_OK)
async def check_answer(body: CheckAnswerRequest, pool=Depends(get_pool)):
    try:
        await srs_service.check_answer(pool, body.uid, body.word_id, body.correct)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"success": True}


@router.post("/magic-sentences", response_model=MagicSentencesResponse)
async def get_magic_sentences(body: MagicSentencesRequest, pool=Depends(get_pool)):
    try:
        data = await srs_service.get_magic_sentences(
            pool,
            uid=body.uid,
            word_id=body.word_id,
            language=body.language,
            full_sentence=body.full_sentence,
            page=body.page,
            rows_per_page=body.rows_per_page,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return data


@router.post("/cloze-questions", response_model=list[ClozeQuestionResult])
async def get_cloze_questions(body: ClozeQuestionsRequest, pool=Depends(get_pool)):
    try:
        data = await srs_service.get_cloze_questions(
            pool,
            uid=body.uid,
            native_language=body.native_language,
            target_language=body.target_language,
            is_exact=body.is_exact,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return data
