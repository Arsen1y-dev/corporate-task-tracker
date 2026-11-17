import logging

from auth_service.config import settings
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisBlacklistService:
    def __init__(self, redis_client: Redis | None = None):
        self._redis = redis_client

    async def get_client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def add_to_blacklist(self, token: str, expire_seconds: int = 3600) -> None:
        try:
            client = await self.get_client()
            await client.setex(f"blacklist:{token}", expire_seconds, "revoked")
        except Exception as e:
            logger.warning(f"Failed to blacklist token in Redis: {e}")

    async def is_blacklisted(self, token: str) -> bool:
        try:
            client = await self.get_client()
            val = await client.get(f"blacklist:{token}")
            return val is not None
        except Exception as e:
            logger.warning(f"Redis unreachable for blacklist check: {e}")
            return False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()


blacklist_service = RedisBlacklistService()
