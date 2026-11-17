import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_service.application.dtos import (
    TagCreate,
    TagResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
)
from tracker_service.domain.models import (
    OutboxMessage,
    OutboxStatus,
    Tag,
    Task,
    Workspace,
)
from tracker_service.infrastructure.grpc_client import AuthGrpcClient
from tracker_service.infrastructure.redis_cache import RedisCacheService
from tracker_service.infrastructure.repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyWorkspaceRepository,
)

logger = logging.getLogger(__name__)


class WorkspaceApplicationService:
    def __init__(self, workspace_repo: SqlAlchemyWorkspaceRepository):
        self.workspace_repo = workspace_repo

    async def create_workspace(
        self, req: WorkspaceCreate, owner_id: int
    ) -> WorkspaceResponse:
        ws = Workspace(
            id=None,
            name=req.name,
            description=req.description,
            owner_id=owner_id,
            plan=req.plan,
        )
        saved = await self.workspace_repo.create(ws)
        return WorkspaceResponse(
            id=saved.id,
            name=saved.name,
            description=saved.description,
            owner_id=saved.owner_id,
            plan=saved.plan,
            created_at=saved.created_at,
        )

    async def list_user_workspaces(self, owner_id: int) -> list[WorkspaceResponse]:
        items = await self.workspace_repo.list_by_owner(owner_id)
        return [
            WorkspaceResponse(
                id=w.id,
                name=w.name,
                description=w.description,
                owner_id=w.owner_id,
                plan=w.plan,
                created_at=w.created_at,
            )
            for w in items
        ]


class TaskApplicationService:
    def __init__(
        self,
        task_repo: SqlAlchemyTaskRepository,
        outbox_repo: SqlAlchemyOutboxRepository,
        grpc_client: AuthGrpcClient,
        cache_service: RedisCacheService,
        project_repo: SqlAlchemyProjectRepository | None = None,
        session: AsyncSession | None = None,
    ):
        self.task_repo = task_repo
        self.outbox_repo = outbox_repo
        self.grpc_client = grpc_client
        self.cache_service = cache_service
        self.project_repo = project_repo
        self.session = session

    async def create_task(self, req: TaskCreate, reporter_id: int) -> TaskResponse:
        # Validation: Target project must exist
        if self.project_repo is not None:
            project = await self.project_repo.get_by_id(req.project_id)
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Project with ID {req.project_id} not found",
                )

        # Synchronous gRPC validation: Assignee user must exist in auth-service
        if req.assignee_id is not None:
            exists, user_info = await self.grpc_client.check_user_exists(
                req.assignee_id
            )
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Assignee user ID {req.assignee_id} does not exist in Auth Service",
                )

        new_task = Task(
            id=None,
            project_id=req.project_id,
            title=req.title,
            description=req.description,
            status=req.status,
            priority=req.priority,
            assignee_id=req.assignee_id,
            reporter_id=reporter_id,
            sprint_id=req.sprint_id,
        )

        # Transaction Outbox pattern: Write Task & Outbox atomically in the same transaction
        if self.session is not None:
            saved_task = await self.task_repo.create(new_task, auto_commit=False)
            outbox_msg = OutboxMessage(
                event_type="task.created",
                payload={
                    "task_id": saved_task.id,
                    "project_id": saved_task.project_id,
                    "title": saved_task.title,
                    "status": saved_task.status.value,
                    "priority": saved_task.priority.value,
                    "assignee_id": saved_task.assignee_id,
                    "reporter_id": saved_task.reporter_id,
                },
                status=OutboxStatus.PENDING,
            )
            await self.outbox_repo.create(outbox_msg, auto_commit=False)
            await self.session.commit()
        else:
            saved_task = await self.task_repo.create(new_task)
            outbox_msg = OutboxMessage(
                event_type="task.created",
                payload={
                    "task_id": saved_task.id,
                    "project_id": saved_task.project_id,
                    "title": saved_task.title,
                    "status": saved_task.status.value,
                    "priority": saved_task.priority.value,
                    "assignee_id": saved_task.assignee_id,
                    "reporter_id": saved_task.reporter_id,
                },
                status=OutboxStatus.PENDING,
            )
            await self.outbox_repo.create(outbox_msg)

        # Invalidate Redis cache for project tasks
        cache_key = f"cache:tasks:project:{req.project_id}"
        await self.cache_service.delete(cache_key)

        return TaskResponse(
            id=saved_task.id,
            project_id=saved_task.project_id,
            title=saved_task.title,
            description=saved_task.description,
            status=saved_task.status,
            priority=saved_task.priority,
            assignee_id=saved_task.assignee_id,
            reporter_id=saved_task.reporter_id,
            sprint_id=saved_task.sprint_id,
            created_at=saved_task.created_at,
            updated_at=saved_task.updated_at,
        )

    async def get_task_by_id(self, task_id: int) -> TaskResponse:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )
        return TaskResponse(
            id=task.id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            assignee_id=task.assignee_id,
            reporter_id=task.reporter_id,
            sprint_id=task.sprint_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    async def get_tasks_by_project(self, project_id: int) -> list[TaskResponse]:
        cache_key = f"cache:tasks:project:{project_id}"
        # Redis Caching: check cache hit
        cached_data = await self.cache_service.get_json(cache_key)
        if cached_data is not None:
            logger.info(f"Cache HIT for key '{cache_key}'")
            return [TaskResponse(**item) for item in cached_data]

        logger.info(f"Cache MISS for key '{cache_key}', reading from database")
        tasks = await self.task_repo.list_by_project(project_id)
        result = [
            TaskResponse(
                id=t.id,
                project_id=t.project_id,
                title=t.title,
                description=t.description,
                status=t.status,
                priority=t.priority,
                assignee_id=t.assignee_id,
                reporter_id=t.reporter_id,
                sprint_id=t.sprint_id,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tasks
        ]
        # Store in Redis with TTL 60 seconds
        await self.cache_service.set_json(
            cache_key, [r.model_dump(mode="json") for r in result], ttl_seconds=60
        )
        return result

    async def update_task(self, task_id: int, req: TaskUpdate) -> TaskResponse:
        existing = await self.task_repo.get_by_id(task_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        if req.title is not None:
            existing.title = req.title
        if req.description is not None:
            existing.description = req.description
        if req.status is not None:
            existing.status = req.status
        if req.priority is not None:
            existing.priority = req.priority
        if req.assignee_id is not None:
            exists, _ = await self.grpc_client.check_user_exists(req.assignee_id)
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Assignee user ID {req.assignee_id} does not exist",
                )
            existing.assignee_id = req.assignee_id
        if req.sprint_id is not None:
            existing.sprint_id = req.sprint_id

        outbox_msg = OutboxMessage(
            event_type="task.updated",
            payload={
                "task_id": existing.id,
                "project_id": existing.project_id,
                "title": existing.title,
                "status": existing.status.value,
                "priority": existing.priority.value,
                "assignee_id": existing.assignee_id,
            },
            status=OutboxStatus.PENDING,
        )

        if self.session is not None:
            updated = await self.task_repo.update(existing, auto_commit=False)
            await self.outbox_repo.create(outbox_msg, auto_commit=False)
            await self.session.commit()
        else:
            updated = await self.task_repo.update(existing)
            await self.outbox_repo.create(outbox_msg)

        # Invalidate cache
        await self.cache_service.delete(f"cache:tasks:project:{updated.project_id}")

        return TaskResponse(
            id=updated.id,
            project_id=updated.project_id,
            title=updated.title,
            description=updated.description,
            status=updated.status,
            priority=updated.priority,
            assignee_id=updated.assignee_id,
            reporter_id=updated.reporter_id,
            sprint_id=updated.sprint_id,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    async def delete_task(self, task_id: int) -> None:
        existing = await self.task_repo.get_by_id(task_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )

        outbox_msg = OutboxMessage(
            event_type="task.deleted",
            payload={
                "task_id": existing.id,
                "project_id": existing.project_id,
                "title": existing.title,
            },
            status=OutboxStatus.PENDING,
        )

        if self.session is not None:
            await self.task_repo.delete(task_id)
            await self.outbox_repo.create(outbox_msg, auto_commit=False)
            await self.session.commit()
        else:
            await self.task_repo.delete(task_id)
            await self.outbox_repo.create(outbox_msg)

        await self.cache_service.delete(f"cache:tasks:project:{existing.project_id}")


class TagApplicationService:
    def __init__(self, tag_repo: SqlAlchemyTagRepository):
        self.tag_repo = tag_repo

    async def create_tag(self, req: TagCreate) -> TagResponse:
        tag = Tag(id=None, name=req.name, color=req.color)
        saved = await self.tag_repo.create(tag)
        return TagResponse(id=saved.id, name=saved.name, color=saved.color)

    async def list_tags(self) -> list[TagResponse]:
        items = await self.tag_repo.list_all()
        return [TagResponse(id=t.id, name=t.name, color=t.color) for t in items]
