from datetime import datetime, timedelta, timezone

import pytest
from auth_service.application.dtos import (
    RefreshTokenRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from auth_service.application.services import AuthApplicationService
from auth_service.domain.models import RefreshToken, Role
from auth_service.infrastructure.database import Base as AuthBase
from auth_service.infrastructure.redis_cache import RedisBlacklistService
from auth_service.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyUserRepository,
)
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tracker_service.application.dtos import TaskCreate
from tracker_service.application.services import TaskApplicationService
from tracker_service.domain.models import TaskPriority, TaskStatus
from tracker_service.infrastructure.database import Base as TrackerBase
from tracker_service.infrastructure.grpc_client import AuthGrpcClient
from tracker_service.infrastructure.redis_cache import RedisCacheService
from tracker_service.infrastructure.repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemyTaskRepository,
)


@pytest.mark.asyncio
async def test_auth_edge_case_invalid_credentials_and_expired_refresh():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        user_repo = SqlAlchemyUserRepository(session)
        token_repo = SqlAlchemyRefreshTokenRepository(session)
        mock_blacklist = RedisBlacklistService(None)
        mock_blacklist.is_blacklisted = lambda t: False
        service = AuthApplicationService(user_repo, token_repo, mock_blacklist)

        # 1. Login non-existent user raises 401
        with pytest.raises(HTTPException) as exc_info:
            await service.login(
                UserLoginRequest(username="ghost_user", password="123")
            )
        assert exc_info.value.status_code == 401
        assert "Invalid username or password" in exc_info.value.detail

        # 2. Register user
        reg_res = await service.register(
            UserRegisterRequest(
                username="edge_user",
                email="edge@domain.com",
                password="CorrectPassword123!",
                role=Role.GUEST,
            )
        )
        assert reg_res.role == Role.GUEST

        # 3. Wrong password raises 401
        with pytest.raises(HTTPException) as exc_info:
            await service.login(
                UserLoginRequest(username="edge_user", password="WrongPassword!")
            )
        assert exc_info.value.status_code == 401

        # 4. Refresh token invalid hash raises 401
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh(RefreshTokenRequest(refresh_token="invalid-token"))
        assert exc_info.value.status_code == 401

        # 5. Expired refresh token raises 401
        from auth_service.application.security import hash_token

        expired_raw = "expired-token-raw"
        expired_hash = hash_token(expired_raw)
        await token_repo.create(
            RefreshToken(
                id=None,
                user_id=reg_res.id,
                token_hash=expired_hash,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                revoked=False,
            )
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh(RefreshTokenRequest(refresh_token=expired_raw))
        assert exc_info.value.status_code == 401
        assert "Refresh token expired" in exc_info.value.detail

    await engine.dispose()


@pytest.mark.asyncio
async def test_task_creation_edge_case_assignee_not_found_grpc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TrackerBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        task_repo = SqlAlchemyTaskRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)

        # Mock gRPC client returning exists=False
        from unittest.mock import AsyncMock

        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        grpc_mock.check_user_exists.return_value = (False, {})
        cache_mock = AsyncMock(spec=RedisCacheService)

        service = TaskApplicationService(
            task_repo, outbox_repo, grpc_mock, cache_mock
        )
        req = TaskCreate(
            project_id=1,
            title="Task with phantom user",
            status=TaskStatus.TODO,
            priority=TaskPriority.LOW,
            assignee_id=99999,
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.create_task(req, reporter_id=1)
        assert exc_info.value.status_code == 400
        assert "does not exist in Auth Service" in exc_info.value.detail

        # Ensure no task or outbox message was created
        pending = await outbox_repo.get_pending()
        assert len(pending) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_password_max_length_and_safe_truncation():
    from auth_service.application.security import hash_password, verify_password
    from pydantic import ValidationError

    # 1. Pydantic validates password length <= 72
    long_pw = "P" * 75
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            username="long_pw_user",
            email="long@domain.com",
            password=long_pw,
        )

    # 2. Hashing safely handles > 72 bytes without throwing ValueError
    hashed = hash_password(long_pw)
    assert verify_password(long_pw, hashed) is True
    assert verify_password("short", hashed) is False


@pytest.mark.asyncio
async def test_task_creation_rejects_non_existent_project():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TrackerBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        from unittest.mock import AsyncMock

        from tracker_service.infrastructure.repositories import SqlAlchemyProjectRepository

        task_repo = SqlAlchemyTaskRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)
        project_repo = SqlAlchemyProjectRepository(session)
        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        cache_mock = AsyncMock(spec=RedisCacheService)

        service = TaskApplicationService(
            task_repo=task_repo,
            outbox_repo=outbox_repo,
            grpc_client=grpc_mock,
            cache_service=cache_mock,
            project_repo=project_repo,
            session=session,
        )

        # Attempt to create task in non-existent project 99999
        req = TaskCreate(
            project_id=99999,
            title="Ghost Project Task",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.create_task(req, reporter_id=1)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    await engine.dispose()


@pytest.mark.asyncio
async def test_saga_rejects_non_existent_workspace():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TrackerBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        from unittest.mock import AsyncMock

        from tracker_service.application.dtos import ProjectSagaCreateRequest
        from tracker_service.application.saga import ProjectCreationSaga
        from tracker_service.infrastructure.repositories import (
            SqlAlchemyProjectRepository,
            SqlAlchemyWorkspaceRepository,
        )

        project_repo = SqlAlchemyProjectRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)
        workspace_repo = SqlAlchemyWorkspaceRepository(session)
        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        cache_mock = AsyncMock(spec=RedisCacheService)

        saga = ProjectCreationSaga(
            project_repo=project_repo,
            outbox_repo=outbox_repo,
            grpc_client=grpc_mock,
            cache_service=cache_mock,
            workspace_repo=workspace_repo,
            session=session,
        )

        req = ProjectSagaCreateRequest(
            workspace_id=88888,
            name="Ghost Workspace Project",
        )
        with pytest.raises(HTTPException) as exc_info:
            await saga.execute(req, owner_id=1)
        assert exc_info.value.status_code == 404
        assert "workspace id 88888 not found" in exc_info.value.detail.lower()

    await engine.dispose()


@pytest.mark.asyncio
async def test_tag_repository_crud():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TrackerBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        from tracker_service.domain.models import Tag
        from tracker_service.infrastructure.repositories import SqlAlchemyTagRepository

        tag_repo = SqlAlchemyTagRepository(session)

        # 1. Create Tag
        tag = await tag_repo.create(Tag(id=None, name="backend", color="#10b981"))
        assert tag.id is not None
        assert tag.name == "backend"

        # 2. Get by ID
        fetched = await tag_repo.get_by_id(tag.id)
        assert fetched is not None
        assert fetched.name == "backend"

        # 3. List all
        await tag_repo.create(Tag(id=None, name="frontend", color="#6366f1"))
        all_tags = await tag_repo.list_all()
        assert len(all_tags) == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_active_only_quota_count():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TrackerBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        from tracker_service.domain.models import Project, ProjectStatus
        from tracker_service.infrastructure.repositories import SqlAlchemyProjectRepository

        project_repo = SqlAlchemyProjectRepository(session)

        # Create 1 ACTIVE project
        await project_repo.create(
            Project(id=None, workspace_id=1, name="Active 1", description="", status=ProjectStatus.ACTIVE, owner_id=5)
        )
        # Create 2 FAILED_QUOTA projects (compensated)
        await project_repo.create(
            Project(id=None, workspace_id=1, name="Failed 1", description="", status=ProjectStatus.FAILED_QUOTA, owner_id=5)
        )
        await project_repo.create(
            Project(id=None, workspace_id=1, name="Failed 2", description="", status=ProjectStatus.FAILED_QUOTA, owner_id=5)
        )
        # Create 1 ARCHIVED project
        await project_repo.create(
            Project(id=None, workspace_id=1, name="Archived 1", description="", status=ProjectStatus.ARCHIVED, owner_id=5)
        )

        # Active-only count should be exactly 1!
        active_count = await project_repo.count_by_owner(5, active_only=True)
        assert active_count == 1

        # Total count without filter is 4
        total_count = await project_repo.count_by_owner(5, active_only=False)
        assert total_count == 4

    await engine.dispose()


@pytest.mark.asyncio
async def test_task_get_and_delete_with_outbox_event():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TrackerBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        from unittest.mock import AsyncMock

        from tracker_service.domain.models import Project, ProjectStatus
        from tracker_service.infrastructure.repositories import SqlAlchemyProjectRepository

        task_repo = SqlAlchemyTaskRepository(session)
        outbox_repo = SqlAlchemyOutboxRepository(session)
        project_repo = SqlAlchemyProjectRepository(session)
        grpc_mock = AsyncMock(spec=AuthGrpcClient)
        cache_mock = AsyncMock(spec=RedisCacheService)

        # Create parent project
        p = await project_repo.create(
            Project(id=None, workspace_id=1, name="P1", description="", status=ProjectStatus.ACTIVE, owner_id=1)
        )

        service = TaskApplicationService(
            task_repo=task_repo,
            outbox_repo=outbox_repo,
            grpc_client=grpc_mock,
            cache_service=cache_mock,
            project_repo=project_repo,
            session=session,
        )

        # Create task
        t = await service.create_task(
            TaskCreate(project_id=p.id, title="Deletable Task"),
            reporter_id=1,
        )
        assert t.id is not None

        # Get task by ID
        fetched = await service.get_task_by_id(t.id)
        assert fetched.id == t.id

        # Delete task
        await service.delete_task(t.id)

        # Verify task is deleted
        with pytest.raises(HTTPException) as exc_info:
            await service.get_task_by_id(t.id)
        assert exc_info.value.status_code == 404

        # Verify outbox event 'task.deleted' was recorded
        pending = await outbox_repo.get_pending()
        event_types = [msg.event_type for msg in pending]
        assert "task.deleted" in event_types

    await engine.dispose()


@pytest.mark.asyncio
async def test_atomic_inbox_transaction_rollback_on_failure():
    from notification_service.application.services import NotificationApplicationService
    from notification_service.infrastructure.database import Base as NotifBase
    from notification_service.infrastructure.repositories import (
        SqlAlchemyEventLogRepository,
        SqlAlchemyInboxRepository,
        SqlAlchemyNotificationRepository,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(NotifBase.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        notif_repo = SqlAlchemyNotificationRepository(session)
        log_repo = SqlAlchemyEventLogRepository(session)
        inbox_repo = SqlAlchemyInboxRepository(session)

        # Simulate failure during notification creation by making notif_repo.create throw
        async def mock_fail_create(*args, **kwargs):
            raise RuntimeError("Database constraint or transient connection failure!")

        notif_repo.create = mock_fail_create

        service = NotificationApplicationService(
            notification_repo=notif_repo,
            event_log_repo=log_repo,
            inbox_repo=inbox_repo,
            session=session,
        )

        msg_id = "failing-msg-999"
        payload = {"task_id": 1, "title": "Fail Task", "assignee_id": 10}

        with pytest.raises(RuntimeError):
            await service.process_incoming_event(
                message_id=msg_id,
                event_type="task.created",
                payload=payload,
            )

        await session.rollback()

        # Crucial check: InboxMessage MUST NOT be committed!
        # Next retry MUST see exists == False so it can be retried!
        exists = await inbox_repo.exists(msg_id)
        assert exists is False

    await engine.dispose()
