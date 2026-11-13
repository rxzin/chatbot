"""A Redis client that behaves like Redis is down."""

import redis.asyncio as redis

from services.memory import RedisMemoryService


def unreachable_client() -> redis.Redis:
    """
    Every command fails, as during an outage. Nothing listens on port 1; the short
    timeout keeps each failed command fast instead of waiting on the operating system.
    """
    return redis.from_url(
        "redis://127.0.0.1:1",
        decode_responses=True,
        socket_connect_timeout=0.05,
        socket_timeout=0.05,
    )


def unreachable_memory_service() -> RedisMemoryService:
    service = RedisMemoryService()
    service.redis_client = unreachable_client()
    return service
