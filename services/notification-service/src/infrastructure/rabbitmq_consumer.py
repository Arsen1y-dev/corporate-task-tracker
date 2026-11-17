import asyncio
import json
import logging

import aio_pika
from aio_pika import ExchangeType
from notification_service.application.services import NotificationApplicationService
from notification_service.config import settings
from notification_service.infrastructure.database import AsyncSessionLocal
from notification_service.infrastructure.repositories import (
    SqlAlchemyEventLogRepository,
    SqlAlchemyInboxRepository,
    SqlAlchemyNotificationRepository,
)

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    def __init__(self):
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def _process_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process(requeue=True, reject_on_redelivered=True):
            try:
                data = json.loads(message.body.decode("utf-8"))
            except Exception as e:
                logger.error(f"Malformed JSON in RabbitMQ message: {e}. Dropping.")
                return

            message_id = data.get("message_id") or message.message_id or "unknown"
            event_type = data.get("event_type", "unknown")
            payload = data.get("payload", {})

            async with AsyncSessionLocal() as session:
                app_service = NotificationApplicationService(
                    notification_repo=SqlAlchemyNotificationRepository(session),
                    event_log_repo=SqlAlchemyEventLogRepository(session),
                    inbox_repo=SqlAlchemyInboxRepository(session),
                    session=session,
                )
                try:
                    await app_service.process_incoming_event(
                        message_id=message_id,
                        event_type=event_type,
                        payload=payload,
                    )
                except Exception as e:
                    logger.error(f"Transient error processing RabbitMQ message {message_id}: {e}")
                    raise

    async def _run(self) -> None:
        while self._running:
            try:
                logger.info(
                    f"Connecting consumer to RabbitMQ at {settings.RABBITMQ_URL}..."
                )
                self._connection = await aio_pika.connect_robust(
                    settings.RABBITMQ_URL
                )
                self._channel = await self._connection.channel()
                await self._channel.set_qos(prefetch_count=10)

                exchange = await self._channel.declare_exchange(
                    settings.RABBITMQ_EXCHANGE,
                    ExchangeType.TOPIC,
                    durable=True,
                )
                queue = await self._channel.declare_queue(
                    settings.RABBITMQ_QUEUE,
                    durable=True,
                )
                await queue.bind(exchange, routing_key="#")

                logger.info(
                    f"RabbitMQ consumer listening on '{settings.RABBITMQ_QUEUE}'"
                )
                await queue.consume(self._process_message)

                # Keep running until cancelled
                while self._running and not self._connection.is_closed:
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(
                    f"RabbitMQ consumer connection error: {e}. Retrying in 5s..."
                )
                await asyncio.sleep(5)

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


rabbitmq_consumer = RabbitMQConsumer()
