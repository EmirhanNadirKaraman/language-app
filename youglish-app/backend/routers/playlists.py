from fastapi import APIRouter, Depends, HTTPException, status

from ..core.deps import get_current_user
from ..database import get_pool
from ..models.schemas import PlaylistGenerateRequest, PlaylistResult
from ..services import playlist_service

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.post("/generate", response_model=PlaylistResult, status_code=status.HTTP_200_OK)
async def generate_playlist(
    body: PlaylistGenerateRequest,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    try:
        result = await playlist_service.generate_playlist(
            pool,
            item_ids=body.item_ids,
            item_type=body.item_type,
            language=body.language,
            max_videos=body.max_videos,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return result
