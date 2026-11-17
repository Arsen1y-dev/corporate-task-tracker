from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_service.domain.models import (
    Comment,
    OutboxMessage,
    OutboxStatus,
    Project,
    ProjectStatus,
    Sprint,
    Tag,
    Task,
    Worklog,
    Workspace,
)
from tracker_service.infrastructure.models import (
    CommentModel,
    OutboxMessageModel,
    ProjectModel,
    SprintModel,
    TagModel,
    TaskModel,
    WorklogModel,
    WorkspaceModel,
)


class SqlAlchemyWorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, workspace: Workspace, auto_commit: bool = True) -> Workspace:
        model = WorkspaceModel(
            name=workspace.name,
            description=workspace.description,
            owner_id=workspace.owner_id,
            plan=workspace.plan,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(model)
        else:
            await self.session.flush()
        return model.to_domain()

    async def get_by_id(self, workspace_id: int) -> Workspace | None:
        result = await self.session.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model else None

    async def list_by_owner(self, owner_id: int) -> list[Workspace]:
        result = await self.session.execute(
            select(WorkspaceModel).where(WorkspaceModel.owner_id == owner_id)
        )
        return [m.to_domain() for m in result.scalars().all()]


class SqlAlchemyProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, project: Project, auto_commit: bool = True) -> Project:
        model = ProjectModel(
            workspace_id=project.workspace_id,
            name=project.name,
            description=project.description,
            status=project.status.value,
            owner_id=project.owner_id,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(model)
        else:
            await self.session.flush()
        return model.to_domain()

    async def get_by_id(self, project_id: int) -> Project | None:
        result = await self.session.execute(
            select(ProjectModel).where(ProjectModel.id == project_id)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model else None

    async def list_by_workspace(self, workspace_id: int) -> list[Project]:
        result = await self.session.execute(
            select(ProjectModel).where(ProjectModel.workspace_id == workspace_id)
        )
        return [m.to_domain() for m in result.scalars().all()]

    async def count_by_owner(self, owner_id: int, active_only: bool = True) -> int:
        query = select(func.count(ProjectModel.id)).where(ProjectModel.owner_id == owner_id)
        if active_only:
            query = query.where(
                ProjectModel.status.in_([ProjectStatus.ACTIVE.value, ProjectStatus.PENDING.value])
            )
        result = await self.session.execute(query)
        return result.scalar_one() or 0

    async def update(self, project: Project, auto_commit: bool = True) -> Project:
        await self.session.execute(
            update(ProjectModel)
            .where(ProjectModel.id == project.id)
            .values(
                name=project.name,
                description=project.description,
                status=project.status.value,
            )
        )
        if auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return (await self.get_by_id(project.id)) or project


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task: Task, auto_commit: bool = True) -> Task:
        model = TaskModel(
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority.value,
            assignee_id=task.assignee_id,
            reporter_id=task.reporter_id,
            sprint_id=task.sprint_id,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(model)
        else:
            await self.session.flush()
        return model.to_domain()

    async def get_by_id(self, task_id: int) -> Task | None:
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model else None

    async def list_by_project(self, project_id: int) -> list[Task]:
        result = await self.session.execute(
            select(TaskModel)
            .where(TaskModel.project_id == project_id)
            .order_by(TaskModel.id.desc())
        )
        return [m.to_domain() for m in result.scalars().all()]

    async def update(self, task: Task, auto_commit: bool = True) -> Task:
        values = {
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.value,
            "assignee_id": task.assignee_id,
            "sprint_id": task.sprint_id,
            "updated_at": datetime.now(timezone.utc),
        }
        await self.session.execute(
            update(TaskModel).where(TaskModel.id == task.id).values(**values)
        )
        if auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return (await self.get_by_id(task.id)) or task

    async def delete(self, task_id: int) -> None:
        await self.session.execute(
            delete(TaskModel).where(TaskModel.id == task_id)
        )
        await self.session.commit()


class SqlAlchemySprintRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, sprint: Sprint) -> Sprint:
        model = SprintModel(
            project_id=sprint.project_id,
            name=sprint.name,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            is_active=sprint.is_active,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model.to_domain()

    async def list_by_project(self, project_id: int) -> list[Sprint]:
        result = await self.session.execute(
            select(SprintModel).where(SprintModel.project_id == project_id)
        )
        return [m.to_domain() for m in result.scalars().all()]


class SqlAlchemyCommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, comment: Comment) -> Comment:
        model = CommentModel(
            task_id=comment.task_id,
            author_id=comment.author_id,
            content=comment.content,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model.to_domain()

    async def list_by_task(self, task_id: int) -> list[Comment]:
        result = await self.session.execute(
            select(CommentModel)
            .where(CommentModel.task_id == task_id)
            .order_by(CommentModel.id.asc())
        )
        return [m.to_domain() for m in result.scalars().all()]


class SqlAlchemyWorklogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, worklog: Worklog) -> Worklog:
        model = WorklogModel(
            task_id=worklog.task_id,
            user_id=worklog.user_id,
            time_spent_minutes=worklog.time_spent_minutes,
            description=worklog.description,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model.to_domain()

    async def list_by_task(self, task_id: int) -> list[Worklog]:
        result = await self.session.execute(
            select(WorklogModel)
            .where(WorklogModel.task_id == task_id)
            .order_by(WorklogModel.id.desc())
        )
        return [m.to_domain() for m in result.scalars().all()]


class SqlAlchemyTagRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tag: Tag) -> Tag:
        model = TagModel(name=tag.name, color=tag.color)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model.to_domain()

    async def get_by_id(self, tag_id: int) -> Tag | None:
        result = await self.session.execute(
            select(TagModel).where(TagModel.id == tag_id)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model else None

    async def list_all(self) -> list[Tag]:
        result = await self.session.execute(
            select(TagModel).order_by(TagModel.name.asc())
        )
        return [m.to_domain() for m in result.scalars().all()]


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, message: OutboxMessage, auto_commit: bool = True) -> OutboxMessage:
        model = OutboxMessageModel(
            id=message.id,
            event_type=message.event_type,
            payload=message.payload,
            status=message.status.value,
        )
        self.session.add(model)
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(model)
        else:
            await self.session.flush()
        return model.to_domain()

    async def get_pending(self, limit: int = 50) -> list[OutboxMessage]:
        result = await self.session.execute(
            select(OutboxMessageModel)
            .where(OutboxMessageModel.status == OutboxStatus.PENDING.value)
            .order_by(OutboxMessageModel.created_at.asc())
            .limit(limit)
        )
        return [m.to_domain() for m in result.scalars().all()]

    async def mark_processed(self, message_id: str) -> None:
        await self.session.execute(
            update(OutboxMessageModel)
            .where(OutboxMessageModel.id == message_id)
            .values(
                status=OutboxStatus.PROCESSED.value,
                processed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.commit()

    async def mark_failed(self, message_id: str, error: str) -> None:
        await self.session.execute(
            update(OutboxMessageModel)
            .where(OutboxMessageModel.id == message_id)
            .values(
                status=OutboxStatus.FAILED.value,
                error_message=error,
            )
        )
        await self.session.commit()
