import asyncio

from fastapi import Request
from core.config import getSettings
from core.database import SessionLocal
from core.logging import logger
from schemas.chat import (
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    StreamError,
    SuggestionsEvent,
    TextDeltaEvent,
    TitleEvent,
    ToolResultEvent,
    ToolStartEvent,
    sse,
)
from schemas.models import User
from schemas.rag import SourceReference, WebSource
from services import tracing, usage
from services.conversation import get_user_conversation, set_conversation_title
from services.documents import list_conversation_documents
from services.streaming import persist_turn
from services.graph.state import AgentState
from services.titles import generate_title, is_untitled


class TurnTimeout(Exception):
    """The whole turn ran past AGENT_TURN_TIMEOUT_SECONDS."""


async def prepare_context(
    chat_request: ChatRequest,
    current_user: User,
    memory_service,
    llm_service,
) -> AgentState:
    async with SessionLocal() as db:
        conversation_docs = await list_conversation_documents(
            db, current_user.id, chat_request.conversation_id
        )
        indexed_docs = [doc for doc in conversation_docs if doc.status == "indexed"]

        document_ids = [doc.id for doc in indexed_docs]
        document_filenames = [doc.filename for doc in indexed_docs]
        has_documents = len(document_ids) > 0

        history, summary = await memory_service.get_conversation_state(
            user_id=current_user.id,
            conversation_id=chat_request.conversation_id,
            db=db,
            llm=llm_service,
        )

    return {
        "user_id": current_user.id,
        "conversation_id": chat_request.conversation_id,
        "user_message": chat_request.message,
        "has_documents": has_documents,
        "document_ids": document_ids,
        "document_filenames": document_filenames,
        "history": history,
        "context_summary": summary,
        "prepared_history": None,
        "prepared_summary": None,
        "exchanges": [],
        "pending": None,
        "citations": {},
        "final_response": None,
    }


def _add_sources(
    sources: list[SourceReference], new: list[dict]
) -> list[SourceReference]:
    """Several searches in one turn can return the same passage; keep it once."""
    seen = {(s.document_id, s.chunk_index) for s in sources}
    merged = list(sources)
    for raw in new:
        source = SourceReference.model_validate(raw)
        if (source.document_id, source.chunk_index) not in seen:
            seen.add((source.document_id, source.chunk_index))
            merged.append(source)
    return merged


def _add_web_sources(sources: list[WebSource], new: list[dict]) -> list[WebSource]:
    seen = {s.url for s in sources}
    merged = list(sources)
    for raw in new:
        source = WebSource.model_validate(raw)
        if source.url not in seen:
            seen.add(source.url)
            merged.append(source)
    return merged


async def _needs_title(chat_request: ChatRequest, user: User) -> bool:
    try:
        async with SessionLocal() as db:
            conversation = await get_user_conversation(db, chat_request.conversation_id, user.id)
            return is_untitled(conversation.title)
    except Exception:
        logger.exception("Couldn't read the conversation's title")
        return False


async def _events_until(graph_events, deadline: float):
    """The graph's events, ending with TurnTimeout if the deadline passes."""
    loop = asyncio.get_running_loop()
    iterator = graph_events.__aiter__()
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TurnTimeout()
            try:
                yield await asyncio.wait_for(iterator.__anext__(), remaining)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError as exc:
                raise TurnTimeout() from exc
    finally:
        await iterator.aclose()


async def run_graph_stream(
    request: Request,
    chat_request: ChatRequest,
    current_user: User,
):
    # Every model call in this turn adds its tokens here; saved when the turn ends.
    records = usage.start_collecting()
    try:
        with tracing.trace_turn(current_user.id, chat_request.conversation_id, chat_request.message) as trace:
            async for frame in _run_turn(request, chat_request, current_user, trace):
                yield frame
    finally:
        await usage.save(records, current_user.id, chat_request.conversation_id)


async def _run_turn(request: Request, chat_request: ChatRequest, current_user: User, trace):
    app_state = request.app.state
    memory_service = app_state.redis_service
    llm_service = app_state.llm_service
    settings = getSettings()

    initial_state = await prepare_context(
        chat_request=chat_request,
        current_user=current_user,
        memory_service=memory_service,
        llm_service=llm_service,
    )

    config = {
        "configurable": {
            "llm": llm_service,
            "memory_service": memory_service,
            "embedding_service": app_state.embedding_service,
            "vector_store": app_state.vector_store_service,
            "reranker_service": app_state.reranker_service,
            "search_provider": getattr(app_state, "search_provider", None),
            "settings": settings,
        }
    }

    # A new conversation gets a title, generated alongside the reply so it adds no wait.
    title_task = None
    if not initial_state["history"] and await _needs_title(chat_request, current_user):
        title_task = asyncio.create_task(
            generate_title(llm_service, chat_request.message, settings.TITLE_TIMEOUT_SECONDS)
        )

    full_model_response = ""
    sources: list[SourceReference] = []
    web_sources: list[WebSource] = []
    suggestions: list[str] = []
    # If "done" ever arrives without the trimmed history, keep the loaded one, or
    # saving the turn would wipe the conversation's context.
    prepared_messages = initial_state["history"]
    final_context_summary = initial_state["context_summary"]

    deadline = asyncio.get_running_loop().time() + settings.AGENT_TURN_TIMEOUT_SECONDS
    try:
        graph_events = app_state.agent_graph.astream(initial_state, config, stream_mode="custom")
        async for event in _events_until(graph_events, deadline):
            if await request.is_disconnected():
                return

            event_name = event.get("event")

            if event_name == "token":
                chunk = event.get("content", "")
                full_model_response += chunk
                if chunk:
                    yield sse(TextDeltaEvent(delta=chunk))

            elif event_name == "tool-start":
                yield sse(
                    ToolStartEvent(
                        tool_call_id=event["id"],
                        tool_name=event["name"],
                        input=event.get("input") or {},
                    )
                )

            elif event_name == "tool-result":
                yield sse(
                    ToolResultEvent(
                        tool_call_id=event["id"],
                        tool_name=event["name"],
                        is_error=bool(event.get("is_error")),
                    )
                )

            elif event_name == "sources":
                sources = _add_sources(sources, event.get("sources") or [])
                web_sources = _add_web_sources(web_sources, event.get("web_sources") or [])

            elif event_name == "suggestions":
                suggestions = list(event.get("suggestions") or [])
                if suggestions:
                    yield sse(SuggestionsEvent(suggestions=suggestions))

            elif event_name == "done":
                prepared_messages = event.get("prepared_messages", prepared_messages)
                final_context_summary = event.get(
                    "context_summary", final_context_summary
                )

        if await request.is_disconnected():
            return

        if sources or web_sources:
            yield sse(SourcesEvent(sources=sources, web_sources=web_sources))

        if title_task is not None:
            title = await title_task  # never raises; bounded by TITLE_TIMEOUT_SECONDS
            title_task = None
            try:
                async with SessionLocal() as db:
                    await set_conversation_title(db, chat_request.conversation_id, current_user.id, title)
                yield sse(TitleEvent(title=title))
            except Exception:
                logger.exception("Couldn't save the conversation's title")

        yield sse(DoneEvent())
        trace.update(output=tracing.clip(full_model_response), metadata={"sources": len(sources) + len(web_sources)})

        if await request.is_disconnected():
            return

        await persist_turn(
            memory_service=memory_service,
            llm=llm_service,
            user_id=current_user.id,
            conversation_id=chat_request.conversation_id,
            user_message=chat_request.message,
            model_response=full_model_response,
            prepared_messages=prepared_messages,
            context_summary=final_context_summary,
            sources=sources,
            web_sources=web_sources,
            suggestions=suggestions,
        )

    except TurnTimeout:
        logger.warning(
            "Turn for %s ran past %ss", chat_request.conversation_id, settings.AGENT_TURN_TIMEOUT_SECONDS
        )
        trace.update(level="ERROR", status_message="turn timed out")
        yield sse(
            ErrorEvent(
                error=StreamError(
                    code="TURN_TIMEOUT",
                    message="That took too long, so it was stopped. Please try again, or ask a simpler question.",
                )
            )
        )
    except Exception:
        logger.exception(f"Stream Generation Failed for {chat_request.conversation_id}")
        trace.update(level="ERROR", status_message="stream failed")
        yield sse(
            ErrorEvent(
                error=StreamError(
                    code="STREAM_GENERATION_FAILED",
                    message="Failed to generate a response. Please try again.",
                )
            )
        )
    finally:
        if title_task is not None and not title_task.done():
            title_task.cancel()
