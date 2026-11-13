"""Chat turns fired concurrently: quota, shared conversation, isolation, bug reports."""

import asyncio
from collections import Counter

import pytest
from sqlalchemy import func, select

from schemas.models import Message, PendingJiraTicket
from services.base import ToolCall
from support.factories import auth_headers, create_conversation, create_user, login
from support.fakes import ScriptedLLM
from support.sse import parse_sse


def post_chat(client, headers, conversation_id, message):
    return client.post(
        "/api/chat",
        headers=headers,
        json={"message": message, "conversationId": str(conversation_id)},
    )


class EchoLLM(ScriptedLLM):
    """Replies with the prompt it was given, so the order of calls does not matter."""

    async def stream_turn(self, *, prompt, **kwargs):
        self.calls.append({"prompt": prompt})
        yield f"reply to {prompt}"


async def message_count(db, conversation_id=None) -> int:
    query = select(func.count()).select_from(Message)
    if conversation_id is not None:
        query = query.where(Message.conversation_id == conversation_id)
    return await db.scalar(query)


async def test_daily_quota_admits_exactly_the_limit_under_concurrency(
    make_client, user, db, scripted_llm, settings_override
):
    settings_override(CHAT_DAILY_LIMIT_PER_USER=5)
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted_llm([["ok"]] * 20)

    responses = await asyncio.gather(
        *[post_chat(make_client(), headers, conversation.id, f"m{i}") for i in range(20)]
    )

    assert Counter(r.status_code for r in responses) == {200: 5, 429: 15}
    assert await message_count(db) == 10


async def concurrent_turns(make_client, user, db, scripted_llm):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    scripted_llm([["ok"]] * 10)
    responses = await asyncio.gather(
        *[post_chat(make_client(), headers, conversation.id, f"m{i}") for i in range(10)]
    )
    assert [r.status_code for r in responses] == [200] * 10
    return account, conversation


async def test_concurrent_turns_in_one_conversation_are_all_stored(
    make_client, user, db, scripted_llm
):
    _, conversation = await concurrent_turns(make_client, user, db, scripted_llm)

    assert await message_count(db, conversation.id) == 20


@pytest.mark.xfail(reason="F14", strict=False)
async def test_concurrent_turns_keep_every_message_in_redis(
    make_client, user, db, scripted_llm, app, redis
):
    account, conversation = await concurrent_turns(make_client, user, db, scripted_llm)

    key = app.state.redis_service._history_key(account.id, conversation.id)
    assert await redis.llen(key) == 20


async def test_concurrent_turns_leave_a_whole_number_of_turns_in_redis(
    make_client, user, db, scripted_llm, app, redis
):
    """Pins F14: Redis holds whatever the last writer left, an even count."""
    account, conversation = await concurrent_turns(make_client, user, db, scripted_llm)

    key = app.state.redis_service._history_key(account.id, conversation.id)
    length = await redis.llen(key)
    assert 2 <= length <= 20
    assert length % 2 == 0


async def chat_as_many_users(make_client, db, app_state_override, n):
    """n users chat once each at the same time. Returns (people, responses)."""
    app_state_override(llm_service=EchoLLM([]))
    people = []
    for i in range(n):
        account = await create_user(db)
        headers = auth_headers(await login(make_client(), account.email))
        conversation = await create_conversation(db, account.id, title="Existing chat")
        people.append((headers, conversation, f"secret-{i}"))

    responses = await asyncio.gather(
        *[
            post_chat(make_client(), headers, conversation.id, text)
            for headers, conversation, text in people
        ],
        return_exceptions=True,
    )
    return people, responses


async def assert_no_cross_talk(db, people, responses):
    for (_, conversation, text), response in zip(people, responses):
        assert not isinstance(response, Exception), repr(response)
        assert response.status_code == 200
        assert f"reply to {text}" in response.text
        rows = (
            await db.execute(
                select(Message.role, Message.content)
                .where(Message.conversation_id == conversation.id)
                .execution_options(populate_existing=True)
            )
        ).all()
        assert sorted(tuple(r) for r in rows) == sorted(
            [("user", text), ("model", f"reply to {text}")]
        )


async def test_twenty_users_chatting_concurrently_all_get_their_own_reply(
    make_client, db, app_state_override
):
    """
    More streams than the pool has connections (5 + 10). Each stream used to hold the
    request's connection while waiting for another, so 16+ streams deadlocked (F30).
    """
    people, responses = await chat_as_many_users(
        make_client, db, app_state_override, 20
    )

    await assert_no_cross_talk(db, people, responses)


class BugReportLLM(ScriptedLLM):
    """Files a bug report on every first call of a turn, then answers once it has the result."""

    async def stream_turn(self, *, prompt, exchanges, **kwargs):
        self.calls.append({"prompt": prompt})
        if exchanges:
            yield "done"
        else:
            args = {"title": "Bug", "description": "Broken."}
            yield [ToolCall(f"c-{prompt}", "report_bug", args)]


async def test_concurrent_bug_reports_by_one_user_save_one_ticket(
    make_client, user, db, app_state_override
):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    app_state_override(llm_service=BugReportLLM([]))

    responses = await asyncio.gather(
        *[post_chat(make_client(), headers, conversation.id, "report") for _ in range(5)]
    )

    assert [r.status_code for r in responses] == [200] * 5
    assert parse_sse(responses[0].text)
    tickets = await db.scalar(select(func.count()).select_from(PendingJiraTicket))
    assert tickets == 1
