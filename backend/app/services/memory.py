import logging

import redis.asyncio as redis
from schemas.chat import MessageParam
from core.config import getSettings
from core.logging import log_event, logger
from datetime import datetime, timezone
from uuid import UUID
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from services.base import AIPlatform


class RedisMemoryService:
    def __init__(self):
        settings = getSettings()
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        self.conversation_ttl = 86400

    def _history_key(self, user_id: UUID, conversation_id: UUID) -> str:
        return f"chat:user:{user_id}:conversation:{conversation_id}"

    def _summary_key(self, user_id: UUID, conversation_id: UUID) -> str:
        return f"chat:user:{user_id}:conversation:{conversation_id}:summary"

    def _synced_key(self, user_id: UUID, conversation_id: UUID) -> str:
        """How many Postgres messages the cached history reflects."""
        return f"chat:user:{user_id}:conversation:{conversation_id}:synced"

    async def _set_synced(
        self, user_id: UUID, conversation_id: UUID, message_count: int
    ) -> None:
        try:
            await self.redis_client.set(
                self._synced_key(user_id, conversation_id),
                message_count,
                ex=self.conversation_ttl,
            )
        except Exception as e:
            logger.exception(f"Failed to record sync marker for {conversation_id}: {e}")

    async def record_saved_turn(self, user_id: UUID, conversation_id: UUID) -> None:
        """
        A turn reached both Redis and Postgres: move the marker on by its 2 messages.
        A missing marker stays missing, so the next turn rebuilds from Postgres.
        """
        try:
            await self.redis_client.eval(
                "if redis.call('exists', KEYS[1]) == 1 then "
                "redis.call('incrby', KEYS[1], 2) "
                "redis.call('expire', KEYS[1], ARGV[1]) end",
                1,
                self._synced_key(user_id, conversation_id),
                self.conversation_ttl,
            )
        except Exception as e:
            logger.exception(f"Failed to advance sync marker for {conversation_id}: {e}")

    async def _in_sync_with_postgres(
        self, user_id: UUID, conversation_id: UUID, db: "AsyncSession"
    ) -> bool:
        from services.message import count_messages

        try:
            marker = await self.redis_client.get(self._synced_key(user_id, conversation_id))
        except Exception:
            return True  # Redis just answered for the history; don't rebuild on a blip.
        if marker is None:
            return False
        return int(marker) == await count_messages(db, conversation_id)

    def _rate_limit_key(self, user_id: str | UUID, action: str) -> str:
        return f"rate_limit:{action}:{user_id}"

    async def try_acquire_rate_limit(
        self, user_id: str | UUID, action: str, limit_seconds: int = 3600
    ) -> bool:
        """
        Atomically reserve a rate-limit slot (SET NX).
        Returns True when the slot was acquired; False when the user is already limited.
        Call release_rate_limit on failure so a failed action does not consume the slot.
        """
        key = self._rate_limit_key(user_id, action)
        try:
            result = await self.redis_client.set(key, "1", ex=limit_seconds, nx=True)
            return bool(result)
        except Exception as e:
            logger.exception(
                f"Failed to acquire rate limit for {action} user {user_id}: {e}"
            )
            return False

    async def release_rate_limit(self, user_id: str | UUID, action: str) -> None:
        """Release a reserved rate-limit slot after a failed action."""
        key = self._rate_limit_key(user_id, action)
        try:
            await self.redis_client.delete(key)
        except Exception as e:
            logger.exception(
                f"Failed to release rate limit for {action} user {user_id}: {e}"
            )

    async def consume_daily_quota(
        self, user_id: str | UUID, action: str, limit: int, *, fail_open: bool = False
    ) -> bool:
        """
        Count one use of action for today (UTC). False once the day's limit is used.
        On a Redis failure returns fail_open: False by default, to protect paid APIs;
        the chat route passes True so an outage does not take chat down.
        """
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"quota:{action}:{user_id}:{day}"
        try:
            count = await self.redis_client.incr(key)
            if count == 1:
                await self.redis_client.expire(key, 2 * 86400)
            return count <= limit
        except Exception:
            logger.exception(f"Failed to count {action} quota for user {user_id}")
            if fail_open:
                log_event(
                    event="chat.quota.check.skipped",
                    message=f"Redis unavailable; {action} quota check skipped",
                    level=logging.WARNING,
                    action=action,
                )
            return fail_open

    async def acquire_inflight(self, key: str, ttl_seconds: int) -> bool | None:
        """
        Claim key (SET NX EX). True when claimed, False when someone else holds it,
        None when Redis fails, so the caller can carry on without the lock.
        """
        try:
            return bool(await self.redis_client.set(key, "1", ex=ttl_seconds, nx=True))
        except Exception:
            logger.exception(f"Failed to acquire in-flight lock {key}")
            return None

    async def release_inflight(self, key: str) -> None:
        try:
            await self.redis_client.delete(key)
        except Exception:
            logger.exception(f"Failed to release in-flight lock {key}")

    async def get_rate_limit_ttl(
        self, user_id: str | UUID, action: str
    ) -> Optional[int]:
        """Return remaining cooldown seconds, or None when not rate limited."""
        key = self._rate_limit_key(user_id, action)
        try:
            ttl = await self.redis_client.ttl(key)
            return ttl if ttl > 0 else None
        except Exception as e:
            logger.exception(
                f"Failed to read rate limit TTL for {action} user {user_id}: {e}"
            )
            return None

    async def get_history(
        self, user_id: UUID, conversation_id: UUID
    ) -> list[MessageParam]:
        """Fetches conversation message history from Redis."""
        key = self._history_key(user_id, conversation_id)

        try:
            raw_messages = await self.redis_client.lrange(key, 0, -1)

            # Deserialize JSON strings back into MessageParam Pydantic models
            history = [MessageParam.model_validate_json(msg) for msg in raw_messages]
            return history
        except Exception as e:
            logger.exception(f"Failed to fetch history for {conversation_id}: {e}")
            return []

    async def get_summary(self, user_id: UUID, conversation_id: UUID) -> Optional[str]:
        key = self._summary_key(user_id, conversation_id)
        try:
            return await self.redis_client.get(key)
        except Exception as e:
            logger.exception(f"Failed to fetch summary for {conversation_id}: {e}")
            return None

    async def save_summary(
        self, user_id: UUID, conversation_id: UUID, summary: str
    ) -> bool:
        key = self._summary_key(user_id, conversation_id)
        try:
            await self.redis_client.set(key, summary, ex=self.conversation_ttl)
            return True
        except Exception as e:
            logger.exception(f"Failed to save summary for {conversation_id}: {e}")
            return False

    async def replace_history(
        self,
        user_id: UUID,
        conversation_id: UUID,
        messages: list[MessageParam],
    ) -> None:
        """Replace the Redis message list without touching the rolling summary."""
        key = self._history_key(user_id, conversation_id)

        try:
            await self.redis_client.delete(key)
            if not messages:
                return

            await self.redis_client.rpush(
                key,
                *[message.model_dump_json(by_alias=True) for message in messages],
            )
            await self.redis_client.expire(key, self.conversation_ttl)
        except Exception as e:
            logger.exception(
                f"Failed to replace Redis history for {conversation_id}: {e}"
            )

    # Appends the turn to a list that exists; writes the whole history to one that
    # has expired or was never built. One script, so no other write lands in between.
    _APPEND_TURN = """
    local turn_size = tonumber(ARGV[2])
    local first, last = 3, 2 + turn_size
    if redis.call('exists', KEYS[1]) == 0 then
        first, last = 3 + turn_size, #ARGV
    end
    for i = first, last do
        redis.call('rpush', KEYS[1], ARGV[i])
    end
    redis.call('expire', KEYS[1], ARGV[1])
    if redis.call('exists', KEYS[2]) == 1 then
        redis.call('expire', KEYS[2], ARGV[1])
    end
    """

    async def append_turn(
        self,
        user_id: UUID,
        conversation_id: UUID,
        turn: list[MessageParam],
        full_history: list[MessageParam],
    ) -> bool:
        """Add one turn's messages to the cached history. False if Redis failed."""

        def encode(messages: list[MessageParam]) -> list[str]:
            return [m.model_dump_json(by_alias=True) for m in messages]

        try:
            await self.redis_client.eval(
                self._APPEND_TURN,
                2,
                self._history_key(user_id, conversation_id),
                self._summary_key(user_id, conversation_id),
                self.conversation_ttl,
                len(turn),
                *encode(turn),
                *encode(full_history),
            )
            return True
        except Exception as e:
            logger.exception(f"Failed to append turn for {conversation_id}: {e}")
            return False

    async def set_conversation_state(
        self,
        user_id: UUID,
        conversation_id: UUID,
        messages: list[MessageParam],
        summary: Optional[str],
    ) -> bool:
        """Write compacted history and summary to Redis."""
        try:
            await self.replace_history(user_id, conversation_id, messages)
            if summary:
                await self.save_summary(user_id, conversation_id, summary)
            else:
                summary_key = self._summary_key(user_id, conversation_id)
                if await self.redis_client.exists(summary_key):
                    await self.redis_client.expire(summary_key, self.conversation_ttl)
            return True
        except Exception as e:
            logger.exception(
                f"Failed to set conversation state for {conversation_id}: {e}"
            )
            return False

    async def get_conversation_state(
        self,
        user_id: UUID,
        conversation_id: UUID,
        db: Optional["AsyncSession"] = None,
        llm: Optional["AIPlatform"] = None,
    ) -> Tuple[list[MessageParam], Optional[str]]:
        """
        Fetch the current conversation working set from Redis.
        Hydrates from Postgres when the cache is cold or behind Postgres (a turn saved
        while Redis was down, F28), compacting before seeding Redis.
        """
        history = await self.get_history(
            user_id=user_id, conversation_id=conversation_id
        )
        summary = await self.get_summary(user_id, conversation_id)

        if history and db is not None:
            if not await self._in_sync_with_postgres(user_id, conversation_id, db):
                # Rebuilt from the full Postgres history, which the old summary
                # would describe a second time.
                history, summary = [], None
                try:
                    await self.redis_client.delete(
                        self._summary_key(user_id, conversation_id)
                    )
                except Exception as e:
                    logger.exception(f"Failed to drop stale summary for {conversation_id}: {e}")

        if not history and db is not None:
            from services.message import get_history as get_postgres_history

            history = await get_postgres_history(db, conversation_id, user_id)
            await self._set_synced(user_id, conversation_id, len(history))
            if history and llm is not None:
                from services.context_budget import compact_history

                compacted = await compact_history(
                    llm=llm,
                    history=history,
                    summary=summary,
                    prompt="",
                )
                await self.set_conversation_state(
                    user_id,
                    conversation_id,
                    compacted.messages,
                    compacted.summary,
                )
                return compacted.messages, compacted.summary
            if history:
                await self.replace_history(user_id, conversation_id, history)

        return history, summary
