import json
import logging
from typing import Any

from redis.asyncio import Redis
from tracker_service.config import settings

logger = logging.getLogger(__name__)


class RedisCacheService:
    def __init__(self, redis_client: Redis | None = None):
        self._redis = redis_client

    async def get_client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def get_json(self, key: str) -> Any | None:
        try:
            client = await self.get_client()
            val = await client.get(key)
            if val is not None:
                return json.loads(val)
            return None
        except Exception as e:
            logger.warning(f"Redis get_json error for key '{key}': {e}")
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        try:
            client = await self.get_client()
            await client.setex(key, ttl_seconds, json.dumps(value, default=str))
        except Exception as e:
            logger.warning(f"Redis set_json error for key '{key}': {e}")

    async def delete(self, key: str) -> None:
        try:
            client = await self.get_client()
            await client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete error for key '{key}': {e}")

    async def delete_pattern(self, pattern: str) -> None:
        try:
            client = await self.get_client()
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis delete_pattern error for pattern '{pattern}': {e}")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()


cache_service = RedisCacheService()
