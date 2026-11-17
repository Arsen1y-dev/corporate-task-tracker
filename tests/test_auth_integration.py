import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "auth-service"))

from auth_service.infrastructure.database import Base, get_db_session
from auth_service.infrastructure.redis_cache import blacklist_service
from auth_service.main import app


@pytest.fixture
async def auth_test_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    # Mock redis blacklist in test with async functions
    async def mock_is_blacklisted(t):
        return False

    async def mock_add_to_blacklist(t, expire_seconds=3600):
        return None

    blacklist_service.is_blacklisted = mock_is_blacklisted
    blacklist_service.add_to_blacklist = mock_add_to_blacklist

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_auth_full_flow(auth_test_client: AsyncClient):
    # 1. Health check
    res = await auth_test_client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 2. Register new user
    reg_payload = {
        "username": "ivan_dev",
        "email": "ivan@example.com",
        "password": "Password123!",
        "role": "developer",
        "max_projects": 5,
    }
    reg_res = await auth_test_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    data = reg_res.json()
    assert data["username"] == "ivan_dev"
    assert data["email"] == "ivan@example.com"
    user_id = data["id"]

    # 3. Duplicate registration should return 409
    dup_res = await auth_test_client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409

    # 4. Login with valid credentials
    login_res = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"username": "ivan_dev", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    # 5. Get current user profile with token
    headers = {"Authorization": f"Bearer {token}"}
    me_res = await auth_test_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["id"] == user_id
    assert me_res.json()["username"] == "ivan_dev"

    # 6. Refresh token
    ref_res = await auth_test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_res.status_code == 200
    new_token_data = ref_res.json()
    assert "access_token" in new_token_data

    # 7. Logout
    logout_res = await auth_test_client.post(
        "/api/v1/auth/logout",
        headers=headers,
        json={"refresh_token": new_token_data["refresh_token"]},
    )
    assert logout_res.status_code == 200
