# Import notification-service modules
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "notification-service"))

from notification_service.application.services import NotificationApplicationService
from notification_service.infrastructure.database import Base
from notification_service.infrastructure.repositories import (
    SqlAlchemyEventLogRepository,
    SqlAlchemyInboxRepository,
    SqlAlchemyNotificationRepository,
)


@pytest.mark.asyncio
async def test_inbox_pattern_idempotency():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        notif_repo = SqlAlchemyNotificationRepository(session)
        log_repo = SqlAlchemyEventLogRepository(session)
        inbox_repo = SqlAlchemyInboxRepository(session)

        service = NotificationApplicationService(notif_repo, log_repo, inbox_repo)

        msg_id = "msg-uuid-12345"
        payload = {
            "task_id": 77,
            "title": "Fix critical bug in payment module",
            "priority": "urgent",
            "assignee_id": 101,
        }

        # First delivery
        first_result = await service.process_incoming_event(
            message_id=msg_id,
            event_type="task.created",
            payload=payload,
        )
        assert first_result is True

        # Check notifications created
        notifications = await service.get_user_notifications(user_id=101)
        assert len(notifications) == 1
        assert "Fix critical bug" in notifications[0].title

        # Check audit log created
        logs = await service.get_recent_event_logs()
        assert len(logs) == 1
        assert logs[0].event_type == "task.created"

        # Duplicate delivery of identical message
        second_result = await service.process_incoming_event(
            message_id=msg_id,
            event_type="task.created",
            payload=payload,
        )
        assert second_result is False  # Idempotent skip!

        # Notifications count MUST NOT increase
        notifications_after = await service.get_user_notifications(user_id=101)
        assert len(notifications_after) == 1

    await engine.dispose()
