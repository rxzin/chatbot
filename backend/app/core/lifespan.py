from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import getSettings
from core.logging import log_event, logger, stop_logging_listener
from services.audit import AuditLogWriter
from services.embeddings import MistralEmbeddingService
from services.fallback import FallbackLLM
from services.graph.graph import graph_builder
from services.graph.prompts import BASE_PROMPT
from services.tracing import init_tracing, shutdown_tracing
from services.memory import RedisMemoryService
from services.mistral import MistralProvider, is_transient_error
from services.reranker import RerankerService
from services.search import build_search_provider
from services.vector_store import PineconeVectorStoreService

SYSTEM_PROMPT = BASE_PROMPT


def _build_llm(settings) -> FallbackLLM:
    return FallbackLLM(
        primary=MistralProvider(
            api_key=settings.MISTRAL_API_KEY,
            model=settings.MISTRAL_MODEL,
            system_prompt=SYSTEM_PROMPT,
        ),
        fallback=MistralProvider(
            api_key=settings.MISTRAL_API_KEY,
            model=settings.MISTRAL_FALLBACK_MODEL,
            system_prompt=SYSTEM_PROMPT,
        ),
        should_fallback=is_transient_error,
    )


def _use_fake_services(app: FastAPI):
    """
    Install the in-process stand-ins. Nothing here opens a network connection.

    Returns the vector store and reranker so shutdown closes them like the real ones.
    """
    from services.fakes import (
        FakeEmbeddingService,
        FakeLLM,
        FakeReranker,
        FakeVectorStore,
    )

    vector_store = FakeVectorStore()
    reranker = FakeReranker()
    app.state.llm_service = FakeLLM(system_prompt=SYSTEM_PROMPT)
    app.state.embedding_service = FakeEmbeddingService()
    app.state.vector_store_service = vector_store
    app.state.reranker_service = reranker
    app.state.search_provider = None
    return vector_store, reranker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared services on startup and release them on shutdown."""
    settings = getSettings()
    redis_service = None
    reranker_service = None
    pinecone_service = None
    audit_writer = AuditLogWriter()
    try:
        audit_writer.start()
        app.state.audit_writer = audit_writer

        redis_service = RedisMemoryService()
        await redis_service.redis_client.ping()
        app.state.redis_service = redis_service

        if settings.EXTERNAL_SERVICES == "fake":
            pinecone_service, reranker_service = _use_fake_services(app)
        else:
            app.state.llm_service = _build_llm(settings)
            app.state.embedding_service = MistralEmbeddingService(
                api_key=settings.MISTRAL_API_KEY,
                model=settings.MISTRAL_EMBED_MODEL,
            )

            pinecone_service = PineconeVectorStoreService()
            await pinecone_service.initialize()
            app.state.vector_store_service = pinecone_service

            reranker_service = RerankerService()
            app.state.reranker_service = reranker_service

            app.state.search_provider = build_search_provider(
                settings.SEARCH_PROVIDER, settings.EXA_API_KEY
            )

        app.state.agent_graph = graph_builder()
        # Fake mode never traces, whatever keys are set.
        tracing_enabled = (
            init_tracing(settings) if settings.EXTERNAL_SERVICES == "live" else False
        )
        log_event(
            event="app.lifecycle.startup.succeeded",
            message="Application services initialized",
            external_services=settings.EXTERNAL_SERVICES,
            redis_connected=True,
            vector_store_initialized=True,
            reranker_initialized=True,
            web_search_enabled=app.state.search_provider is not None,
            tracing_enabled=tracing_enabled,
        )
    except Exception:
        logger.exception(
            "Application startup failed",
            extra={"event": "app.lifecycle.startup.failed"},
        )
        raise

    yield

    try:
        await audit_writer.stop()
        shutdown_tracing()

        search_provider = getattr(app.state, "search_provider", None)
        if search_provider is not None:
            await search_provider.close()

        if pinecone_service is not None:
            await pinecone_service.close()
            log_event(
                event="app.lifecycle.shutdown.pinecone.succeeded",
                message="Pinecone client closed on shutdown",
            )

        if reranker_service is not None:
            await reranker_service.close()
            log_event(
                event="app.lifecycle.shutdown.reranker.succeeded",
                message="Reranker client closed on shutdown",
            )
        if redis_service is not None:
            await redis_service.redis_client.aclose()
            log_event(
                event="app.lifecycle.shutdown.redis.succeeded",
                message="Redis connection closed on shutdown",
            )
    finally:
        stop_logging_listener()
