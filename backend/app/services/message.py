from typing import Optional
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.chat import MessageParam
from schemas.models import Message
from services.conversation import get_user_conversation


async def list_messages(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> list[Message]:
    await get_user_conversation(db, conversation_id, user_id)

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def get_history(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> list[MessageParam]:
    rows = await list_messages(db, conversation_id, user_id)
    return [
        MessageParam(role=row.role, content=row.content, timestamp=row.created_at)
        for row in rows
    ]


async def save_turn(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    user_message: str,
    model_response: str,
    model_parts: Optional[list[dict]] = None,
    idempotency_key: Optional[str] = None,
) -> bool:
    try:
        db.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                parts=[{"type": "text", "text": user_message}],
                idempotency_key=idempotency_key,
            )
        )
        db.add(
            Message(
                conversation_id=conversation_id,
                role="model",
                content=model_response,
                parts=model_parts or [{"type": "text", "text": model_response}],
            )
        )
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        return False


async def get_turn_by_key(
    db: AsyncSession, conversation_id: UUID, key: str
) -> tuple[Message, Message] | None:
    """The user message saved with this Idempotency-Key and the model reply after it."""
    user_message = (
        await db.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if user_message is None:
        return None
    # Both rows of a turn share one commit time, so the id breaks the tie.
    model_message = (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "model",
                tuple_(Message.created_at, Message.id)
                > tuple_(user_message.created_at, user_message.id),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if model_message is None:
        return None
    return user_message, model_message
