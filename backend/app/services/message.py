from typing import Optional
from uuid import UUID

from sqlalchemy import select
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
) -> bool:
    try:
        db.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                parts=[{"type": "text", "text": user_message}],
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
