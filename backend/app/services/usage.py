"""
Token usage per model call.

The provider records every call (model, tokens) into a collector bound to the current
chat turn, tagged with a purpose such as "agent" or "title". The runner saves the batch
when the turn ends. Calls made outside a turn are not recorded.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional
from uuid import UUID

from core.database import SessionLocal
from core.logging import logger
from schemas.models import LlmUsage


@dataclass
class UsageRecord:
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int


# The list is shared by reference, so tasks started during the turn (which copy the
# context) add to the same collector.
_collector: ContextVar[Optional[list[UsageRecord]]] = ContextVar("llm_usage", default=None)
_purpose: ContextVar[str] = ContextVar("llm_purpose", default="other")


def start_collecting() -> list[UsageRecord]:
    records: list[UsageRecord] = []
    _collector.set(records)
    return records


def current_purpose() -> str:
    return _purpose.get()


@contextmanager
def purpose(name: str) -> Iterator[None]:
    """Tag model calls made inside this block, e.g. purpose("title")."""
    token = _purpose.set(name)
    try:
        yield
    finally:
        _purpose.reset(token)


def record(model: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> None:
    records = _collector.get()
    if records is None:
        return
    records.append(
        UsageRecord(
            purpose=_purpose.get(),
            model=model,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
        )
    )


async def save(records: list[UsageRecord], user_id: UUID, conversation_id: Optional[UUID]) -> None:
    """Write a turn's records. Failures are logged, never raised: usage is bookkeeping."""
    if not records:
        return
    try:
        async with SessionLocal() as db:
            db.add_all(
                LlmUsage(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    purpose=r.purpose,
                    model=r.model,
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                )
                for r in records
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to save token usage")
