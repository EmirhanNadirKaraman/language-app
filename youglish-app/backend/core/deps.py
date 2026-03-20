import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.security import decode_token
from ..database import get_pool

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    pool=Depends(get_pool),
) -> dict:
    """FastAPI dependency. Returns {user_id: UUID, email: str} or raises 401."""
    try:
        user_id = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = await pool.fetchrow(
        "SELECT user_id, email FROM users WHERE user_id = $1::uuid",
        user_id,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return dict(user)
