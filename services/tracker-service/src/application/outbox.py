import asyncio
import logging

from tracker_service.config import settings
from tracker_service.infrastructure.database import AsyncSessionLocal
from tracker_service.infrastructure.rabbitmq import rabbitmq_publisher
from tracker_service.infrastructure.repositories import SqlAlchemyOutboxRepository

logger = logging.getLogger(__name__)


class OutboxPublisherService:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def publish_pending_once(self) -> int:
        published_count = 0
        async with AsyncSessionLocal() as session:
            outbox_repo = SqlAlchemyOutboxRepository(session)
            pending_messages = await outbox_repo.get_pending(limit=20)
            for msg in pending_messages:
                try:
                    ok = await rabbitmq_publisher.publish_event(
                        event_type=msg.event_type,
                        message_id=msg.id,
                        payload=msg.payload,
                    )
                    if ok:
                        await outbox_repo.mark_processed(msg.id)
                        published_count += 1
                    else:
                        logger.warning(
                            f"Message {msg.id} could not be sent to RabbitMQ. Will retry."
                        )
                except Exception as e:
                    logger.error(f"Error publishing outbox message {msg.id}: {e}")
                    await outbox_repo.mark_failed(msg.id, str(e))
        return published_count

    async def _loop(self) -> None:
        logger.info("Outbox publisher background loop started")
        while self._running:
            try:
                await self.publish_pending_once()
            except Exception as e:
                logger.error(f"Error in outbox publisher loop: {e}")
            await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


outbox_publisher_service = OutboxPublisherService()
