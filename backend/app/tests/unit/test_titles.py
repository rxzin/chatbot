"""Conversation titles."""

import asyncio

from services.titles import fallback_title, generate_title, is_untitled
from support.fakes import ScriptedLLM

MESSAGE = "help me plan a trip"


class SlowLLM(ScriptedLLM):
    async def _complete_text(self, system_instruction, prompt, max_output_tokens):
        await asyncio.sleep(1)
        return "Too Late"


def test_is_untitled():
    assert is_untitled(None) is True
    assert is_untitled("") is True
    assert is_untitled("New Conversation") is True
    assert is_untitled("Trip to Paris") is False


def test_fallback_title_keeps_at_most_six_words():
    title = fallback_title("one two three four five six seven eight")

    assert title == "one two three four five six"


def test_fallback_title_for_an_empty_message():
    assert fallback_title("   ") == "New Conversation"


async def test_generate_title_uses_the_first_line_of_the_model_reply():
    llm = ScriptedLLM([], completion="Planning a Trip.\nsecond line")

    assert await generate_title(llm, MESSAGE, 1.0) == "Planning a Trip"


async def test_generate_title_falls_back_when_the_model_raises():
    llm = ScriptedLLM([], completion=RuntimeError("boom"))

    assert await generate_title(llm, MESSAGE, 1.0) == MESSAGE


async def test_generate_title_falls_back_on_timeout():
    assert await generate_title(SlowLLM([]), MESSAGE, 0.01) == MESSAGE


async def test_generate_title_rejects_a_link():
    llm = ScriptedLLM([], completion="Visit https://example.com now")

    assert await generate_title(llm, MESSAGE, 1.0) == MESSAGE
