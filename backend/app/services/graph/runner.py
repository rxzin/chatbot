import json
from fastapi import Request
from core.config import getSettings
from core.database import SessionLocal
from core.logging import logger
from schemas.chat import ChatStreamResponse, ChatStreamDelta, ChatRequest
from schemas.models import User
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
        "route": "chat",  # Placeholder
        "route_reason": "",
        "grounded_prompt": None,
        "sources": None,
        "final_response": None,
    }


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
            "settings": settings,
        }
    }

    full_model_response = ""
    buffered_sources = None
    # Nodes that don't trim the history (bug_report) send "done" without it.
    # Keep the loaded history then, or saving the turn would wipe the context.
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
                delta = ChatStreamDelta(content=chunk)
                response = ChatStreamResponse(success=True, data=delta)
                yield f"data: {response.model_dump_json(by_alias=True)}\n\n"

            elif event_name == "sources":
                buffered_sources = event.get("sources")

            elif event_name == "done":
                prepared_messages = event.get("prepared_messages", prepared_messages)
                final_context_summary = event.get(
                    "context_summary", final_context_summary
                )

        if await request.is_disconnected():
            return

        final_delta = ChatStreamDelta(
            content="", finishReason="STOP", sources=buffered_sources
        )
        final_response = ChatStreamResponse(success=True, data=final_delta)
        yield f"data: {final_response.model_dump_json(by_alias=True)}\n\n"

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
        )

    except Exception:
        logger.exception(f"Stream Generation Failed for {chat_request.conversation_id}")
        error_data = {
            "success": False,
            "error": {
                "code": "STREAM_GENERATION_FAILED",
                "message": "Failed to generate a response. Please try again.",
            },
        }
        yield f"data: {json.dumps(error_data)}\n\n"
