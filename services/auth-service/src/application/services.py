import secrets
from datetime import datetime, timedelta, timezone

from auth_service.application.dtos import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from auth_service.application.security import (
    create_access_token,
    hash_password,
    hash_token,
    verify_password,
)
from auth_service.config import settings
from auth_service.domain.models import RefreshToken, User
from auth_service.domain.repositories import RefreshTokenRepository, UserRepository
from auth_service.infrastructure.redis_cache import RedisBlacklistService
from fastapi import HTTPException, status


class AuthApplicationService:
    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: RefreshTokenRepository,
        blacklist_service: RedisBlacklistService,
    ):
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.blacklist_service = blacklist_service

    async def register(self, req: UserRegisterRequest) -> UserResponse:
        existing_user = await self.user_repo.get_by_username(req.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already registered",
            )
        existing_email = await self.user_repo.get_by_email(req.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        hashed = hash_password(req.password)
        new_user = User(
            id=None,
            username=req.username,
            email=req.email,
            hashed_password=hashed,
            role=req.role,
            max_projects=req.max_projects,
        )
        saved = await self.user_repo.create(new_user)
        return UserResponse(
            id=saved.id,
            username=saved.username,
            email=saved.email,
            role=saved.role,
            is_active=saved.is_active,
            max_projects=saved.max_projects,
            created_at=saved.created_at,
        )

    async def login(self, req: UserLoginRequest) -> TokenResponse:
        user = await self.user_repo.get_by_username(req.username)
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )

        raw_refresh = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_refresh)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        await self.token_repo.create(
            RefreshToken(
                id=None,
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                revoked=False,
            )
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, req: RefreshTokenRequest) -> TokenResponse:
        token_hash = hash_token(req.refresh_token)
        stored = await self.token_repo.get_by_hash(token_hash)
        if not stored or stored.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token",
            )
        # Check expiration
        now = datetime.now(timezone.utc)
        stored_exp = stored.expires_at
        if stored_exp.tzinfo is None:
            stored_exp = stored_exp.replace(tzinfo=timezone.utc)
        if stored_exp < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        user = await self.user_repo.get_by_id(stored.user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Rotate refresh token
        await self.token_repo.revoke(token_hash)
        raw_refresh = secrets.token_urlsafe(32)
        new_hash = hash_token(raw_refresh)
        expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.token_repo.create(
            RefreshToken(
                id=None,
                user_id=user.id,
                token_hash=new_hash,
                expires_at=expires_at,
                revoked=False,
            )
        )

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(self, access_token: str, refresh_token: str | None) -> None:
        if refresh_token:
            await self.token_repo.revoke(hash_token(refresh_token))
        await self.blacklist_service.add_to_blacklist(
            access_token, expire_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
