"""Chat calls wait out a brief Mistral rate limit instead of failing straight over."""

import httpx2
from mistralai.client import Mistral
from mistralai.client.utils import RetryConfig

from services.mistral import MistralProvider

TURN = dict(
    prompt="hi",
    history=[],
    context_summary=None,
    instructions="",
    exchanges=[],
    tools=[],
    allow_tools=False,
)


class _Message:
    content = "hello"


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]
    usage = None


class _EmptyStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _FakeChat:
    def __init__(self):
        self.calls: list[dict] = []

    async def complete_async(self, **kwargs):
        self.calls.append(kwargs)
        return _Response()

    async def stream_async(self, **kwargs):
        self.calls.append(kwargs)
        return _EmptyStream()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


def _provider() -> tuple[MistralProvider, _FakeChat]:
    provider = MistralProvider(api_key="test", model="m")
    fake = _FakeClient()
    provider._client = fake
    return provider, fake.chat


async def test_complete_text_passes_a_retry_config():
    provider, chat = _provider()

    assert await provider._complete_text("sys", "hi", 10) == "hello"

    assert isinstance(chat.calls[0]["retries"], RetryConfig)


async def test_complete_text_without_retry_passes_no_retry_config():
    provider, chat = _provider()

    await provider.complete_text("sys", "hi", 10, retry=False)

    assert chat.calls[0]["retries"] is None


async def test_stream_turn_passes_a_retry_config():
    provider, chat = _provider()

    [_ async for _ in provider.stream_turn(**TURN)]

    assert isinstance(chat.calls[0]["retries"], RetryConfig)


async def test_complete_text_retries_after_a_429():
    seen: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(1)
        if len(seen) == 1:
            return httpx2.Response(
                429,
                headers={"retry-after-ms": "1"},
                json={"message": "Rate limit exceeded", "code": "1300"},
            )
        return httpx2.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "model": "m",
                "created": 1,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "after retry"},
                    }
                ],
            },
        )

    provider = MistralProvider(api_key="test", model="m")
    provider._client = Mistral(
        api_key="test",
        async_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )

    assert await provider._complete_text("sys", "hi", 10) == "after retry"
    assert len(seen) == 2
