import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..core.deps import get_current_user
from ..database import get_pool

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/stream")
async def notification_stream(
    request: Request,
    pool=Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """SSE stream — delivers unseen notifications as they arrive."""
    user_id = current_user["user_id"]

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break

                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT notification_id, type, payload
                        FROM   notification
                        WHERE  user_id = $1 AND seen = FALSE
                        ORDER  BY created_at
                        """,
                        user_id,
                    )
                    if rows:
                        ids = [r["notification_id"] for r in rows]
                        await conn.execute(
                            "UPDATE notification SET seen = TRUE "
                            "WHERE notification_id = ANY($1::int[])",
                            ids,
                        )
                        for row in rows:
                            data = json.dumps({
                                "type":    row["type"],
                                "payload": dict(row["payload"]),
                            })
                            yield f"data: {data}\n\n"
                    else:
                        yield ": heartbeat\n\n"

                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )
