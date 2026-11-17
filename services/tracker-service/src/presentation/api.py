from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_service.application.dtos import (
    CommentCreate,
    CommentResponse,
    ProjectResponse,
    ProjectSagaCreateRequest,
    ProjectSagaResponse,
    SprintCreate,
    SprintResponse,
    TagCreate,
    TagResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    WorklogCreate,
    WorklogResponse,
    WorkspaceCreate,
    WorkspaceResponse,
)
from tracker_service.application.saga import ProjectCreationSaga
from tracker_service.application.services import (
    TagApplicationService,
    TaskApplicationService,
    WorkspaceApplicationService,
)
from tracker_service.domain.models import Comment, Sprint, Worklog
from tracker_service.infrastructure.database import get_db_session
from tracker_service.infrastructure.grpc_client import auth_grpc_client
from tracker_service.infrastructure.redis_cache import cache_service
from tracker_service.infrastructure.repositories import (
    SqlAlchemyCommentRepository,
    SqlAlchemyOutboxRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemySprintRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyWorklogRepository,
    SqlAlchemyWorkspaceRepository,
)
from tracker_service.presentation.dependencies import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Tracker Core"])


# ================= Workspaces =================
@router.post(
    "/workspaces",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace(
    req: WorkspaceCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = WorkspaceApplicationService(SqlAlchemyWorkspaceRepository(session))
    return await service.create_workspace(req, owner_id=user["id"])


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = WorkspaceApplicationService(SqlAlchemyWorkspaceRepository(session))
    return await service.list_user_workspaces(owner_id=user["id"])


# ================= Projects & Saga =================
@router.post("/projects/saga", response_model=ProjectSagaResponse)
async def create_project_via_saga(
    req: ProjectSagaCreateRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Distributed Saga Orchestration for Project Creation.
    Coordinates local DB creation, gRPC quota check to auth-service,
    and automatic compensation upon failure.
    """
    saga = ProjectCreationSaga(
        project_repo=SqlAlchemyProjectRepository(session),
        outbox_repo=SqlAlchemyOutboxRepository(session),
        grpc_client=auth_grpc_client,
        cache_service=cache_service,
        workspace_repo=SqlAlchemyWorkspaceRepository(session),
        session=session,
    )
    return await saga.execute(req, owner_id=user["id"])


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    workspace_id: int = Query(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = SqlAlchemyProjectRepository(session)
    projects = await repo.list_by_workspace(workspace_id)
    return [
        ProjectResponse(
            id=p.id,
            workspace_id=p.workspace_id,
            name=p.name,
            description=p.description,
            status=p.status,
            owner_id=p.owner_id,
            created_at=p.created_at,
        )
        for p in projects
    ]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = SqlAlchemyProjectRepository(session)
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project ID {project_id} not found",
        )
    return ProjectResponse(
        id=project.id,
        workspace_id=project.workspace_id,
        name=project.name,
        description=project.description,
        status=project.status,
        owner_id=project.owner_id,
        created_at=project.created_at,
    )


# ================= Tasks (Cached in Redis, Outbox event, gRPC assignee check) =================
@router.post(
    "/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED
)
async def create_task(
    req: TaskCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TaskApplicationService(
        task_repo=SqlAlchemyTaskRepository(session),
        outbox_repo=SqlAlchemyOutboxRepository(session),
        grpc_client=auth_grpc_client,
        cache_service=cache_service,
        project_repo=SqlAlchemyProjectRepository(session),
        session=session,
    )
    return await service.create_task(req, reporter_id=user["id"])


@router.get("/tasks", response_model=list[TaskResponse])
async def get_tasks(
    project_id: int = Query(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TaskApplicationService(
        task_repo=SqlAlchemyTaskRepository(session),
        outbox_repo=SqlAlchemyOutboxRepository(session),
        grpc_client=auth_grpc_client,
        cache_service=cache_service,
        project_repo=SqlAlchemyProjectRepository(session),
        session=session,
    )
    return await service.get_tasks_by_project(project_id)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TaskApplicationService(
        task_repo=SqlAlchemyTaskRepository(session),
        outbox_repo=SqlAlchemyOutboxRepository(session),
        grpc_client=auth_grpc_client,
        cache_service=cache_service,
        project_repo=SqlAlchemyProjectRepository(session),
        session=session,
    )
    return await service.get_task_by_id(task_id)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    req: TaskUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TaskApplicationService(
        task_repo=SqlAlchemyTaskRepository(session),
        outbox_repo=SqlAlchemyOutboxRepository(session),
        grpc_client=auth_grpc_client,
        cache_service=cache_service,
        project_repo=SqlAlchemyProjectRepository(session),
        session=session,
    )
    return await service.update_task(task_id, req)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TaskApplicationService(
        task_repo=SqlAlchemyTaskRepository(session),
        outbox_repo=SqlAlchemyOutboxRepository(session),
        grpc_client=auth_grpc_client,
        cache_service=cache_service,
        project_repo=SqlAlchemyProjectRepository(session),
        session=session,
    )
    await service.delete_task(task_id)
    return {"message": "Task deleted successfully"}


# ================= Sprints =================
@router.post(
    "/sprints", response_model=SprintResponse, status_code=status.HTTP_201_CREATED
)
async def create_sprint(
    req: SprintCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    project_repo = SqlAlchemyProjectRepository(session)
    project = await project_repo.get_by_id(req.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project ID {req.project_id} not found",
        )
    repo = SqlAlchemySprintRepository(session)
    sprint = Sprint(
        id=None,
        project_id=req.project_id,
        name=req.name,
        start_date=req.start_date,
        end_date=req.end_date,
        is_active=True,
    )
    saved = await repo.create(sprint)
    return SprintResponse(
        id=saved.id,
        project_id=saved.project_id,
        name=saved.name,
        start_date=saved.start_date,
        end_date=saved.end_date,
        is_active=saved.is_active,
    )


@router.get("/sprints", response_model=list[SprintResponse])
async def list_sprints(
    project_id: int = Query(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = SqlAlchemySprintRepository(session)
    sprints = await repo.list_by_project(project_id)
    return [
        SprintResponse(
            id=s.id,
            project_id=s.project_id,
            name=s.name,
            start_date=s.start_date,
            end_date=s.end_date,
            is_active=s.is_active,
        )
        for s in sprints
    ]


# ================= Comments =================
@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    task_id: int,
    req: CommentCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    task_repo = SqlAlchemyTaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task ID {task_id} not found",
        )
    repo = SqlAlchemyCommentRepository(session)
    saved = await repo.create(
        Comment(id=None, task_id=task_id, author_id=user["id"], content=req.content)
    )
    return CommentResponse(
        id=saved.id,
        task_id=saved.task_id,
        author_id=saved.author_id,
        content=saved.content,
        created_at=saved.created_at,
    )


@router.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    task_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = SqlAlchemyCommentRepository(session)
    comments = await repo.list_by_task(task_id)
    return [
        CommentResponse(
            id=c.id,
            task_id=c.task_id,
            author_id=c.author_id,
            content=c.content,
            created_at=c.created_at,
        )
        for c in comments
    ]


# ================= Worklogs =================
@router.post(
    "/tasks/{task_id}/worklogs",
    response_model=WorklogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def log_work(
    task_id: int,
    req: WorklogCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    task_repo = SqlAlchemyTaskRepository(session)
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task ID {task_id} not found",
        )
    repo = SqlAlchemyWorklogRepository(session)
    saved = await repo.create(
        Worklog(
            id=None,
            task_id=task_id,
            user_id=user["id"],
            time_spent_minutes=req.time_spent_minutes,
            description=req.description,
        )
    )
    return WorklogResponse(
        id=saved.id,
        task_id=saved.task_id,
        user_id=saved.user_id,
        time_spent_minutes=saved.time_spent_minutes,
        description=saved.description,
        logged_at=saved.logged_at,
    )


@router.get("/tasks/{task_id}/worklogs", response_model=list[WorklogResponse])
async def list_worklogs(
    task_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = SqlAlchemyWorklogRepository(session)
    worklogs = await repo.list_by_task(task_id)
    return [
        WorklogResponse(
            id=w.id,
            task_id=w.task_id,
            user_id=w.user_id,
            time_spent_minutes=w.time_spent_minutes,
            description=w.description,
            logged_at=w.logged_at,
        )
        for w in worklogs
    ]


# ================= Tags =================
@router.post(
    "/tags",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tag(
    req: TagCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TagApplicationService(SqlAlchemyTagRepository(session))
    return await service.create_tag(req)


@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = TagApplicationService(SqlAlchemyTagRepository(session))
    return await service.list_tags()
