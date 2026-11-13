"""Trimming conversation history to the message and token limits."""

from schemas.chat import MessageParam
from services.context_budget import compact_history
from support.fakes import ScriptedLLM


def history(count: int) -> list[MessageParam]:
    return [
        MessageParam(role="user" if i % 2 == 0 else "model", content=f"message {i}")
        for i in range(count)
    ]


async def test_history_within_limits_is_returned_unchanged(settings_override):
    settings_override(MAX_REDIS_MESSAGES=4, MIN_RECENT_TURNS=1)
    llm = ScriptedLLM([], completion="SUMMARY")

    result = await compact_history(llm=llm, history=history(4), summary="earlier")

    assert [m.content for m in result.messages] == [f"message {i}" for i in range(4)]
    assert result.summary == "earlier"
    assert llm.completions == []


async def test_oldest_turns_are_evicted_and_summarized_once(settings_override):
    settings_override(MAX_REDIS_MESSAGES=4, MIN_RECENT_TURNS=1)
    llm = ScriptedLLM([], completion="SUMMARY")

    result = await compact_history(llm=llm, history=history(8), summary=None)

    assert [m.content for m in result.messages] == [f"message {i}" for i in range(4, 8)]
    assert result.summary == "SUMMARY"
    assert len(llm.completions) == 1
    prompt = llm.completions[0]["prompt"]
    assert all(f"message {i}\n" in prompt for i in range(4))
    assert "message 4" not in prompt


async def test_existing_summary_is_passed_to_the_summarizer(settings_override):
    settings_override(MAX_REDIS_MESSAGES=2, MIN_RECENT_TURNS=1)
    llm = ScriptedLLM([], completion="SUMMARY")

    await compact_history(llm=llm, history=history(4), summary="what came before")

    assert "what came before" in llm.completions[0]["prompt"]


async def test_never_keeps_fewer_than_the_minimum_recent_turns(settings_override):
    settings_override(MAX_REDIS_MESSAGES=1, MIN_RECENT_TURNS=2)
    llm = ScriptedLLM([], completion="SUMMARY")

    result = await compact_history(llm=llm, history=history(8), summary=None)

    assert len(result.messages) == 4


async def test_token_limit_also_evicts(settings_override):
    settings_override(
        MAX_REDIS_MESSAGES=100,
        MIN_RECENT_TURNS=1,
        MODEL_INPUT_TOKEN_LIMIT=100,
        INPUT_TOKEN_BUFFER=0,
        SUMMARIZE_THRESHOLD=1.0,
    )
    llm = ScriptedLLM([], completion="SUMMARY")
    long_history = [
        MessageParam(role="user" if i % 2 == 0 else "model", content="word " * 40)
        for i in range(6)
    ]

    result = await compact_history(llm=llm, history=long_history, summary=None)

    assert len(result.messages) == 2
    assert len(llm.completions) == 1
