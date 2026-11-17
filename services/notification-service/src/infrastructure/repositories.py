from notification_service.domain.models import EventLog, InboxMessage, Notification
from notification_service.infrastructure.models import (
    EventLogModel,
    InboxMessageModel,
    NotificationModel,
)
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, notification: Notification, auto_commit: bool = True) -> Notification:
        model = NotificationModel(
            user_id=notification.user_id,
            title=notification.title,
            message=notification.message,
            channel=notification.channel.value,
            is_read=notification.is_read,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(model)
        else:
            await self.session.flush()
        return model.to_domain()

    async def list_by_user(
        self, user_id: int, unread_only: bool = False
    ) -> list[Notification]:
        query = select(NotificationModel).where(NotificationModel.user_id == user_id)
        if unread_only:
            query = query.where(NotificationModel.is_read.is_(False))
        query = query.order_by(desc(NotificationModel.created_at))
        result = await self.session.execute(query)
        return [m.to_domain() for m in result.scalars().all()]

    async def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
            )
            .values(is_read=True)
        )
        await self.session.commit()
        return result.rowcount > 0


class SqlAlchemyEventLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, log: EventLog, auto_commit: bool = True) -> EventLog:
        model = EventLogModel(
            aggregate_type=log.aggregate_type,
            aggregate_id=log.aggregate_id,
            event_type=log.event_type,
            payload=log.payload,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(model)
        else:
            await self.session.flush()
        return model.to_domain()

    async def list_recent(self, limit: int = 50) -> list[EventLog]:
        result = await self.session.execute(
            select(EventLogModel)
            .order_by(desc(EventLogModel.occurred_at))
            .limit(limit)
        )
        return [m.to_domain() for m in result.scalars().all()]


class SqlAlchemyInboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def exists(self, message_id: str) -> bool:
        result = await self.session.execute(
            select(InboxMessageModel).where(
                InboxMessageModel.message_id == message_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def create(self, message: InboxMessage, auto_commit: bool = True) -> InboxMessage:
        model = InboxMessageModel(
            message_id=message.message_id,
            event_type=message.event_type,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return model.to_domain()
