from fastapi import APIRouter, Depends, HTTPException, Query, status
from notification_service.application.dtos import EventLogResponse, NotificationResponse
from notification_service.application.services import NotificationApplicationService
from notification_service.infrastructure.database import get_db_session
from notification_service.infrastructure.repositories import (
    SqlAlchemyEventLogRepository,
    SqlAlchemyInboxRepository,
    SqlAlchemyNotificationRepository,
)
from notification_service.presentation.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["Notifications & Audit"])


def get_notification_service(
    session: AsyncSession = Depends(get_db_session),
) -> NotificationApplicationService:
    return NotificationApplicationService(
        notification_repo=SqlAlchemyNotificationRepository(session),
        event_log_repo=SqlAlchemyEventLogRepository(session),
        inbox_repo=SqlAlchemyInboxRepository(session),
    )


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(False),
    user: dict = Depends(get_current_user),
    service: NotificationApplicationService = Depends(get_notification_service),
):
    return await service.get_user_notifications(
        user_id=user["id"], unread_only=unread_only
    )


@router.patch("/notifications/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    service: NotificationApplicationService = Depends(get_notification_service),
):
    success = await service.mark_read(
        notification_id=notification_id, user_id=user["id"]
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"message": "Notification marked as read"}


@router.get("/event-logs", response_model=list[EventLogResponse])
async def list_event_logs(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    service: NotificationApplicationService = Depends(get_notification_service),
):
    return await service.get_recent_event_logs(limit=limit)
