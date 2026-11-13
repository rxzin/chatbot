"""One conversation followed through two chat turns, across the API, Postgres and Redis."""

import json

from sqlalchemy import func, select

from schemas.models import Conversation, LlmUsage, Message
from support.factories import (
    auth_headers,
    chat,
    create_conversation,
    create_user,
    login,
)


async def _stored_messages(db, conversation_id) -> list[Message]:
    rows = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .execution_options(populate_existing=True)
    )
    # User and model rows of one turn share a timestamp, so order by role within it.
    return sorted(rows.scalars().all(), key=lambda m: (m.created_at, m.role != "user"))


async def test_chat_lifecycle_end_to_end(
    client, make_client, user, db, redis, scripted_llm
):
    account, headers = user
    scripted = scripted_llm([["Hi ", "there"], ["Again"]])
    conversation = await create_conversation(db, account.id)
    history_key = f"chat:user:{account.id}:conversation:{conversation.id}"
    body = {"message": "hello", "conversationId": str(conversation.id)}

    # Another user cannot use this conversation, and is refused before any quota is spent.
    other = await create_user(db)
    other_headers = auth_headers(await login(make_client(), other.email))
    refused = await client.post("/api/chat", headers=other_headers, json=body)
    assert refused.status_code == 404
    assert await redis.keys(f"quota:chat:{other.id}:*") == []

    # Turn 1 starts with a cold cache, so the model sees no history.
    events = await chat(client, headers, conversation.id, "hello")

    assert scripted.calls[0]["history"] == []
    deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
    assert "".join(deltas) == "Hi there"
    assert [e["type"] for e in events] == [
        "text-delta",
        "text-delta",
        "title",
        "done",
    ]

    rows = await _stored_messages(db, conversation.id)
    assert [(m.role, m.content) for m in rows] == [
        ("user", "hello"),
        ("model", "Hi there"),
    ]
    usage_rows = await db.scalar(
        select(func.count())
        .select_from(LlmUsage)
        .where(LlmUsage.conversation_id == conversation.id)
    )
    assert usage_rows == 0
    titled = await db.scalar(
        select(Conversation.title)
        .where(Conversation.id == conversation.id)
        .execution_options(populate_existing=True)
    )
    assert titled == "Test Title"
    assert await redis.llen(history_key) == 2

    # Turn 2 after the cache is lost: history is rebuilt from Postgres.
    await redis.delete(history_key)
    events = await chat(client, headers, conversation.id, "again")

    assert events[-1]["type"] == "done"
    assert len(scripted.calls[1]["history"]) == 2
    assert await redis.llen(history_key) == 4
    assert len(await _stored_messages(db, conversation.id)) == 4


async def test_turn_that_needs_compaction_replaces_the_cached_history(
    client, user, db, redis, scripted_llm, settings_override
):
    """Appending is for turns that fit; a turn past the budget rewrites the list."""
    settings_override(MAX_REDIS_MESSAGES=4, MIN_RECENT_TURNS=1)
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted_llm([["a1"], ["a2"], ["a3"]], completion="the summary")
    history_key = f"chat:user:{account.id}:conversation:{conversation.id}"

    for message in ("q1", "q2"):
        await chat(client, headers, conversation.id, message)
    assert await redis.llen(history_key) == 4  # appended, within budget

    await chat(client, headers, conversation.id, "q3")

    cached = [json.loads(m)["content"] for m in await redis.lrange(history_key, 0, -1)]
    assert len(cached) <= 4
    assert cached[-2:] == ["q3", "a3"]
    assert await redis.get(f"{history_key}:summary") == "the summary"
    assert len(await _stored_messages(db, conversation.id)) == 6
