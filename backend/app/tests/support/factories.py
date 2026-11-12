"""Builders for the rows and requests most tests start from."""

from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import get_hash
from schemas.models import Conversation, Roles, User
from support.sse import parse_sse

DEFAULT_PASSWORD = "Passw0rd!x"


async def create_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    role: str | None = "users",
    is_active: bool = True,
) -> User:
    """Insert a user directly. role=None gives a user with no role, so no permissions."""
    user = User(
        email=email or f"user-{uuid4().hex[:12]}@example.com",
        password=get_hash(password),
        is_active=is_active,
    )
    if role is not None:
        user.roles.append(
            (await db.execute(select(Roles).where(Roles.name == role))).scalar_one()
        )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login(
    client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD
) -> str:
    """Log in through the real endpoint. The refresh cookie lands in the client's jar."""
    response = await client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_conversation(
    db: AsyncSession, user_id: UUID, title: str = "New Conversation"
) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def chat(
    client: AsyncClient, headers: dict[str, str], conversation_id: UUID, message: str
) -> list[dict]:
    """Send one chat message, read the stream to its end, and return the parsed events."""
    response = await client.post(
        "/api/chat",
        headers=headers,
        json={"message": message, "conversationId": str(conversation_id)},
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)
