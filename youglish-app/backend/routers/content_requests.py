import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.deps import get_current_user
from ..database import get_pool

router = APIRouter(prefix="/content-requests", tags=["content-requests"])

PIPELINE_SCRIPT = Path(__file__).parents[3] / "subtitle-scraper" / "pipeline.py"

# Holds a reference to the currently running pipeline subprocess, if any.
_pipeline_proc: asyncio.subprocess.Process | None = None


async def _spawn_pipeline() -> None:
    """Spawn pipeline.py --requests-only if it isn't already running."""
    global _pipeline_proc
    if _pipeline_proc is not None and _pipeline_proc.returncode is None:
        return  # already running — it will pick up the new request too
    _pipeline_proc = await asyncio.create_subprocess_exec(
        sys.executable, str(PIPELINE_SCRIPT), "--requests-only",
    )


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
    The pipeline is spawned immediately in the background to process it.
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

    result = dict(row)

    # Only spawn if the request is actually pending (not already done/in-progress)
    if result["status"] == "pending":
        asyncio.ensure_future(_spawn_pipeline())

    return result


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
