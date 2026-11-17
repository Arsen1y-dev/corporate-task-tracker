# Import tracker-service modules
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "tracker-service"))

from tracker_service.application.dtos import ProjectSagaCreateRequest, TaskCreate
from tracker_service.application.saga import ProjectCreationSaga
from tracker_service.application.services import TaskApplicationService
from tracker_service.domain.models import OutboxStatus, ProjectStatus, TaskPriority, TaskStatus
from tracker_service.infrastructure.database import Base
from tracker_service.infrastructure.grpc_client import AuthGrpcClient
from tracker_service.infrastructure.redis_cache import RedisCacheService
from tracker_service.infrastructure.repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyTaskRepository,
)


@pytest.mark.asyncio
async def test_saga_orchestrator_success():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        project_repo = SqlAlchemyProjectRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)

        # Mock gRPC client (quota allowed)
        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        grpc_mock.check_project_quota.return_value = (True, "Quota ok", 5)

        # Mock Redis cache
        cache_mock = AsyncMock(spec=RedisCacheService)

        saga = ProjectCreationSaga(project_repo, outbox_repo, grpc_mock, cache_mock)
        req = ProjectSagaCreateRequest(
            workspace_id=1,
            name="Alpha Project",
            description="Core trading system",
            simulate_quota_exceeded=False,
        )

        res = await saga.execute(req, owner_id=10)
        assert res.saga_status == "COMPLETED"
        assert res.compensation_triggered is False
        assert res.project.status == ProjectStatus.ACTIVE
        assert res.project.name == "Alpha Project"

        # Verify Outbox message was generated in the same transaction
        pending = await outbox_repo.get_pending()
        assert len(pending) == 1
        assert pending[0].event_type == "project.created"
        assert pending[0].payload["project_id"] == res.project.id
        assert pending[0].status == OutboxStatus.PENDING

    await engine.dispose()


@pytest.mark.asyncio
async def test_saga_orchestrator_compensation_on_quota_failure():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        project_repo = SqlAlchemyProjectRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)

        # Mock gRPC client rejecting quota
        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        grpc_mock.check_project_quota.return_value = (
            False,
            "User reached maximum allowed projects (5)",
            5,
        )
        cache_mock = AsyncMock(spec=RedisCacheService)

        saga = ProjectCreationSaga(project_repo, outbox_repo, grpc_mock, cache_mock)
        req = ProjectSagaCreateRequest(
            workspace_id=1,
            name="Excess Project",
            simulate_quota_exceeded=False,
        )

        res = await saga.execute(req, owner_id=10)
        # Verify compensation was executed!
        assert res.saga_status == "COMPENSATED"
        assert res.compensation_triggered is True
        assert res.project.status == ProjectStatus.FAILED_QUOTA

        # Verify NO success outbox message was created
        pending = await outbox_repo.get_pending()
        assert len(pending) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_task_creation_with_outbox():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        task_repo = SqlAlchemyTaskRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)
        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        grpc_mock.check_user_exists.return_value = (True, {"user_id": 99})
        cache_mock = AsyncMock(spec=RedisCacheService)

        service = TaskApplicationService(
            task_repo, outbox_repo, grpc_mock, cache_mock
        )
        req = TaskCreate(
            project_id=1,
            title="Implement gRPC endpoints",
            description="High priority requirement",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee_id=99,
        )

        task_res = await service.create_task(req, reporter_id=1)
        assert task_res.id is not None
        assert task_res.title == "Implement gRPC endpoints"

        # Check outbox
        pending = await outbox_repo.get_pending()
        assert len(pending) == 1
        assert pending[0].event_type == "task.created"
        assert pending[0].payload["task_id"] == task_res.id

    await engine.dispose()
