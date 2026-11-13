from fastapi import APIRouter, Request, Depends, Security
from fastapi.responses import StreamingResponse
from schemas.chat import (
    ChatRequest,
    ChatStreamEvent,
    DoneEvent,
    SourcesEvent,
    SuggestionsEvent,
    TextDeltaEvent,
    sse,
)
from core.config import getSettings
from core.errors import ConflictError, TooManyRequestsError
from core.logging import get_request_id, log_event, set_request_context
from sqlalchemy.ext.asyncio import AsyncSession
from auth.service import get_current_active_user
from core.database import get_db
from core.idempotency import idempotency_key
from schemas.models import User
from services.conversation import get_user_conversation
from services.graph.runner import run_graph_stream
from services.message import get_turn_by_key

chat_router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _replay_stream(model_message):
    """A saved reply as a stream: text, then sources and suggestions if stored, then done."""
    yield sse(TextDeltaEvent(delta=model_message.content))
    for part in model_message.parts or []:
        if part.get("type") == "sources":
            yield sse(SourcesEvent.model_validate(part))
        elif part.get("type") == "suggestions":
            yield sse(SuggestionsEvent.model_validate(part))
    yield sse(DoneEvent())


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
    key: str | None = Depends(idempotency_key),
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

    inflight_key = None
    if key is not None:
        # 1. Already answered: replay it. No model call, no quota use, no writes.
        saved = await get_turn_by_key(db, chat_request.conversation_id, key)
        if saved is not None:
            log_event(
                event="chat.idempotency.replayed",
                message="Chat turn replayed from a saved Idempotency-Key",
                conversation_id=str(chat_request.conversation_id),
            )
            return StreamingResponse(
                _replay_stream(saved[1]),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )
        # 2. Being answered right now by another request with this key.
        inflight_key = f"idem:chat:{chat_request.conversation_id}:{key}"
        acquired = await request.app.state.redis_service.acquire_inflight(
            inflight_key, int(getSettings().AGENT_TURN_TIMEOUT_SECONDS) + 30
        )
        if acquired is False:
            raise ConflictError("This message is already being processed.")
        if acquired is None:  # Redis is down: the unique index still holds
            inflight_key = None

    try:
        return await _start_stream(
            request, chat_request, current_user, key, inflight_key
        )
    except BaseException:
        # Refused before the stream began (quota): nothing will release the lock.
        if inflight_key is not None:
            await request.app.state.redis_service.release_inflight(inflight_key)
        raise


async def _start_stream(
    request: Request,
    chat_request: ChatRequest,
    current_user: User,
    key: str | None,
    inflight_key: str | None,
):
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
            idempotency_key=key,
            inflight_key=inflight_key,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
