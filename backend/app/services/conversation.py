from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import NotFoundError
from schemas.models import Conversation


async def create_conversation(
    db: AsyncSession,
    user_id: UUID,
    title: str = "New Conversation",
    idempotency_key: str | None = None,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id, title=title, idempotency_key=idempotency_key
    )
    db.add(conversation)
    try:
        await db.commit()
    except IntegrityError:
        # The unique index on (user_id, idempotency_key): this key already made one.
        await db.rollback()
        if idempotency_key is None:
            raise
        existing = (
            await db.execute(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    await db.refresh(conversation)
    return conversation


async def list_user_conversations(
    db: AsyncSession, user_id: UUID
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_conversation(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


async def set_conversation_title(
    db: AsyncSession, conversation_id: UUID, user_id: UUID, title: str
) -> None:
    conversation = await get_user_conversation(db, conversation_id, user_id)
    conversation.title = title[:100]
    await db.commit()
