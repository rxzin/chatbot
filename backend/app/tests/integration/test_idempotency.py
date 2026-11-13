"""Optional Idempotency-Key on POST /api/conversations and POST /api/chat (D4)."""

import asyncio
import subprocess
from pathlib import Path
import sys
from collections import Counter

from sqlalchemy import func, select

from schemas.models import Conversation, Message
from support.factories import (
    auth_headers,
    create_conversation,
    create_user,
    login,
)
from support.redis import unreachable_memory_service
from support.sse import parse_sse

APP_DIR = Path(__file__).resolve().parents[2]
KEY = {"Idempotency-Key": "key-1"}


def post_chat(client, headers, conversation_id, message="hello"):
    return client.post(
        "/api/chat",
        headers=headers,
        json={"message": message, "conversationId": str(conversation_id)},
    )


async def message_count(db, conversation_id) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation_id)
    )


def joined_text(response) -> str:
    return "".join(
        e["delta"] for e in parse_sse(response.text) if e["type"] == "text-delta"
    )


# --- POST /api/conversations -----------------------------------------------------------


async def test_conversation_same_key_twice_returns_the_same_conversation(
    client, user, db
):
    _, headers = user
    first = await client.post(
        "/api/conversations", headers={**headers, **KEY}, json={"title": "A"}
    )
    second = await client.post(
        "/api/conversations", headers={**headers, **KEY}, json={"title": "A"}
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert await db.scalar(select(func.count()).select_from(Conversation)) == 1


async def test_conversation_same_key_from_another_user_is_a_new_conversation(
    client, make_client, user, db
):
    _, headers = user
    other = await create_user(db)
    other_headers = auth_headers(await login(make_client(), other.email))

    first = await client.post(
        "/api/conversations", headers={**headers, **KEY}, json={"title": "A"}
    )
    second = await client.post(
        "/api/conversations", headers={**other_headers, **KEY}, json={"title": "A"}
    )

    assert first.json()["id"] != second.json()["id"]
    assert await db.scalar(select(func.count()).select_from(Conversation)) == 2


async def test_conversation_without_a_key_is_created_each_time(client, user, db):
    _, headers = user
    for _ in range(2):
        response = await client.post(
            "/api/conversations", headers=headers, json={"title": "A"}
        )
        assert response.status_code == 201

    assert await db.scalar(select(func.count()).select_from(Conversation)) == 2


# --- POST /api/chat --------------------------------------------------------------------


async def test_chat_repeat_is_replayed_without_a_second_model_call(
    client, user, db, redis, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted = scripted_llm([["Hi ", "there"]])

    first = await post_chat(client, {**headers, **KEY}, conversation.id)
    second = await post_chat(client, {**headers, **KEY}, conversation.id)

    assert first.status_code == second.status_code == 200
    assert await message_count(db, conversation.id) == 2
    assert len(scripted.calls) == 1
    assert joined_text(second) == joined_text(first) == "Hi there"
    assert parse_sse(second.text)[-1]["type"] == "done"
    (quota_key,) = await redis.keys(f"quota:chat:{account.id}:*")
    assert await redis.get(quota_key) == "1"


async def test_chat_in_flight_duplicate_gets_409(
    client, make_client, user, db, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted = scripted_llm([["Hi ", "there"]])
    scripted.gate = asyncio.Event()

    first = asyncio.create_task(
        post_chat(client, {**headers, **KEY}, conversation.id)
    )
    try:
        for _ in range(200):
            if len(scripted.calls) == 1:
                break
            await asyncio.sleep(0.05)
        assert len(scripted.calls) == 1

        second = await post_chat(make_client(), {**headers, **KEY}, conversation.id)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"
        assert (
            second.json()["error"]["message"]
            == "This message is already being processed."
        )
    finally:
        scripted.gate.set()

    done = await first
    assert done.status_code == 200
    assert parse_sse(done.text)[-1]["type"] == "done"
    assert await message_count(db, conversation.id) == 2


async def test_chat_replay_still_works_when_redis_is_down(
    client, user, db, app_state_override, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted = scripted_llm([["Hi ", "there"]])
    app_state_override(redis_service=unreachable_memory_service())

    first = await post_chat(client, {**headers, **KEY}, conversation.id)
    second = await post_chat(client, {**headers, **KEY}, conversation.id)

    assert first.status_code == second.status_code == 200
    assert await message_count(db, conversation.id) == 2
    assert len(scripted.calls) == 1


async def test_ten_concurrent_chats_with_one_key_store_one_turn(
    make_client, user, db, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted_llm([["ok"]] * 10)

    responses = await asyncio.gather(
        *[
            post_chat(make_client(), {**headers, **KEY}, conversation.id)
            for _ in range(10)
        ]
    )

    assert set(Counter(r.status_code for r in responses)) <= {200, 409}
    assert await message_count(db, conversation.id) == 2


# --- the header itself -----------------------------------------------------------------


async def test_a_key_longer_than_128_characters_is_rejected(client, user):
    _, headers = user
    response = await client.post(
        "/api/conversations",
        headers={**headers, "Idempotency-Key": "k" * 129},
        json={"title": "A"},
    )
    assert response.status_code == 422


async def test_an_empty_key_is_rejected(client, user):
    _, headers = user
    response = await client.post(
        "/api/conversations",
        headers={**headers, "Idempotency-Key": ""},
        json={"title": "A"},
    )
    assert response.status_code == 422


# --- migration -------------------------------------------------------------------------


async def test_migration_downgrades_and_upgrades_cleanly(app):
    from core.database import engine

    def alembic(*args):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=APP_DIR,
            check=True,
            capture_output=True,
        )

    try:
        alembic("downgrade", "-1")
    finally:
        alembic("upgrade", "head")
        await engine.dispose()
