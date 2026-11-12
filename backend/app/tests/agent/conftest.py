"""Shared setup for the stream and agent tests."""

import pytest_asyncio
from sqlalchemy import select

from schemas.models import Message
from support.factories import create_conversation


@pytest_asyncio.fixture
async def conversation(user, db):
    """A conversation that already has a title, so no title event joins the stream."""
    account, _ = user
    return await create_conversation(db, account.id, title="Existing chat")


@pytest_asyncio.fixture
async def stored_messages(db):
    """Read what a turn saved: await stored_messages(conversation.id) -> [Message]."""

    async def read(conversation_id) -> list[Message]:
        rows = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .execution_options(populate_existing=True)
        )
        # User and model rows of one turn share a timestamp, so order by role within it.
        return sorted(
            rows.scalars().all(), key=lambda m: (m.created_at, m.role != "user")
        )

    return read
