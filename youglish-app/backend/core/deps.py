import json

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.security import decode_token
from ..database import get_pool
from ..services import rate_limiter

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    pool=Depends(get_pool),
) -> dict:
    """FastAPI dependency. Returns {user_id, email, is_admin} or raises 401.

    Distinguishes token expiry from generic token errors so the frontend can
    react differently (silent re-login vs. surfacing a real auth bug). The
    `WWW-Authenticate` header on the expired branch follows RFC 6750.
    """
    try:
        user_id = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_expired",
            headers={
                "WWW-Authenticate":
                    'Bearer error="invalid_token", error_description="token expired"',
            },
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await pool.fetchrow(
        "SELECT user_id, email, settings FROM users WHERE user_id = $1::uuid",
        user_id,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    row = dict(user)
    row["user_id"] = str(row["user_id"])  # asyncpg returns UUID objects; normalize to str
    raw_settings = row.pop("settings") or "{}"
    settings = json.loads(raw_settings) if isinstance(raw_settings, str) else (raw_settings or {})
    row["is_admin"] = bool(settings.get("is_admin", False))
    return row


async def rate_limit_llm(current_user: dict = Depends(get_current_user)) -> None:
    """FastAPI dependency that gates LLM-backed routes (#12).

    Calls `rate_limiter.check_and_record(user_id)` which raises 429 when the
    user has exceeded the per-minute or per-hour budget. Depends on
    `get_current_user`, so any auth failure (401 / 403) fires *before* the
    rate-limit check — anonymous callers never reach the limiter.
    """
    await rate_limiter.check_and_record(str(current_user["user_id"]))
