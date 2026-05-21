"""Account self-service endpoints.

DELETE /api/v1/account permanently removes the authenticated user's account
and all owned private data. All FKs to `users(user_id)` declare either
`ON DELETE CASCADE` (the dominant path — see migration audit in
`docs/PRIVACY.md`) or `ON DELETE SET NULL` (`content_request`,
`client_error_log` — intentionally anonymised, not deleted, so error and
operational signal survives).

Shared catalog tables (`word_table`, `phrase_table`, `grammar_rule_table`,
`channel`, `video`, `sentence`, `language_table`, `llm_cache`, …) have no
`user_id` FK and are left intact.

Bearer-token only deletes the *current* user. There is no admin-deletes-other
endpoint; that would need a separate route + admin gate.
"""
from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from ..core.deps import get_current_user
from ..database import get_pool

router = APIRouter(prefix="/account", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> Response:
    """Delete the authenticated user and all cascading private data.

    Single statement, transactional by virtue of being one statement — asyncpg
    wraps each `execute` in an implicit transaction. Cascade fan-out happens
    inside Postgres atomically.
    """
    await pool.execute(
        "DELETE FROM users WHERE user_id = $1::uuid",
        current_user["user_id"],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
