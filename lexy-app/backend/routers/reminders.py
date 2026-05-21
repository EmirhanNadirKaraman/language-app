from fastapi import APIRouter, Depends

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import ReminderSummary
from ..services import reminder_service

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/summary", response_model=ReminderSummary)
async def get_reminder_summary(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
):
    user_id = str(current_user["user_id"])
    data = await reminder_service.get_summary(pool, user_id)
    return ReminderSummary(**data)
