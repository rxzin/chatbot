from __future__ import annotations

from typing import Optional
from uuid import UUID

from core.config import getSettings
from schemas.rag import SourceReference
from services.embeddings import EmbeddingService
from services.reranker import RerankerService
from services.vector_store import VectorSearchResult, VectorStoreService


def _snippet(text: str, max_length: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1].rstrip()}..."


def to_sources(results: list[VectorSearchResult]) -> list[SourceReference]:
    return [
        SourceReference(
            documentId=result.document_id,
            filename=result.filename,
            page=result.page,
            chunkIndex=result.chunk_index,
            snippet=_snippet(result.content),
            score=result.score,
        )
        for result in results
    ]


async def retrieve_context(
    *,
    embedding_service: EmbeddingService,
    reranker_service: RerankerService,
    vector_store: VectorStoreService,
    user_id: UUID,
    message: str,
    top_k: int,
    document_ids: Optional[list[UUID]] = None,
) -> list[VectorSearchResult]:
    if document_ids is not None and len(document_ids) == 0:
        return []

    settings = getSettings()
    
    # 1. Initial Vector Retrieval
    query_embedding = await embedding_service.embed_query(message)
    initial_results = await vector_store.query(
        user_id=user_id,
        query_embedding=query_embedding,
        top_k=settings.RAG_INITIAL_TOP_K,
        document_ids=document_ids,
    )

    if not initial_results:
        return []

    # 2. Reranking
    docs_to_rerank = [res.content for res in initial_results]
    scores = await reranker_service.rerank(message, docs_to_rerank)
    
    # Assign new scores and sort descending
    for res, score in zip(initial_results, scores):
        res.score = float(score)
        
    initial_results.sort(key=lambda x: x.score, reverse=True)

    # Filter out extremely low confidence reranker scores if needed
    # initial_results = [res for res in initial_results if res.score >= settings.RAG_RELEVANCE_THRESHOLD]

    # 3. Deduplicate Parent Chunks
    final_results = []
    seen_parents = set()
    
    for res in initial_results:
        parent_key = f"{res.document_id}:{res.parent_id}"
        if parent_key not in seen_parents:
            seen_parents.add(parent_key)
            final_results.append(res)
            if len(final_results) >= top_k:
                break
                
    return final_results
