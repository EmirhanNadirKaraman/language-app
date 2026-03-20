from fastapi import APIRouter, Depends

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import ReadingStatsResponse
from ..services import reading_stats_service

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("/{video_id}/reading-stats", response_model=ReadingStatsResponse)
async def reading_stats(
    video_id: str,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    stats = await reading_stats_service.get_video_stats(
        pool, video_id, str(current_user["user_id"])
    )
    return ReadingStatsResponse(video_id=video_id, **stats)


@router.get("/{video_id}/word-colors", response_model=dict[str, str])
async def word_colors(
    video_id: str,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await reading_stats_service.get_video_word_statuses(
        pool, video_id, str(current_user["user_id"])
    )
