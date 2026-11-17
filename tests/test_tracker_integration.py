import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "tracker-service"))

from tracker_service.infrastructure.database import Base, get_db_session
from tracker_service.infrastructure.grpc_client import auth_grpc_client
from tracker_service.infrastructure.redis_cache import cache_service
from tracker_service.main import app
from tracker_service.presentation.dependencies import get_current_user


@pytest.fixture
async def tracker_test_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    async def override_get_current_user():
        return {"id": 1, "username": "lead_architect", "role": "admin"}

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock gRPC client responses
    auth_grpc_client.check_user_exists = AsyncMock(
        return_value=(True, {"user_id": 1, "username": "lead_architect"})
    )
    auth_grpc_client.check_project_quota = AsyncMock(
        return_value=(True, "Quota valid", 10)
    )

    # In-memory dictionary for mock Redis cache
    cache_store = {}

    async def mock_get_json(k):
        return cache_store.get(k)

    async def mock_set_json(k, v, ttl_seconds=60):
        cache_store[k] = v

    async def mock_delete(k):
        cache_store.pop(k, None)

    cache_service.get_json = mock_get_json
    cache_service.set_json = mock_set_json
    cache_service.delete = mock_delete

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_tracker_full_workflow(tracker_test_client: AsyncClient):
    # 1. Health check
    h = await tracker_test_client.get("/health")
    assert h.status_code == 200

    # 2. Create workspace
    ws_res = await tracker_test_client.post(
        "/api/v1/workspaces",
        json={"name": "Engineering Workspace", "description": "Core dev team"},
    )
    assert ws_res.status_code == 201
    ws = ws_res.json()
    ws_id = ws["id"]

    # 3. Create project via Saga (Success scenario)
    saga_res = await tracker_test_client.post(
        "/api/v1/projects/saga",
        json={
            "workspace_id": ws_id,
            "name": "Backend Refactoring",
            "description": "Migration to microservices",
            "simulate_quota_exceeded": False,
        },
    )
    assert saga_res.status_code == 200
    saga_data = saga_res.json()
    assert saga_data["saga_status"] == "COMPLETED"
    assert saga_data["compensation_triggered"] is False
    assert saga_data["project"]["status"] == "active"
    project_id = saga_data["project"]["id"]

    # 4. Create project via Saga with Compensation (Failure scenario)
    saga_fail_res = await tracker_test_client.post(
        "/api/v1/projects/saga",
        json={
            "workspace_id": ws_id,
            "name": "Quota Exceeding Project",
            "simulate_quota_exceeded": True,
        },
    )
    assert saga_fail_res.status_code == 200
    fail_data = saga_fail_res.json()
    assert fail_data["saga_status"] == "COMPENSATED"
    assert fail_data["compensation_triggered"] is True
    assert fail_data["project"]["status"] == "failed_quota"

    # 5. Create Task
    task_res = await tracker_test_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Configure Redis cluster",
            "description": "Add caching layer for query optimization",
            "status": "todo",
            "priority": "high",
            "assignee_id": 1,
        },
    )
    assert task_res.status_code == 201
    task = task_res.json()
    task_id = task["id"]
    assert task["title"] == "Configure Redis cluster"

    # 6. Retrieve tasks (checks Redis cache populate)
    tasks_res = await tracker_test_client.get(
        f"/api/v1/tasks?project_id={project_id}"
    )
    assert tasks_res.status_code == 200
    tasks_list = tasks_res.json()
    assert len(tasks_list) == 1

    # 7. Add Comment
    comment_res = await tracker_test_client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "Draft PR is ready for review"},
    )
    assert comment_res.status_code == 201
    assert comment_res.json()["content"] == "Draft PR is ready for review"

    # 8. Log Work
    worklog_res = await tracker_test_client.post(
        f"/api/v1/tasks/{task_id}/worklogs",
        json={"time_spent_minutes": 90, "description": "Wrote unit tests"},
    )
    assert worklog_res.status_code == 201
    assert worklog_res.json()["time_spent_minutes"] == 90

    # 9. Get Project by ID
    p_get = await tracker_test_client.get(f"/api/v1/projects/{project_id}")
    assert p_get.status_code == 200
    assert p_get.json()["id"] == project_id

    # 10. Get Task by ID
    t_get = await tracker_test_client.get(f"/api/v1/tasks/{task_id}")
    assert t_get.status_code == 200
    assert t_get.json()["id"] == task_id

    # 11. Tags CRUD
    tag_create_res = await tracker_test_client.post(
        "/api/v1/tags",
        json={"name": "performance", "color": "#f59e0b"},
    )
    assert tag_create_res.status_code == 201
    assert tag_create_res.json()["name"] == "performance"

    tags_list_res = await tracker_test_client.get("/api/v1/tags")
    assert tags_list_res.status_code == 200
    assert len(tags_list_res.json()) >= 1

    # 12. 404 Validation: creating task in phantom project
    ghost_task_res = await tracker_test_client.post(
        "/api/v1/tasks",
        json={"project_id": 99999, "title": "Ghost"},
    )
    assert ghost_task_res.status_code == 404

    # 13. 404 Validation: comment on phantom task
    ghost_comment_res = await tracker_test_client.post(
        "/api/v1/tasks/99999/comments",
        json={"content": "Ghost"},
    )
    assert ghost_comment_res.status_code == 404

    # 14. 404 Validation: worklog on phantom task
    ghost_worklog_res = await tracker_test_client.post(
        "/api/v1/tasks/99999/worklogs",
        json={"time_spent_minutes": 10},
    )
    assert ghost_worklog_res.status_code == 404

    # 15. Delete Task
    del_res = await tracker_test_client.delete(f"/api/v1/tasks/{task_id}")
    assert del_res.status_code == 200
    get_after_del = await tracker_test_client.get(f"/api/v1/tasks/{task_id}")
    assert get_after_del.status_code == 404
