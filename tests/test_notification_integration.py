import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "notification-service"))

from notification_service.application.services import NotificationApplicationService
from notification_service.infrastructure.database import Base, get_db_session
from notification_service.infrastructure.repositories import (
    SqlAlchemyEventLogRepository,
    SqlAlchemyInboxRepository,
    SqlAlchemyNotificationRepository,
)
from notification_service.main import app
from notification_service.presentation.dependencies import get_current_user


@pytest.fixture
async def notif_test_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    async def override_get_current_user():
        return {"id": 10, "username": "developer_10", "role": "developer"}

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Populate an event directly through the service to simulate message arrival
    async with session_maker() as session:
        service = NotificationApplicationService(
            notification_repo=SqlAlchemyNotificationRepository(session),
            event_log_repo=SqlAlchemyEventLogRepository(session),
            inbox_repo=SqlAlchemyInboxRepository(session),
        )
        await service.process_incoming_event(
            message_id="integration-msg-1",
            event_type="task.created",
            payload={
                "task_id": 55,
                "title": "Set up CI/CD pipeline",
                "priority": "high",
                "assignee_id": 10,
            },
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_notifications_api(notif_test_client: AsyncClient):
    # 1. Health check
    h = await notif_test_client.get("/health")
    assert h.status_code == 200

    # 2. Get notifications for current user (id=10)
    res = await notif_test_client.get("/api/v1/notifications")
    assert res.status_code == 200
    notifications = res.json()
    assert len(notifications) == 1
    assert "Set up CI/CD pipeline" in notifications[0]["title"]
    assert notifications[0]["is_read"] is False
    notif_id = notifications[0]["id"]

    # 3. Mark notification as read
    read_res = await notif_test_client.patch(
        f"/api/v1/notifications/{notif_id}/read"
    )
    assert read_res.status_code == 200

    # 4. Get unread only -> should be empty now
    unread_res = await notif_test_client.get("/api/v1/notifications?unread_only=true")
    assert unread_res.status_code == 200
    assert len(unread_res.json()) == 0

    # 5. List event logs
    logs_res = await notif_test_client.get("/api/v1/event-logs")
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) >= 1
    assert logs[0]["event_type"] == "task.created"
