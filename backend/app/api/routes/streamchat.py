from fastapi import APIRouter, Request, Depends, Security
from fastapi.responses import StreamingResponse
from schemas.chat import ChatRequest, ChatStreamEvent
from core.config import getSettings
from core.errors import TooManyRequestsError
from core.logging import get_request_id, log_event, set_request_context
from sqlalchemy.ext.asyncio import AsyncSession
from auth.service import get_current_active_user
from core.database import get_db
from schemas.models import User
from services.conversation import get_user_conversation
from services.graph.runner import run_graph_stream

chat_router = APIRouter()


@chat_router.post(
    "/chat",
    status_code=200,
    responses={
        200: {
            # Documents the event shape; the body is text/event-stream, one
            # "data: <ChatStreamEvent>" line per event, ending with done or error.
            "model": ChatStreamEvent,
            "description": "Server-Sent Events stream of ChatStreamEvent objects.",
        }
    },
)
async def chat_stream_endpoint(
    request: Request,
    chat_request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["ai:chat"]),
):
    """Stream a chat response via the LangGraph Intelligent Router."""
    set_request_context(
        request_id=getattr(request.state, "request_id", get_request_id()),
        user_id=str(current_user.id),
    )
    log_event(
        event="chat.stream.request.started",
        message="Chat streaming request received",
        conversation_id=str(chat_request.conversation_id),
        path="/chat",
    )

    # Ensure conversation belongs to user before starting graph
    await get_user_conversation(db, chat_request.conversation_id, current_user.id)
    log_event(
        event="chat.conversation.authorize.succeeded",
        message="Conversation ownership validated for chat stream",
        conversation_id=str(chat_request.conversation_id),
    )

    # Counted before any model call, so a refused message costs nothing.
    limit = getSettings().CHAT_DAILY_LIMIT_PER_USER
    if limit > 0 and not await request.app.state.redis_service.consume_daily_quota(
        current_user.id, action="chat", limit=limit, fail_open=True
    ):
        raise TooManyRequestsError(
            f"You've reached today's limit of {limit} messages. "
            "It resets at midnight UTC."
        )

    log_event(
        event="chat.stream.response.started",
        message="Chat stream response started",
        conversation_id=str(chat_request.conversation_id),
    )
    return StreamingResponse(
        run_graph_stream(
            request=request,
            chat_request=chat_request,
            current_user=current_user,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
