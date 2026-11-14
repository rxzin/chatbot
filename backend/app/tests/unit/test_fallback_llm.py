"""Switching to the fallback model when the primary fails."""

import httpx2
import pytest

from services.fallback import FallbackLLM
from services.mistral import is_transient_error
from support.fakes import ScriptedLLM

TURN = dict(
    prompt="hi",
    history=[],
    context_summary=None,
    instructions="",
    exchanges=[],
    tools=[],
    allow_tools=True,
)


class FailsMidReply(ScriptedLLM):
    async def stream_turn(self, **kwargs):
        yield "partial "
        raise RuntimeError("connection dropped")


async def collect(llm) -> list:
    return [chunk async for chunk in llm.stream_turn(**TURN)]


async def test_failure_before_any_output_uses_the_fallback():
    fallback = ScriptedLLM([["from ", "fallback"]])
    llm = FallbackLLM(ScriptedLLM([RuntimeError("down")]), fallback, lambda e: True)

    assert await collect(llm) == ["from ", "fallback"]


async def test_failure_after_output_is_not_retried():
    fallback = ScriptedLLM([["from fallback"]])
    llm = FallbackLLM(FailsMidReply([]), fallback, lambda e: True)

    with pytest.raises(RuntimeError, match="connection dropped"):
        await collect(llm)
    assert fallback.calls == []


async def test_error_that_should_not_fall_back_propagates():
    fallback = ScriptedLLM([["from fallback"]])
    llm = FallbackLLM(ScriptedLLM([ValueError("bad")]), fallback, lambda e: False)

    with pytest.raises(ValueError):
        await collect(llm)
    assert fallback.calls == []


async def test_complete_text_falls_back_too():
    llm = FallbackLLM(
        ScriptedLLM([], completion=RuntimeError("down")),
        ScriptedLLM([], completion="from fallback"),
        lambda e: True,
    )

    assert await llm.complete_text("system", "prompt", 10) == "from fallback"


def test_which_errors_count_as_transient():
    assert is_transient_error(httpx2.ConnectError("x")) is True
    assert is_transient_error(ValueError()) is False
