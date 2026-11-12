"""
In-process stand-ins for Mistral, Pinecone and Cohere.

Used when EXTERNAL_SERVICES=fake (tests and mocked benchmarks), so the app starts and
answers without any network access, at no cost, and with a predictable reply shape.
"""

import asyncio
import hashlib
from typing import AsyncGenerator, Optional, Sequence
from uuid import UUID

from core.config import getSettings
from schemas.chat import MessageParam
from services.base import AIPlatform, ToolExchange, ToolSpec, TurnChunk
from services.embeddings import EmbeddingService
from services.vector_store import VectorChunk, VectorSearchResult, VectorStoreService

_FAKE_SCORE = 0.9


class FakeLLM(AIPlatform):
    """
    Streams a fixed-shape reply and never asks for a tool.

    The first chunk carries the number of history messages it was given, so a caller
    can tell from the reply alone whether earlier turns reached the model.
    """

    async def stream_turn(
        self,
        *,
        prompt: str,
        history: Sequence[MessageParam],
        context_summary: Optional[str],
        instructions: str,
        exchanges: Sequence[ToolExchange],
        tools: Sequence[ToolSpec],
        allow_tools: bool,
    ) -> AsyncGenerator[TurnChunk, None]:
        settings = getSettings()
        delay = settings.FAKE_LLM_TOKEN_DELAY_MS / 1000

        yield f"fake-reply h={len(history)} "
        for _ in range(settings.FAKE_LLM_TOKEN_COUNT - 1):
            await asyncio.sleep(delay)
            yield "tok "

    async def _complete_text(
        self, system_instruction: str, prompt: str, max_output_tokens: int
    ) -> str:
        return "Fake Title"


class FakeEmbeddingService(EmbeddingService):
    """The same text always gets the same vector; different texts get different ones."""

    def _embed(self, text: str) -> list[float]:
        dimension = getSettings().EMBEDDING_DIMENSION
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255 for i in range(dimension)]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text) if text else []


class FakeVectorStore(VectorStoreService):
    """Chunks kept in memory. A query returns the user's chunks; it does not rank them."""

    def __init__(self) -> None:
        self.chunks: dict[tuple[UUID, UUID], list[VectorChunk]] = {}

    async def add_chunks(self, chunks: list[VectorChunk]) -> None:
        for chunk in chunks:
            self.chunks.setdefault((chunk.user_id, chunk.document_id), []).append(chunk)

    async def query(
        self,
        *,
        user_id: UUID,
        query_embedding: list[float],
        top_k: int,
        document_ids: Optional[list[UUID]] = None,
    ) -> list[VectorSearchResult]:
        if not query_embedding:
            return []
        matches = [
            chunk
            for (owner, document_id), chunks in self.chunks.items()
            if owner == user_id and (not document_ids or document_id in document_ids)
            for chunk in chunks
        ]
        return [
            VectorSearchResult(
                document_id=chunk.document_id,
                filename=chunk.filename,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=_FAKE_SCORE,
                parent_id=chunk.parent_id,
                parent_content=chunk.parent_content,
            )
            for chunk in matches[:top_k]
        ]

    async def delete_document(self, *, user_id: UUID, document_id: UUID) -> None:
        self.chunks.pop((user_id, document_id), None)

    async def close(self) -> None:
        self.chunks.clear()


class FakeReranker:
    """Scores every document as relevant, so nothing is filtered out."""

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [_FAKE_SCORE] * len(documents)

    async def close(self) -> None:
        return None
