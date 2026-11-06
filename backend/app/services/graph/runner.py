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
    TextDeltaEvent,
    ToolResultEvent,
    ToolStartEvent,
    sse,
)
from schemas.models import User
from schemas.rag import SourceReference, WebSource
from services.documents import list_conversation_documents
from services.streaming import persist_turn
from services.graph.state import AgentState


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


async def run_graph_stream(
    request: Request,
    chat_request: ChatRequest,
    current_user: User,
):
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

    full_model_response = ""
    sources: list[SourceReference] = []
    web_sources: list[WebSource] = []
    # If "done" ever arrives without the trimmed history, keep the loaded one, or
    # saving the turn would wipe the conversation's context.
    prepared_messages = initial_state["history"]
    final_context_summary = initial_state["context_summary"]

    try:
        async for event in app_state.agent_graph.astream(
            initial_state, config, stream_mode="custom"
        ):
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

            elif event_name == "done":
                prepared_messages = event.get("prepared_messages", prepared_messages)
                final_context_summary = event.get(
                    "context_summary", final_context_summary
                )

        if await request.is_disconnected():
            return

        if sources or web_sources:
            yield sse(SourcesEvent(sources=sources, web_sources=web_sources))
        yield sse(DoneEvent())

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
        )

    except Exception:
        logger.exception(f"Stream Generation Failed for {chat_request.conversation_id}")
        yield sse(
            ErrorEvent(
                error=StreamError(
                    code="STREAM_GENERATION_FAILED",
                    message="Failed to generate a response. Please try again.",
                )
            )
        )
