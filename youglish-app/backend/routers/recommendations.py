from fastapi import APIRouter, Depends, Query

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import SentenceRecommendationsResponse, VideoRecommendationsResponse
from ..services import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/sentences", response_model=SentenceRecommendationsResponse)
async def get_sentence_recommendations(
    language: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    target_unknown: int = Query(default=2, ge=1, le=8),
    min_unknown: int = Query(default=1, ge=0),
    max_unknown: int = Query(default=4, ge=1, le=15),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await recommendation_service.recommend_sentences(
        pool,
        user_id=current_user["user_id"],
        language=language,
        limit=limit,
        target_unknown=target_unknown,
        min_unknown=min_unknown,
        max_unknown=max_unknown,
    )


@router.get("/videos", response_model=VideoRecommendationsResponse)
async def get_video_recommendations(
    language: str = Query(...),
    limit: int = Query(default=5, ge=1, le=20),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await recommendation_service.recommend_videos(
        pool,
        user_id=current_user["user_id"],
        language=language,
        limit=limit,
    )
