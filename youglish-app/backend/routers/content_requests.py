from typing import Literal
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.deps import get_current_user
from ..database import get_pool

router = APIRouter(prefix="/content-requests", tags=["content-requests"])


class ContentRequestCreate(BaseModel):
    request_type: Literal["channel", "video"]
    content_id: str


class ContentRequestRead(BaseModel):
    request_id: int
    request_type: str
    content_id: str
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=ContentRequestRead, status_code=201)
async def submit_request(
    body: ContentRequestCreate,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """Submit a request to add a channel or video to the database.

    - If the request already exists and failed, it is reset to pending.
    - If it's already pending or done, the existing row is returned unchanged.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO content_request (user_id, request_type, content_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (request_type, content_id) DO UPDATE
                SET status     = CASE WHEN content_request.status = 'failed'
                                      THEN 'pending'
                                      ELSE content_request.status END,
                    error      = CASE WHEN content_request.status = 'failed'
                                      THEN NULL
                                      ELSE content_request.error END,
                    updated_at = NOW()
            RETURNING *
            """,
            current_user["user_id"],
            body.request_type,
            body.content_id,
        )
    return dict(row)


@router.get("", response_model=list[ContentRequestRead])
async def list_requests(
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """Return the current user's content requests, newest first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM content_request
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            current_user["user_id"],
        )
    return [dict(r) for r in rows]
