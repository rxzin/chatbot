"""Conversation memory in Redis: cache hits, rebuilding from Postgres, expiry, outages."""

from uuid import uuid4

import pytest

from schemas.chat import MessageParam
from services.message import save_turn
from support.factories import create_conversation, create_user
from support.fakes import ScriptedLLM
from support.redis import unreachable_memory_service

DAY = 86400


def turn(index: int) -> list[MessageParam]:
    return [
        MessageParam(role="user", content=f"question {index}"),
        MessageParam(role="model", content=f"answer {index}"),
    ]


@pytest.fixture
def memory(app):
    return app.state.redis_service


@pytest.fixture
def ids():
    """A user id and a conversation id. Redis needs no matching rows in Postgres."""
    return uuid4(), uuid4()


async def test_state_written_to_redis_is_read_back(memory, ids):
    user_id, conversation_id = ids
    await memory.set_conversation_state(user_id, conversation_id, turn(1), "a summary")

    history, summary = await memory.get_conversation_state(user_id, conversation_id)

    assert [(m.role, m.content) for m in history] == [
        ("user", "question 1"),
        ("model", "answer 1"),
    ]
    assert summary == "a summary"


async def test_cold_cache_is_rebuilt_from_postgres(memory, db, redis):
    account = await create_user(db)
    conversation = await create_conversation(db, account.id)
    await save_turn(db, conversation.id, account.id, "question 1", "answer 1")
    await save_turn(db, conversation.id, account.id, "question 2", "answer 2")
    key = memory._history_key(account.id, conversation.id)
    assert await redis.exists(key) == 0

    history, summary = await memory.get_conversation_state(
        account.id, conversation.id, db=db, llm=ScriptedLLM([])
    )

    assert sorted(m.content for m in history) == [
        "answer 1",
        "answer 2",
        "question 1",
        "question 2",
    ]
    assert summary is None
    assert await redis.llen(key) == 4


async def test_cold_cache_for_someone_elses_conversation_is_refused(memory, db):
    """The Postgres fallback checks ownership, so a guessed id leaks nothing."""
    from core.errors import NotFoundError

    owner = await create_user(db)
    stranger = await create_user(db)
    conversation = await create_conversation(db, owner.id)
    await save_turn(db, conversation.id, owner.id, "private", "reply")

    with pytest.raises(NotFoundError):
        await memory.get_conversation_state(stranger.id, conversation.id, db=db)


async def test_history_and_summary_expire_after_a_day(memory, ids, redis):
    user_id, conversation_id = ids
    await memory.set_conversation_state(user_id, conversation_id, turn(1), "a summary")

    history_ttl = await redis.ttl(memory._history_key(user_id, conversation_id))
    summary_ttl = await redis.ttl(memory._summary_key(user_id, conversation_id))

    assert 0 < history_ttl <= DAY
    assert 0 < summary_ttl <= DAY


async def test_a_later_write_refreshes_the_summary_expiry(memory, ids, redis):
    user_id, conversation_id = ids
    summary_key = memory._summary_key(user_id, conversation_id)
    await memory.set_conversation_state(user_id, conversation_id, turn(1), "a summary")
    await redis.expire(summary_key, 10)

    await memory.set_conversation_state(user_id, conversation_id, turn(2), None)

    assert await redis.ttl(summary_key) > 10
    assert await redis.get(summary_key) == "a summary"


async def test_replacing_history_with_nothing_deletes_the_key(memory, ids, redis):
    user_id, conversation_id = ids
    key = memory._history_key(user_id, conversation_id)
    await memory.replace_history(user_id, conversation_id, turn(1))
    assert await redis.exists(key) == 1

    await memory.replace_history(user_id, conversation_id, [])

    assert await redis.exists(key) == 0


async def test_replacing_history_does_not_append(memory, ids, redis):
    user_id, conversation_id = ids
    await memory.replace_history(user_id, conversation_id, turn(1) + turn(2))

    await memory.replace_history(user_id, conversation_id, turn(3))

    history = await memory.get_history(user_id, conversation_id)
    assert [m.content for m in history] == ["question 3", "answer 3"]


# --- Redis unreachable -------------------------------------------------------------


async def test_reads_return_empty_when_redis_is_down(ids):
    memory = unreachable_memory_service()
    user_id, conversation_id = ids

    assert await memory.get_history(user_id, conversation_id) == []
    assert await memory.get_summary(user_id, conversation_id) is None
    assert await memory.get_rate_limit_ttl(user_id, "bug_report") is None


async def test_limits_refuse_when_redis_is_down(ids):
    """Fails closed: these guard paid calls. Finding F12; the chat route opts in to fail_open (Task X2)."""
    memory = unreachable_memory_service()
    user_id, _ = ids

    assert await memory.consume_daily_quota(user_id, "chat", limit=100) is False
    assert (
        await memory.consume_daily_quota(user_id, "chat", limit=100, fail_open=True)
        is True
    )
    assert await memory.try_acquire_rate_limit(user_id, "bug_report") is False


async def test_failed_write_is_reported_as_saved_when_a_summary_is_given(ids):
    """
    Pins finding F12: replace_history and save_summary swallow their errors, so the
    caller is told the state was saved when nothing was written.
    """
    memory = unreachable_memory_service()
    user_id, conversation_id = ids

    saved = await memory.set_conversation_state(
        user_id, conversation_id, turn(1), "a summary"
    )

    assert saved is True


async def test_failed_write_without_a_summary_is_reported_as_failed(ids):
    """Without a summary the method touches Redis directly, so the error is seen."""
    memory = unreachable_memory_service()
    user_id, conversation_id = ids

    saved = await memory.set_conversation_state(user_id, conversation_id, turn(1), None)

    assert saved is False
