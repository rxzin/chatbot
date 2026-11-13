"""Rules the database itself enforces: foreign keys, uniqueness, atomic writes, ids."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from core.config import getSettings
from schemas.models import (
    AuditLog,
    Conversation,
    Document,
    LlmUsage,
    Message,
    Session,
    User,
)
from services.message import save_turn
from support.factories import create_conversation, create_user, login


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_deleting_a_user_removes_everything_they_own(client, db):
    """Plain SQL DELETE, so this tests the foreign keys rather than the ORM."""
    account = await create_user(db)
    keeper = await create_user(db)
    await login(client, account.email)
    conversation = await create_conversation(db, account.id)
    kept_conversation = await create_conversation(db, keeper.id)
    await save_turn(db, conversation.id, account.id, "hello", "hi")
    db.add(
        Document(
            user_id=account.id,
            conversation_id=conversation.id,
            filename="notes.txt",
            content_type="text/plain",
            size_bytes=5,
        )
    )
    await db.commit()

    await db.execute(delete(User).where(User.id == account.id))
    await db.commit()

    assert await count(db, Message) == 0
    assert await count(db, Session) == 0
    assert await count(db, Document) == 0
    remaining = (await db.execute(select(Conversation.id))).scalars().all()
    assert remaining == [kept_conversation.id]


async def test_deleting_a_conversation_keeps_its_usage_rows(db):
    account = await create_user(db)
    conversation = await create_conversation(db, account.id)
    db.add(
        LlmUsage(
            user_id=account.id,
            conversation_id=conversation.id,
            purpose="agent",
            model="test-model",
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    await db.commit()

    await db.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db.commit()

    (usage,) = (await db.execute(select(LlmUsage))).scalars().all()
    assert usage.conversation_id is None
    assert usage.user_id == account.id
    assert usage.prompt_tokens == 10


async def test_deleting_a_user_keeps_their_audit_rows(db):
    account = await create_user(db)
    db.add(
        AuditLog(
            user_id=account.id,
            method="GET",
            path="/api/conversations",
            status_code=200,
            duration_ms=3,
        )
    )
    await db.commit()

    await db.execute(delete(User).where(User.id == account.id))
    await db.commit()

    (entry,) = (await db.execute(select(AuditLog))).scalars().all()
    assert entry.user_id is None
    assert entry.path == "/api/conversations"


async def test_email_must_be_unique(db):
    await create_user(db, email="taken@example.com")

    with pytest.raises(IntegrityError):
        await create_user(db, email="taken@example.com")
    await db.rollback()

    assert await count(db, User) == 1


async def test_save_turn_writes_both_messages_or_neither(db):
    saved = await save_turn(db, uuid4(), uuid4(), "hello", "hi")

    assert saved is False
    assert await count(db, Message) == 0


async def test_save_turn_stores_the_user_and_model_messages(db):
    account = await create_user(db)
    conversation = await create_conversation(db, account.id)

    saved = await save_turn(db, conversation.id, account.id, "hello", "hi there")

    assert saved is True
    rows = (await db.execute(select(Message.role, Message.content))).all()
    assert sorted(rows) == [("model", "hi there"), ("user", "hello")]


async def test_ids_follow_the_configured_strategy(db):
    account = await create_user(db)

    first = await create_conversation(db, account.id)
    second = await create_conversation(db, account.id)

    if getSettings().ID_STRATEGY == "uuidv7":
        assert first.id.version == 7
        assert second.id > first.id
    else:
        assert first.id.version == 4


async def test_message_parts_round_trip_unchanged(db):
    account = await create_user(db)
    conversation = await create_conversation(db, account.id)
    parts = [
        {"type": "text", "text": "See the notes."},
        {
            "type": "sources",
            "sources": [
                {"number": 1, "filename": "notes.txt", "page": None, "tags": ["a", "b"]}
            ],
        },
    ]

    await save_turn(db, conversation.id, account.id, "q", "See the notes.", parts)
    db.expire_all()

    stored = await db.scalar(select(Message.parts).where(Message.role == "model"))
    assert stored == parts
