from abc import ABC, abstractmethod

from mistralai.client import Mistral
from mistralai.client.utils import BackoffStrategy, RetryConfig

# Child chunks are at most 200 tokens, so a batch stays near 6,400 tokens.
_BATCH_SIZE = 32
_TIMEOUT_MS = 60_000


def retry_for(max_elapsed_ms: int) -> RetryConfig:
    """Back off on 429 and 5xx, honoring Retry-After when the API sends it."""
    return RetryConfig(
        "backoff",
        BackoffStrategy(
            initial_interval=1_000,
            max_interval=60_000,
            exponent=2.0,
            max_elapsed_time=max_elapsed_ms,
        ),
        retry_connection_errors=True,
    )


# Ingestion runs in the background and can wait out a rate-limit window.
_INGEST_RETRY = retry_for(300_000)
# A query blocks a live chat reply, so it gives up much sooner.
_QUERY_RETRY = retry_for(15_000)


class EmbeddingService(ABC):
    """
    Vectors from different models are not comparable, so this has no runtime fallback.
    Changing the model means a new Pinecone index and re-embedding every document.
    """

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks, returning one vector per text in the same order."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query."""


class MistralEmbeddingService(EmbeddingService):
    def __init__(self, api_key: str, model: str):
        self.model = model
        self._client = Mistral(api_key=api_key, timeout_ms=_TIMEOUT_MS)

    async def _embed_batch(
        self, texts: list[str], retries: RetryConfig
    ) -> list[list[float]]:
        response = await self._client.embeddings.create_async(
            model=self.model, inputs=texts, retries=retries
        )
        return [item.embedding for item in response.data]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        # Sequential on purpose: concurrent batches would burn the per-minute request
        # limit that chat replies also depend on.
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            embeddings.extend(await self._embed_batch(batch, _INGEST_RETRY))
        return embeddings

    async def embed_query(self, text: str) -> list[float]:
        if not text:
            return []
        embeddings = await self._embed_batch([text], _QUERY_RETRY)
        return embeddings[0]
