from fastapi import APIRouter

from ..models.schemas import MatchRequest, MatchResponse
from ..services import matcher_service

router = APIRouter(prefix="/sentences", tags=["matcher"])


@router.post("/match", response_model=MatchResponse)
async def match_sentence(body: MatchRequest):
    phrases = await matcher_service.match_sentence(body.sentence)
    return MatchResponse(sentence=body.sentence, phrases=phrases)
