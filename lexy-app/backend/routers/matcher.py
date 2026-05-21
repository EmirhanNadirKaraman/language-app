from fastapi import APIRouter, Query

from ..models.schemas import MatchRequest, MatchResponse
from ..services import matcher_service

router = APIRouter(prefix="/sentences", tags=["matcher"])


@router.post("/match", response_model=MatchResponse)
async def match_sentence(
    body: MatchRequest,
    language: str = Query(default="de"),
):
    """Extract phrases from a sentence.

    `language` defaults to 'de' for back-compat with pre-Stage-1 callers
    that didn't pass a language query parameter. Non-German content
    routes through the dispatcher and returns an empty phrases list
    (words-only v1 for L2).
    """
    phrases = await matcher_service.match_sentence(body.sentence, language)
    return MatchResponse(sentence=body.sentence, phrases=phrases)
