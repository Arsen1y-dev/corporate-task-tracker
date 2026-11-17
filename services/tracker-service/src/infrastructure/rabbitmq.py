import json
import logging
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message
from tracker_service.config import settings

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    def __init__(self):
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._exchange: aio_pika.abc.AbstractRobustExchange | None = None

    async def connect(self) -> None:
        try:
            self._connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE,
                ExchangeType.TOPIC,
                durable=True,
            )
            logger.info(
                f"Connected to RabbitMQ exchange '{settings.RABBITMQ_EXCHANGE}'"
            )
        except Exception as e:
            logger.warning(f"Could not connect to RabbitMQ at startup: {e}")

    async def publish_event(
        self, event_type: str, message_id: str, payload: dict[str, Any]
    ) -> bool:
        try:
            if self._exchange is None or self._connection is None or self._connection.is_closed:
                await self.connect()
            if self._exchange is None:
                logger.warning("RabbitMQ exchange not available")
                return False

            body = json.dumps(
                {
                    "message_id": message_id,
                    "event_type": event_type,
                    "payload": payload,
                },
                default=str,
            ).encode("utf-8")

            msg = Message(
                body=body,
                content_type="application/json",
                message_id=message_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self._exchange.publish(msg, routing_key=event_type)
            logger.info(f"Published event '{event_type}' [id={message_id}] to RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"Failed to publish event '{event_type}' to RabbitMQ: {e}")
            return False

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


rabbitmq_publisher = RabbitMQPublisher()
