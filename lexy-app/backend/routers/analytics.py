from fastapi import APIRouter, Depends, Query

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import FailedItemStats, InteractedItemStats, ItemFrequency
from ..services import usage_events_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/unknown-frequent", response_model=list[ItemFrequency])
async def unknown_frequent(
    limit: int = Query(default=10, ge=1, le=50),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await usage_events_service.most_frequent_unknown_items(
        pool, str(current_user["user_id"]), limit
    )


@router.get("/learning-frequent", response_model=list[ItemFrequency])
async def learning_frequent(
    limit: int = Query(default=10, ge=1, le=50),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await usage_events_service.most_frequent_learning_items(
        pool, str(current_user["user_id"]), limit
    )


@router.get("/recently-failed", response_model=list[FailedItemStats])
async def recently_failed(
    limit: int = Query(default=10, ge=1, le=50),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await usage_events_service.recently_failed_items(
        pool, str(current_user["user_id"]), limit
    )


@router.get("/most-interacted", response_model=list[InteractedItemStats])
async def most_interacted(
    since_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await usage_events_service.most_interacted_items(
        pool, str(current_user["user_id"]), since_days, limit
    )
