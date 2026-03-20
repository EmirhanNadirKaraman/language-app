from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_pool
from ..models.schemas import LoginRequest, RegisterRequest, TokenResponse, UserRead
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, pool=Depends(get_pool)):
    try:
        user = await auth_service.register_user(pool, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UserRead(user_id=user["user_id"], email=user["email"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, pool=Depends(get_pool)):
    try:
        token = await auth_service.login_user(pool, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(access_token=token)
