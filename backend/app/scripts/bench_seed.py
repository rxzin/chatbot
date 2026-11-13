"""
Synthetic benchmark dataset: users bench0..benchN-1@example.com, each with conversations
of alternating user/model messages. Run from /app: python -m scripts.bench_seed
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select

from auth.security import get_hash
from core.database import SessionLocal
from schemas.models import Conversation, Message, Roles, User, user_roles_table

PASSWORD = "BenchPassw0rd!"
EMAIL = "bench{}@example.com"
BATCH = 5000


async def _counts(db) -> dict:
    pattern = "bench%@example.com"
    users = (
        await db.execute(
            select(func.count()).select_from(User).where(User.email.like(pattern))
        )
    ).scalar_one()
    conversations = (
        await db.execute(
            select(func.count())
            .select_from(Conversation)
            .join(User, User.id == Conversation.user_id)
            .where(User.email.like(pattern))
        )
    ).scalar_one()
    messages = (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .where(User.email.like(pattern))
        )
    ).scalar_one()
    return {"users": users, "conversations": conversations, "messages": messages}


async def _insert_batched(db, table, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH):
        await db.execute(insert(table), rows[i : i + BATCH])


async def seed_bench(
    users: int = 200, conversations: int = 5, messages: int = 20
) -> dict:
    """Insert the dataset and return its row counts. Returns existing counts if present."""
    async with SessionLocal() as db:
        exists = (
            await db.execute(select(User.id).where(User.email == EMAIL.format(0)))
        ).first()
        if exists:
            return await _counts(db)

        role_id = (
            await db.execute(select(Roles.id).where(Roles.name == "users"))
        ).scalar_one()
        password_hash = get_hash(PASSWORD)  # once, production Argon2 parameters
        base = datetime.now(timezone.utc) - timedelta(days=1)

        user_rows, link_rows, conv_rows, msg_rows = [], [], [], []
        for u in range(users):
            user_id = uuid.uuid4()
            user_rows.append(
                {
                    "id": user_id,
                    "email": EMAIL.format(u),
                    "password": password_hash,
                    "is_active": True,
                }
            )
            link_rows.append({"user_id": user_id, "role_id": role_id})
            for c in range(conversations):
                conv_id = uuid.uuid4()
                conv_start = base + timedelta(minutes=u * conversations + c)
                conv_rows.append(
                    {
                        "id": conv_id,
                        "user_id": user_id,
                        "title": f"Bench conversation {c}",
                        "created_at": conv_start,
                    }
                )
                # A turn is a user row and a model row one microsecond apart, as
                # save_turn writes them.
                for turn in range(messages // 2):
                    t = conv_start + timedelta(seconds=turn)
                    question = f"Benchmark question {turn} in conversation {c}"
                    answer = f"Benchmark answer {turn}. " + "lorem ipsum dolor sit amet " * 8
                    for role, text, ts in (
                        ("user", question, t),
                        ("model", answer, t + timedelta(microseconds=1)),
                    ):
                        msg_rows.append(
                            {
                                "id": uuid.uuid4(),
                                "conversation_id": conv_id,
                                "role": role,
                                "content": text,
                                "parts": [{"type": "text", "text": text}],
                                "created_at": ts,
                            }
                        )

        await _insert_batched(db, User, user_rows)
        await _insert_batched(db, user_roles_table, link_rows)
        await _insert_batched(db, Conversation, conv_rows)
        await _insert_batched(db, Message, msg_rows)
        await db.commit()
        return await _counts(db)


async def main() -> None:
    print(json.dumps(await seed_bench()))


if __name__ == "__main__":
    asyncio.run(main())
