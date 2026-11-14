"""The stand-ins for Mistral, Pinecone and Cohere used by tests and mocked benchmarks."""

from uuid import uuid4

from core.config import getSettings
from schemas.chat import MessageParam
from services.fakes import (
    FakeEmbeddingService,
    FakeLLM,
    FakeReranker,
    FakeVectorStore,
)
from services.vector_store import VectorChunk


def _chunk(user_id, document_id, index=0) -> VectorChunk:
    return VectorChunk(
        id=f"{document_id}:{index}",
        document_id=document_id,
        user_id=user_id,
        filename="notes.txt",
        page=None,
        chunk_index=index,
        content=f"chunk {index}",
        embedding=[0.1],
        parent_id=f"{document_id}:p",
        parent_content="parent",
    )


async def _stream(llm, history):
    return [
        chunk
        async for chunk in llm.stream_turn(
            prompt="hi",
            history=history,
            context_summary=None,
            instructions="",
            exchanges=[],
            tools=[],
            allow_tools=True,
        )
    ]


async def test_fake_llm_reports_history_length_and_token_count(monkeypatch):
    settings = getSettings()
    monkeypatch.setattr(settings, "FAKE_LLM_TOKEN_COUNT", 4)
    monkeypatch.setattr(settings, "FAKE_LLM_TOKEN_DELAY_MS", 0)
    history = [
        MessageParam(role="user", content="a"),
        MessageParam(role="model", content="b"),
    ]

    chunks = await _stream(FakeLLM(), history)

    assert chunks == ["fake-reply h=2 ", "tok ", "tok ", "tok "]
    assert await FakeLLM().complete_text("system", "prompt", 10) == "Fake Title"


async def test_fake_embeddings_are_deterministic_and_sized():
    service = FakeEmbeddingService()
    dimension = getSettings().EMBEDDING_DIMENSION

    first, second = await service.embed_texts(["alpha", "beta"])

    assert len(first) == len(second) == dimension
    assert first != second
    assert await service.embed_query("alpha") == first
    assert await service.embed_query("") == []


async def test_fake_vector_store_scopes_by_user_and_document():
    store = FakeVectorStore()
    owner, stranger = uuid4(), uuid4()
    doc_a, doc_b = uuid4(), uuid4()
    await store.add_chunks(
        [_chunk(owner, doc_a, 0), _chunk(owner, doc_a, 1), _chunk(owner, doc_b, 0)]
    )

    everything = await store.query(user_id=owner, query_embedding=[0.1], top_k=10)
    only_b = await store.query(
        user_id=owner, query_embedding=[0.1], top_k=10, document_ids=[doc_b]
    )
    capped = await store.query(user_id=owner, query_embedding=[0.1], top_k=1)
    other_user = await store.query(user_id=stranger, query_embedding=[0.1], top_k=10)

    assert len(everything) == 3
    assert {r.score for r in everything} == {0.9}
    assert [r.document_id for r in only_b] == [doc_b]
    assert len(capped) == 1
    assert other_user == []

    await store.delete_document(user_id=owner, document_id=doc_a)
    remaining = await store.query(user_id=owner, query_embedding=[0.1], top_k=10)
    assert [r.document_id for r in remaining] == [doc_b]
    await store.close()


async def test_fake_reranker_scores_every_document():
    reranker = FakeReranker()

    assert await reranker.rerank("q", ["a", "b", "c"]) == [0.9, 0.9, 0.9]
    assert await reranker.rerank("q", []) == []
    await reranker.close()
