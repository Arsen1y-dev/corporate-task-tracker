from auth_service.application.dtos import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from auth_service.application.security import decode_access_token
from auth_service.application.services import AuthApplicationService
from auth_service.domain.models import User
from auth_service.infrastructure.database import get_db_session
from auth_service.infrastructure.redis_cache import blacklist_service
from auth_service.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyUserRepository,
)
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuthApplicationService:
    user_repo = SqlAlchemyUserRepository(session)
    token_repo = SqlAlchemyRefreshTokenRepository(session)
    return AuthApplicationService(user_repo, token_repo, blacklist_service)


async def get_current_user(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid",
        )
    token = authorization.split(" ", 1)[1]
    if await blacklist_service.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_repo = SqlAlchemyUserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: UserRegisterRequest,
    auth_service: AuthApplicationService = Depends(get_auth_service),
):
    return await auth_service.register(req)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: UserLoginRequest,
    auth_service: AuthApplicationService = Depends(get_auth_service),
):
    return await auth_service.login(req)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    req: RefreshTokenRequest,
    auth_service: AuthApplicationService = Depends(get_auth_service),
):
    return await auth_service.refresh(req)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    req: LogoutRequest,
    authorization: str | None = Header(None),
    auth_service: AuthApplicationService = Depends(get_auth_service),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    token = authorization.split(" ", 1)[1]
    await auth_service.logout(token, req.refresh_token)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        max_projects=current_user.max_projects,
        created_at=current_user.created_at,
    )
