from datetime import timedelta

import jwt
import pytest
from auth_service.application.dtos import UserLoginRequest, UserRegisterRequest
from auth_service.application.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from auth_service.application.services import AuthApplicationService
from auth_service.domain.models import Role
from auth_service.infrastructure.database import Base
from auth_service.infrastructure.redis_cache import RedisBlacklistService
from auth_service.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyUserRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def test_password_hashing():
    pw = "SuperSecret123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_generation_and_decoding():
    token = create_access_token(user_id=42, username="john_doe", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["username"] == "john_doe"
    assert payload["role"] == "admin"


def test_jwt_expiration():
    token = create_access_token(
        user_id=1, username="test", role="guest", expires_delta=timedelta(seconds=-10)
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


@pytest.mark.asyncio
async def test_auth_service_register_and_login():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        user_repo = SqlAlchemyUserRepository(session)
        token_repo = SqlAlchemyRefreshTokenRepository(session)
        mock_blacklist = RedisBlacklistService(None)
        # Mock blacklist methods for unit test
        async def mock_is_blacklisted(t):
            return False

        async def mock_add_to_blacklist(t, exp):
            return None

        mock_blacklist.is_blacklisted = mock_is_blacklisted
        mock_blacklist.add_to_blacklist = mock_add_to_blacklist

        service = AuthApplicationService(user_repo, token_repo, mock_blacklist)

        # 1. Register
        reg_req = UserRegisterRequest(
            username="alex",
            email="alex@company.com",
            password="securePassword456",
            role=Role.DEVELOPER,
            max_projects=3,
        )
        user_res = await service.register(reg_req)
        assert user_res.id is not None
        assert user_res.username == "alex"
        assert user_res.max_projects == 3

        # 2. Login
        login_req = UserLoginRequest(username="alex", password="securePassword456")
        token_res = await service.login(login_req)
        assert token_res.access_token is not None
        assert token_res.refresh_token is not None

        # 3. Verify access token payload
        payload = decode_access_token(token_res.access_token)
        assert payload["username"] == "alex"
        assert payload["role"] == "developer"

    await engine.dispose()
