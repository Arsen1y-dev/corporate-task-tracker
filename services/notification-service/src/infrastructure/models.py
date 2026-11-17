from datetime import datetime, timezone

from notification_service.domain.models import (
    EventLog,
    InboxMessage,
    Notification,
    NotificationChannel,
)
from notification_service.infrastructure.database import Base
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(
        String(50), default=NotificationChannel.IN_APP.value, nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    def to_domain(self) -> Notification:
        return Notification(
            id=self.id,
            user_id=self.user_id,
            title=self.title,
            message=self.message,
            channel=NotificationChannel(self.channel),
            is_read=self.is_read,
            created_at=self.created_at,
        )


class EventLogModel(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    def to_domain(self) -> EventLog:
        return EventLog(
            id=self.id,
            aggregate_type=self.aggregate_type,
            aggregate_id=self.aggregate_id,
            event_type=self.event_type,
            payload=self.payload,
            occurred_at=self.occurred_at,
        )


class InboxMessageModel(Base):
    __tablename__ = "inbox_messages"

    message_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    def to_domain(self) -> InboxMessage:
        return InboxMessage(
            message_id=self.message_id,
            event_type=self.event_type,
            processed_at=self.processed_at,
        )
