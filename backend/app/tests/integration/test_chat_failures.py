"""What a chat turn leaves behind when something goes wrong."""

import asyncio
import json
import time

import httpx
import pytest
from sqlalchemy import func, select

from schemas.models import Message
from support.factories import (
    auth_headers,
    chat,
    create_conversation,
    create_user,
    login,
)
from support.redis import unreachable_memory_service


async def _row_count(db, conversation_id) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation_id)
    )


async def _eventually(check, timeout=2.0):
    """Poll an async predicate until it is true or the timeout passes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result = await check()
        if result or loop.time() > deadline:
            return result
        await asyncio.sleep(0.05)


def _post_body(conversation_id, message="hello"):
    return {"message": message, "conversationId": str(conversation_id)}


# --- the model fails -----------------------------------------------------------------


async def test_agent_failure_streams_an_error_and_saves_nothing(
    client, user, db, redis, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    scripted_llm([RuntimeError("boom")])

    events = await chat(client, headers, conversation.id, "hello")

    assert [e["type"] for e in events] == ["error"]
    assert events[0]["error"]["code"] == "STREAM_GENERATION_FAILED"
    assert await _row_count(db, conversation.id) == 0
    assert await redis.keys("chat:user:*") == []
    # A failed turn still uses up one message of the day's quota. Pinned as is.
    (key,) = await redis.keys(f"quota:chat:{account.id}:*")
    assert await redis.get(key) == "1"


# --- Redis is down -------------------------------------------------------------------


async def test_chat_works_when_redis_is_down(
    client, user, db, app_state_override, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    scripted_llm([["Hi ", "there"]])
    app_state_override(redis_service=unreachable_memory_service())

    started = time.monotonic()
    events = await chat(client, headers, conversation.id, "hello")
    elapsed = time.monotonic() - started

    # D2: the daily quota is skipped during the outage (fail open), chat carries on.
    assert [e["type"] for e in events][-1] == "done"
    assert await _row_count(db, conversation.id) == 2
    assert elapsed < 10


async def test_second_turn_during_outage_reads_history_from_postgres(
    client, user, db, app_state_override, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    model = scripted_llm([["one"], ["two"]])
    app_state_override(redis_service=unreachable_memory_service())

    await chat(client, headers, conversation.id, "first")
    await chat(client, headers, conversation.id, "second")

    assert len(model.calls[1]["history"]) == 2
    assert await _row_count(db, conversation.id) == 4


async def test_health_reports_redis_down(client, app_state_override):
    app_state_override(redis_service=unreachable_memory_service())

    health = await client.get("/health/")

    assert health.status_code == 503
    assert health.json()["redis"] is False


@pytest.mark.xfail(reason="F28", strict=False)
async def test_history_not_stale_after_outage(
    client, user, db, app, app_state_override, scripted_llm
):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    model = scripted_llm([["one"], ["two"], ["three"]])
    await chat(client, headers, conversation.id, "first")  # Redis now holds 2 messages
    working = app.state.redis_service

    app_state_override(redis_service=unreachable_memory_service())
    await chat(client, headers, conversation.id, "second")  # saved to Postgres only
    app_state_override(redis_service=working)
    await chat(client, headers, conversation.id, "third")

    # Desired: all 4 earlier messages. Actual: Redis still holds the pre-outage 2.
    assert len(model.calls[2]["history"]) == 4


async def test_chat_works_without_redis_when_the_quota_is_off(
    client, user, db, app_state_override, scripted_llm, settings_override
):
    settings_override(CHAT_DAILY_LIMIT_PER_USER=0)
    account, headers = user
    conversation = await create_conversation(db, account.id)
    scripted_llm([["Hi ", "there"]])
    app_state_override(redis_service=unreachable_memory_service())

    events = await chat(client, headers, conversation.id, "hello")

    assert [e["type"] for e in events][-1] == "done"
    assert await _row_count(db, conversation.id) == 2


# --- saving the turn fails -----------------------------------------------------------


async def test_postgres_failure_after_done_is_silent_to_the_client(
    client, user, db, redis, scripted_llm, monkeypatch
):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    scripted_llm([["Hi ", "there"]])

    async def refuse(*args, **kwargs):
        return False

    monkeypatch.setattr("services.streaming.save_postgres_turn", refuse)

    events = await chat(client, headers, conversation.id, "hello")

    # F11: the client saw done, Redis kept the turn, but Postgres has nothing.
    assert [e["type"] for e in events][-1] == "done"
    history_key = f"chat:user:{account.id}:conversation:{conversation.id}"
    assert await redis.llen(history_key) == 2
    assert await _row_count(db, conversation.id) == 0


async def test_postgres_exception_after_done_adds_an_error_event(
    client, user, db, scripted_llm, monkeypatch
):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    scripted_llm([["Hi ", "there"]])

    async def explode(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("services.streaming.save_postgres_turn", explode)

    events = await chat(client, headers, conversation.id, "hello")

    # F10: the error arrives after done, so a client that stops at done never sees it.
    types = [e["type"] for e in events]
    assert types[-2:] == ["done", "error"]
    assert await _row_count(db, conversation.id) == 0


# --- invalid access ------------------------------------------------------------------


async def test_refused_requests_do_not_use_quota(client, user, db, redis, scripted_llm):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    model = scripted_llm([["never sent"]])
    body = _post_body(conversation.id)

    unknown = await client.post(
        "/api/chat",
        headers=headers,
        json=_post_body("00000000-0000-4000-8000-000000000000"),
    )
    anonymous = await client.post("/api/chat", json=body)
    plain = await create_user(db, role=None)
    plain_headers = auth_headers(await login(client, plain.email))
    forbidden = await client.post("/api/chat", headers=plain_headers, json=body)

    assert unknown.status_code == 404
    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert model.calls == []
    assert await redis.keys("quota:chat:*") == []


# --- the client disconnects ----------------------------------------------------------


async def test_interrupted_stream(live_server, user, db, redis, scripted_llm):
    account, headers = user
    conversation = await create_conversation(db, account.id)
    model = scripted_llm([["Hi ", "there"]])
    model.gate = asyncio.Event()
    history_key = f"chat:user:{account.id}:conversation:{conversation.id}"

    async with httpx.AsyncClient(base_url=live_server, timeout=10) as http:
        async with http.stream(
            "POST", "/api/chat", headers=headers, json=_post_body(conversation.id)
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    assert json.loads(line[5:])["type"] == "text-delta"
                    break
        # The response is closed here: the client is gone mid-stream.
        model.gate.set()

        async def nothing_saved():
            return await _row_count(db, conversation.id) == 0 and not await redis.exists(
                history_key
            )

        # Wait out the server noticing the disconnect, then check nothing was saved
        # (a save, if it were going to happen, lands within this time).
        await asyncio.sleep(0.5)
        assert await _eventually(nothing_saved, timeout=1.5)
        assert (await http.get("/health/")).status_code == 200


async def _chat_and_hang_up_at_done(base_url, headers, conversation_id, extra=None):
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as http:
        async with http.stream(
            "POST",
            "/api/chat",
            headers={**headers, **(extra or {})},
            json=_post_body(conversation_id),
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data:") and json.loads(line[5:])["type"] == "done":
                    break


async def test_disconnect_after_done_keeps_turn(
    live_server, user, db, redis, scripted_llm
):
    """
    A client that closes the stream as soon as it sees `done` (Review Focus 3).
    The save used to run after `done` and was skipped once the client had gone, so the
    turn was lost in 16 of 16 runs. It now starts before `done` and outlives the client.
    """
    account, headers = user
    conversation = await create_conversation(db, account.id)
    scripted_llm([["Hi ", "there"]])
    history_key = f"chat:user:{account.id}:conversation:{conversation.id}"

    await _chat_and_hang_up_at_done(live_server, headers, conversation.id)

    async def saved():
        return await _row_count(db, conversation.id) == 2

    assert await _eventually(saved)
    assert await redis.llen(history_key) == 2


async def test_retry_after_hanging_up_at_done_never_runs_the_model_twice(
    live_server, user, db, scripted_llm
):
    """The Idempotency-Key lock is held until the save ends, not until the client goes."""
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted = scripted_llm([["Hi ", "there"]])
    key = {"Idempotency-Key": "retry-1"}

    await _chat_and_hang_up_at_done(live_server, headers, conversation.id, key)
    async with httpx.AsyncClient(base_url=live_server, timeout=10) as http:
        retry = await http.post(
            "/api/chat",
            headers={**headers, **key},
            json=_post_body(conversation.id),
        )

    assert retry.status_code in (200, 409)
    assert len(scripted.calls) == 1

    async def saved():
        return await _row_count(db, conversation.id) == 2

    assert await _eventually(saved)
