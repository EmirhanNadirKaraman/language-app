from fastapi import APIRouter, Depends

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import UserPreferences, UserPreferencesUpdate
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
