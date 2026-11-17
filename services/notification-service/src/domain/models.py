from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class NotificationChannel(str, Enum):
    EMAIL = "email"
    IN_APP = "in_app"
    SLACK = "slack"


@dataclass
class Notification:
    id: int | None
    user_id: int
    title: str
    message: str
    channel: NotificationChannel = NotificationChannel.IN_APP
    is_read: bool = False
    created_at: datetime | None = None


@dataclass
class EventLog:
    id: int | None
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime | None = None


@dataclass
class InboxMessage:
    message_id: str
    event_type: str
    processed_at: datetime | None = None
