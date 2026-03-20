from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_pool
from ..models.schemas import (
    CheckAnswerRequest,
    ClozeQuestionResult,
    ClozeQuestionsRequest,
    MagicSentencesRequest,
    MagicSentencesResponse,
)
from ..services import srs_service

router = APIRouter(prefix="/srs", tags=["srs"])


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
