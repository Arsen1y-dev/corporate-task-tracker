import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure services are in python path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root / "services" / "auth-service"))
sys.path.insert(0, str(root / "services" / "tracker-service"))
sys.path.insert(0, str(root / "services" / "notification-service"))
sys.path.insert(0, str(root / "proto" / "generated"))


@pytest.fixture
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session, engine
    await engine.dispose()
