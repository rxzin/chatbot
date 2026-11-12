"""The event stream of POST /api/chat, with the model scripted by each test."""

import asyncio

from sqlalchemy import select

from schemas.models import Conversation
from support.factories import chat, create_conversation
from support.sse import parse_sse


def types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def text_of(events: list[dict]) -> str:
    return "".join(e["delta"] for e in events if e["type"] == "text-delta")


async def post_chat(client, headers, conversation_id, message="hello"):
    return await client.post(
        "/api/chat",
        headers=headers,
        json={"message": message, "conversationId": str(conversation_id)},
    )


async def test_plain_reply_streams_text_then_done_and_is_saved(
    client, user, conversation, scripted_llm, stored_messages
):
    _, headers = user
    scripted_llm([["Hello", ", ", "world"]])

    events = await chat(client, headers, conversation.id, "hi")

    assert types(events) == ["text-delta", "text-delta", "text-delta", "done"]
    assert events[-1] == {"type": "done", "finishReason": "stop"}
    user_row, model_row = await stored_messages(conversation.id)
    assert (user_row.role, user_row.content) == ("user", "hi")
    assert (model_row.role, model_row.content) == ("model", text_of(events))
    assert model_row.parts == [{"type": "text", "text": "Hello, world"}]


async def test_response_headers_are_set_for_streaming(
    client, user, conversation, scripted_llm
):
    _, headers = user
    scripted_llm([["ok"]])

    response = await post_chat(client, headers, conversation.id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-cache"


async def test_first_turn_of_an_untitled_conversation_gets_a_title(
    client, user, db, scripted_llm
):
    account, headers = user
    untitled = await create_conversation(db, account.id)
    scripted_llm([["first reply"], ["second reply"]], completion="Trip Planning")

    first = await chat(client, headers, untitled.id, "help me plan a trip")
    second = await chat(client, headers, untitled.id, "and a hotel")

    assert types(first) == ["text-delta", "title", "done"]
    assert first[1] == {"type": "title", "title": "Trip Planning"}
    assert types(second) == ["text-delta", "done"]
    title = await db.scalar(
        select(Conversation.title).where(Conversation.id == untitled.id)
    )
    assert title == "Trip Planning"


async def test_suggestions_are_sent_before_done_and_saved(
    client, user, conversation, scripted_llm, settings_override, stored_messages
):
    settings_override(SUGGESTIONS_ENABLED=True)
    _, headers = user
    scripted_llm(
        [["An answer."]], completion="A question?\nB question?\nC question?"
    )

    events = await chat(client, headers, conversation.id, "hi")

    assert types(events) == ["text-delta", "suggestions", "done"]
    suggestions = ["A question?", "B question?", "C question?"]
    assert events[1]["suggestions"] == suggestions
    _, model_row = await stored_messages(conversation.id)
    assert model_row.parts[-1] == {"type": "suggestions", "suggestions": suggestions}


async def test_failed_suggestions_do_not_fail_the_reply(
    client, user, conversation, scripted_llm, settings_override
):
    settings_override(SUGGESTIONS_ENABLED=True)
    _, headers = user
    scripted_llm([["An answer."]], completion=RuntimeError("model down"))

    events = await chat(client, headers, conversation.id, "hi")

    assert types(events) == ["text-delta", "done"]


async def test_model_error_ends_the_stream_with_one_error_event(
    client, user, conversation, scripted_llm, stored_messages
):
    _, headers = user
    scripted_llm([RuntimeError("boom")])

    events = await chat(client, headers, conversation.id, "hi")

    assert types(events) == ["error"]
    assert events[0]["error"]["code"] == "STREAM_GENERATION_FAILED"
    assert "boom" not in events[0]["error"]["message"]
    assert await stored_messages(conversation.id) == []


async def test_turn_that_runs_too_long_is_stopped(
    client, user, conversation, scripted_llm, settings_override, stored_messages
):
    settings_override(AGENT_TURN_TIMEOUT_SECONDS=0.1)
    _, headers = user
    model = scripted_llm([["partial ", "never sent"]])
    model.gate = asyncio.Event()  # never set: the model hangs after its first chunk

    events = await chat(client, headers, conversation.id, "hi")

    assert types(events)[-1] == "error"
    assert "done" not in types(events)
    assert events[-1]["error"]["code"] == "TURN_TIMEOUT"
    assert await stored_messages(conversation.id) == []


async def test_invalid_message_is_rejected_before_streaming(
    client, user, conversation, scripted_llm
):
    _, headers = user
    model = scripted_llm([])

    empty = await post_chat(client, headers, conversation.id, "")
    too_long = await post_chat(client, headers, conversation.id, "x" * 8001)
    at_limit_would_stream = await post_chat(client, headers, conversation.id, "x" * 8000)

    for response in (empty, too_long):
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
    assert model.calls[0]["prompt"] == "x" * 8000
    # The script is empty, so the accepted message reaches the model and fails there.
    assert types(parse_sse(at_limit_would_stream.text)) == ["error"]
