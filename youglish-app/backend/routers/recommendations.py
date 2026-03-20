from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    ItemRecommendationsResponse,
    SentenceRecommendationsResponse,
    VideoRecommendationsResponse,
)
from ..services import recommendation_service

_VALID_ITEM_TYPES = {"word", "phrase", "grammar_rule"}

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/items", response_model=ItemRecommendationsResponse)
async def get_item_recommendations(
    language: str = Query(...),
    item_type: str = Query(default="word"),
    limit: int = Query(default=10, ge=1, le=50),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    if item_type not in _VALID_ITEM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"item_type must be one of {sorted(_VALID_ITEM_TYPES)}",
        )
    return await recommendation_service.recommend_items(
        pool,
        user_id=current_user["user_id"],
        language=language,
        item_type=item_type,
        limit=limit,
    )


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
