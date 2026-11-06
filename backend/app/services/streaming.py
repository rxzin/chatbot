from typing import Optional
from uuid import UUID

from core.database import SessionLocal
from core.logging import logger
from schemas.chat import MessageParam, SourcesPart, TextPart
from schemas.rag import SourceReference
from services.context_budget import compact_history
from services.base import AIPlatform
from services.memory import RedisMemoryService
from services.message import save_turn as save_postgres_turn


def _model_parts(text: str, sources: Optional[list[SourceReference]]) -> list[dict]:
    """The reply's display parts, in the order they were streamed."""
    parts: list = [TextPart(text=text)]
    if sources:
        parts.append(SourcesPart(sources=sources))
    return [part.model_dump(by_alias=True, mode="json") for part in parts]


async def persist_turn(
    *,
    memory_service: RedisMemoryService,
    llm: AIPlatform,
    user_id: UUID,
    conversation_id: UUID,
    user_message: str,
    model_response: str,
    prepared_messages: list[MessageParam],
    context_summary: Optional[str] = None,
    sources: Optional[list[SourceReference]] = None,
) -> None:
    if not model_response:
        return

    new_history = [
        *prepared_messages,
        MessageParam(role="user", content=user_message),
        MessageParam(role="model", content=model_response),
    ]
    compacted = await compact_history(
        llm=llm,
        history=new_history,
        summary=context_summary,
        prompt="",
    )

    redis_saved = await memory_service.set_conversation_state(
        user_id=user_id,
        conversation_id=conversation_id,
        messages=compacted.messages,
        summary=compacted.summary,
    )

    postgres_saved = False
    async with SessionLocal() as db:
        postgres_saved = await save_postgres_turn(
            db,
            conversation_id,
            user_id,
            user_message,
            model_response,
            _model_parts(model_response, sources),
        )

    if redis_saved and postgres_saved:
        logger.info(f"Saved turn for user {user_id}, conversation {conversation_id}")
    elif redis_saved:
        logger.warning(
            "Turn saved to Redis but failed to persist in Postgres for conversation %s",
            conversation_id,
        )
    elif postgres_saved:
        logger.warning(
            "Turn saved to Postgres but failed to update Redis context for conversation %s",
            conversation_id,
        )
    else:
        logger.warning("Stream completed but failed to persist turn for session")
