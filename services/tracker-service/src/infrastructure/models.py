import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from tracker_service.domain.models import (
    Comment,
    OutboxMessage,
    OutboxStatus,
    Project,
    ProjectStatus,
    Sprint,
    Tag,
    Task,
    TaskPriority,
    TaskStatus,
    Worklog,
    Workspace,
)
from tracker_service.infrastructure.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceModel(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def to_domain(self) -> Workspace:
        return Workspace(
            id=self.id,
            name=self.name,
            description=self.description,
            owner_id=self.owner_id,
            plan=self.plan,
            created_at=self.created_at,
        )


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=ProjectStatus.PENDING.value, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def to_domain(self) -> Project:
        return Project(
            id=self.id,
            workspace_id=self.workspace_id,
            name=self.name,
            description=self.description,
            status=ProjectStatus(self.status),
            owner_id=self.owner_id,
            created_at=self.created_at,
        )


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=TaskStatus.TODO.value, nullable=False)
    priority: Mapped[str] = mapped_column(String(50), default=TaskPriority.MEDIUM.value, nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reporter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sprint_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    def to_domain(self) -> Task:
        return Task(
            id=self.id,
            project_id=self.project_id,
            title=self.title,
            description=self.description,
            status=TaskStatus(self.status),
            priority=TaskPriority(self.priority),
            assignee_id=self.assignee_id,
            reporter_id=self.reporter_id,
            sprint_id=self.sprint_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class SprintModel(Base):
    __tablename__ = "sprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def to_domain(self) -> Sprint:
        return Sprint(
            id=self.id,
            project_id=self.project_id,
            name=self.name,
            start_date=self.start_date,
            end_date=self.end_date,
            is_active=self.is_active,
        )


class CommentModel(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def to_domain(self) -> Comment:
        return Comment(
            id=self.id,
            task_id=self.task_id,
            author_id=self.author_id,
            content=self.content,
            created_at=self.created_at,
        )


class WorklogModel(Base):
    __tablename__ = "worklogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    time_spent_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    def to_domain(self) -> Worklog:
        return Worklog(
            id=self.id,
            task_id=self.task_id,
            user_id=self.user_id,
            time_spent_minutes=self.time_spent_minutes,
            description=self.description,
            logged_at=self.logged_at,
        )


class TagModel(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#3b82f6", nullable=False)

    def to_domain(self) -> Tag:
        return Tag(id=self.id, name=self.name, color=self.color)


class OutboxMessageModel(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=OutboxStatus.PENDING.value, index=True, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_domain(self) -> OutboxMessage:
        return OutboxMessage(
            id=self.id,
            event_type=self.event_type,
            payload=self.payload,
            status=OutboxStatus(self.status),
            error_message=self.error_message,
            created_at=self.created_at,
            processed_at=self.processed_at,
        )
