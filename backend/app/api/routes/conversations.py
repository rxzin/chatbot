from uuid import UUID

from fastapi import APIRouter, Depends, status, Security
from sqlalchemy.ext.asyncio import AsyncSession

from auth.service import get_current_active_user
from core.database import get_db
from core.idempotency import idempotency_key
from schemas.models import User
from schemas.schema import ConversationCreate, ConversationResponse, MessageResponse
from services.conversation import (
    create_conversation,
    get_user_conversation,
    list_user_conversations,
)
from services.message import list_messages

conv_router = APIRouter()


@conv_router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(
        get_current_active_user, scopes=["conversations:read"]
    ),
):
    return await list_user_conversations(db, current_user.id)


@conv_router.get(
    "/conversations/{conversation_id}", response_model=ConversationResponse
)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(
        get_current_active_user, scopes=["conversations:read"]
    ),
):
    return await get_user_conversation(db, conversation_id, current_user.id)


@conv_router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_conversation_messages(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(
        get_current_active_user, scopes=["conversations:read"]
    ),
):
    return await list_messages(db, conversation_id, current_user.id)


@conv_router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationResponse,
)
async def start_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(
        get_current_active_user, scopes=["conversations:create"]
    ),
    key: str | None = Depends(idempotency_key),
):
    """Create a new conversation row for the authenticated user."""
    conversation = await create_conversation(
        db, user_id=current_user.id, title=body.title, idempotency_key=key
    )
    return conversation
