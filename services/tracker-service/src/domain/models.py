import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    FAILED_QUOTA = "failed_quota"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass
class Workspace:
    id: int | None
    name: str
    description: str | None
    owner_id: int
    plan: str = "free"
    created_at: datetime | None = None


@dataclass
class Project:
    id: int | None
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus = ProjectStatus.PENDING
    owner_id: int = 0
    created_at: datetime | None = None


@dataclass
class Sprint:
    id: int | None
    project_id: int
    name: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    is_active: bool = False


@dataclass
class Task:
    id: int | None
    project_id: int
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: int | None = None
    reporter_id: int | None = None
    sprint_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Comment:
    id: int | None
    task_id: int
    author_id: int
    content: str
    created_at: datetime | None = None


@dataclass
class Worklog:
    id: int | None
    task_id: int
    user_id: int
    time_spent_minutes: int
    description: str | None = None
    logged_at: datetime | None = None


@dataclass
class Tag:
    id: int | None
    name: str
    color: str = "#3b82f6"


@dataclass
class OutboxMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    error_message: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None
