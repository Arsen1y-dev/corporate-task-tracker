from datetime import datetime
from typing import Any

from notification_service.domain.models import NotificationChannel
from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    channel: NotificationChannel
    is_read: bool
    created_at: datetime | None


class EventLogResponse(BaseModel):
    id: int
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime | None
