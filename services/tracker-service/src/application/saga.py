import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_service.application.dtos import (
    ProjectResponse,
    ProjectSagaCreateRequest,
    ProjectSagaResponse,
)
from tracker_service.domain.models import OutboxMessage, OutboxStatus, Project, ProjectStatus
from tracker_service.infrastructure.grpc_client import AuthGrpcClient
from tracker_service.infrastructure.redis_cache import RedisCacheService
from tracker_service.infrastructure.repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyWorkspaceRepository,
)

logger = logging.getLogger(__name__)


class ProjectCreationSaga:
    def __init__(
        self,
        project_repo: SqlAlchemyProjectRepository,
        outbox_repo: SqlAlchemyOutboxRepository,
        grpc_client: AuthGrpcClient,
        cache_service: RedisCacheService,
        workspace_repo: SqlAlchemyWorkspaceRepository | None = None,
        session: AsyncSession | None = None,
    ):
        self.project_repo = project_repo
        self.outbox_repo = outbox_repo
        self.grpc_client = grpc_client
        self.cache_service = cache_service
        self.workspace_repo = workspace_repo
        self.session = session

    async def execute(
        self, req: ProjectSagaCreateRequest, owner_id: int
    ) -> ProjectSagaResponse:
        logger.info(
            f"Starting ProjectCreationSaga for owner_id={owner_id}, name='{req.name}'"
        )

        # Validation: workspace must exist
        if self.workspace_repo is not None:
            workspace = await self.workspace_repo.get_by_id(req.workspace_id)
            if not workspace:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Workspace ID {req.workspace_id} not found",
                )

        # Step 1: Create project in PENDING state
        project = Project(
            id=None,
            workspace_id=req.workspace_id,
            name=req.name,
            description=req.description,
            status=ProjectStatus.PENDING,
            owner_id=owner_id,
        )
        saved_project = await self.project_repo.create(project)
        logger.info(
            f"Saga Step 1: Project {saved_project.id} created with status PENDING"
        )

        # Step 2: Synchronous gRPC check to auth-service for user quota
        active_projects_count = await self.project_repo.count_by_owner(
            owner_id, active_only=True
        )
        # Note: saved_project is already created, so count includes it

        if req.simulate_quota_exceeded:
            allowed = False
            reason = "Simulated quota exceeded flag triggered"
            max_projects = active_projects_count - 1
        else:
            current_count = max(0, active_projects_count - 1)
            allowed, reason, max_projects = await self.grpc_client.check_project_quota(
                user_id=owner_id,
                current_project_count=current_count,
            )

        # Compensation branch if quota exceeded or check failed
        if not allowed:
            logger.warning(
                f"Saga Step 2: Quota check failed ({reason}). Triggering compensation..."
            )
            saved_project.status = ProjectStatus.FAILED_QUOTA
            compensated_project = await self.project_repo.update(saved_project)
            await self.cache_service.delete(f"cache:project:{saved_project.id}")
            logger.info(
                f"Saga Compensation complete: Project {saved_project.id} set to FAILED_QUOTA"
            )
            return ProjectSagaResponse(
                project=ProjectResponse(
                    id=compensated_project.id,
                    workspace_id=compensated_project.workspace_id,
                    name=compensated_project.name,
                    description=compensated_project.description,
                    status=compensated_project.status,
                    owner_id=compensated_project.owner_id,
                    created_at=compensated_project.created_at,
                ),
                saga_status="COMPENSATED",
                quota_checked=True,
                compensation_triggered=True,
                message=f"Saga compensated: {reason}",
            )

        # Step 3: Success branch - Activate project and enqueue outbox message
        saved_project.status = ProjectStatus.ACTIVE
        outbox_msg = OutboxMessage(
            event_type="project.created",
            payload={
                "project_id": saved_project.id,
                "workspace_id": saved_project.workspace_id,
                "name": saved_project.name,
                "owner_id": saved_project.owner_id,
                "status": saved_project.status.value,
            },
            status=OutboxStatus.PENDING,
        )

        if self.session is not None:
            active_project = await self.project_repo.update(
                saved_project, auto_commit=False
            )
            await self.outbox_repo.create(outbox_msg, auto_commit=False)
            await self.session.commit()
        else:
            active_project = await self.project_repo.update(saved_project)
            await self.outbox_repo.create(outbox_msg)

        await self.cache_service.delete(f"cache:project:{active_project.id}")
        logger.info(
            f"Saga Step 3: Project {active_project.id} activated, Outbox event recorded"
        )

        return ProjectSagaResponse(
            project=ProjectResponse(
                id=active_project.id,
                workspace_id=active_project.workspace_id,
                name=active_project.name,
                description=active_project.description,
                status=active_project.status,
                owner_id=active_project.owner_id,
                created_at=active_project.created_at,
            ),
            saga_status="COMPLETED",
            quota_checked=True,
            compensation_triggered=False,
            message="Project successfully created and activated via Saga orchestrator.",
        )
