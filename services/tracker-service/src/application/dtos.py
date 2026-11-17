from datetime import datetime

from pydantic import BaseModel, Field
from tracker_service.domain.models import ProjectStatus, TaskPriority, TaskStatus


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    plan: str = "free"


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    plan: str
    created_at: datetime | None


class ProjectCreate(BaseModel):
    workspace_id: int
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None


class ProjectSagaCreateRequest(BaseModel):
    workspace_id: int
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    simulate_quota_exceeded: bool = False


class ProjectResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus
    owner_id: int
    created_at: datetime | None


class ProjectSagaResponse(BaseModel):
    project: ProjectResponse
    saga_status: str
    quota_checked: bool
    compensation_triggered: bool
    message: str


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(..., min_length=2, max_length=200)
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: int | None = None
    sprint_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    sprint_id: int | None = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee_id: int | None
    reporter_id: int | None
    sprint_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


class SprintCreate(BaseModel):
    project_id: int
    name: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class SprintResponse(BaseModel):
    id: int
    project_id: int
    name: str
    start_date: datetime | None
    end_date: datetime | None
    is_active: bool


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1)


class CommentResponse(BaseModel):
    id: int
    task_id: int
    author_id: int
    content: str
    created_at: datetime | None


class WorklogCreate(BaseModel):
    time_spent_minutes: int = Field(..., gt=0)
    description: str | None = None


class WorklogResponse(BaseModel):
    id: int
    task_id: int
    user_id: int
    time_spent_minutes: int
    description: str | None
    logged_at: datetime | None


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("#3b82f6", max_length=20)


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
