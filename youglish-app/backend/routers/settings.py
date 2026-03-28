from fastapi import APIRouter, Depends

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import (
    CategoryPreferenceRequest,
    ChannelPreferenceRequest,
    UserPreferences,
    UserPreferencesUpdate,
)
from ..services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/preferences", response_model=UserPreferences)
async def get_preferences(
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await settings_service.get_preferences(pool, current_user["user_id"])


@router.put("/preferences", response_model=UserPreferences)
async def update_preferences(
    body: UserPreferencesUpdate,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    return await settings_service.update_preferences(pool, current_user["user_id"], updates)


@router.put("/channel-preference", response_model=UserPreferences)
async def set_channel_preference(
    body: ChannelPreferenceRequest,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await settings_service.channel_preference_action(
        pool,
        str(current_user["user_id"]),
        body.channel_id,
        body.channel_name,
        body.action,
    )


@router.put("/category-preference", response_model=UserPreferences)
async def set_category_preference(
    body: CategoryPreferenceRequest,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    return await settings_service.category_preference_action(
        pool,
        str(current_user["user_id"]),
        body.category,
        body.action,
    )
