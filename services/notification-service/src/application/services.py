import logging
from typing import Any

from notification_service.application.dtos import EventLogResponse, NotificationResponse
from notification_service.domain.models import (
    EventLog,
    InboxMessage,
    Notification,
    NotificationChannel,
)
from notification_service.infrastructure.repositories import (
    SqlAlchemyEventLogRepository,
    SqlAlchemyInboxRepository,
    SqlAlchemyNotificationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NotificationApplicationService:
    def __init__(
        self,
        notification_repo: SqlAlchemyNotificationRepository,
        event_log_repo: SqlAlchemyEventLogRepository,
        inbox_repo: SqlAlchemyInboxRepository,
        session: AsyncSession | None = None,
    ):
        self.notification_repo = notification_repo
        self.event_log_repo = event_log_repo
        self.inbox_repo = inbox_repo
        self.session = session

    async def process_incoming_event(
        self, message_id: str, event_type: str, payload: dict[str, Any]
    ) -> bool:
        # Transaction Inbox pattern: Check for duplicate message (Idempotency)
        if await self.inbox_repo.exists(message_id):
            logger.info(
                f"Inbox pattern: Duplicate message {message_id} ignored (already processed)"
            )
            return False

        auto_commit = self.session is None

        # Mark as received in Inbox (participates in transaction)
        await self.inbox_repo.create(
            InboxMessage(message_id=message_id, event_type=event_type),
            auto_commit=auto_commit,
        )

        # Log event for auditing
        aggregate_type = event_type.split(".")[0] if "." in event_type else "unknown"
        aggregate_id = str(payload.get(f"{aggregate_type}_id", "0"))
        await self.event_log_repo.create(
            EventLog(
                id=None,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
            ),
            auto_commit=auto_commit,
        )

        # Business logic: generate notifications based on event type
        if event_type == "task.created":
            assignee_id = payload.get("assignee_id")
            if assignee_id:
                await self.notification_repo.create(
                    Notification(
                        id=None,
                        user_id=int(assignee_id),
                        title=f"New Task Assigned: {payload.get('title', 'Untitled')}",
                        message=f"Task #{payload.get('task_id')} has been assigned to you with priority {payload.get('priority')}",
                        channel=NotificationChannel.IN_APP,
                    ),
                    auto_commit=auto_commit,
                )
        elif event_type == "task.updated":
            assignee_id = payload.get("assignee_id")
            if assignee_id:
                await self.notification_repo.create(
                    Notification(
                        id=None,
                        user_id=int(assignee_id),
                        title=f"Task Updated: {payload.get('title', 'Untitled')}",
                        message=f"Task #{payload.get('task_id')} status changed to {payload.get('status')}",
                        channel=NotificationChannel.IN_APP,
                    ),
                    auto_commit=auto_commit,
                )
        elif event_type == "project.created":
            owner_id = payload.get("owner_id")
            if owner_id:
                await self.notification_repo.create(
                    Notification(
                        id=None,
                        user_id=int(owner_id),
                        title=f"Project Activated: {payload.get('name', 'Untitled')}",
                        message=f"Your project #{payload.get('project_id')} is now ACTIVE via Saga workflow",
                        channel=NotificationChannel.IN_APP,
                    ),
                    auto_commit=auto_commit,
                )

        if self.session is not None:
            await self.session.commit()

        logger.info(
            f"Successfully processed event '{event_type}' [id={message_id}]"
        )
        return True

    async def get_user_notifications(
        self, user_id: int, unread_only: bool = False
    ) -> list[NotificationResponse]:
        items = await self.notification_repo.list_by_user(user_id, unread_only)
        return [
            NotificationResponse(
                id=n.id,
                user_id=n.user_id,
                title=n.title,
                message=n.message,
                channel=n.channel,
                is_read=n.is_read,
                created_at=n.created_at,
            )
            for n in items
        ]

    async def mark_read(self, notification_id: int, user_id: int) -> bool:
        return await self.notification_repo.mark_as_read(notification_id, user_id)

    async def get_recent_event_logs(self, limit: int = 50) -> list[EventLogResponse]:
        items = await self.event_log_repo.list_recent(limit)
        return [
            EventLogResponse(
                id=item.id,
                aggregate_type=item.aggregate_type,
                aggregate_id=item.aggregate_id,
                event_type=item.event_type,
                payload=item.payload,
                occurred_at=item.occurred_at,
            )
            for item in items
        ]
