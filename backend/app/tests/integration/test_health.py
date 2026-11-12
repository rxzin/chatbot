"""Smoke test: the app starts on the fakes and reaches the test Postgres and Redis."""


async def test_health_ok(client):
    response = await client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"health": True, "redis": True, "database": True}


async def test_health_redirect(client):
    response = await client.get("/health")

    assert response.status_code == 307


async def test_fixtures_log_a_user_in(client, user, admin, db):
    """The user and admin fixtures go through the real login and get real permissions."""
    account, headers = user
    admin_account, admin_headers = admin

    me = await client.get("/api/auth/me", headers=headers)
    admin_me = await client.get("/api/auth/me", headers=admin_headers)

    assert me.status_code == 200
    assert me.json()["email"] == account.email
    assert "ai:chat" in me.json()["permissions"]
    assert admin_me.json()["email"] == admin_account.email
    assert "audit:read" in admin_me.json()["permissions"]


async def test_chat_round_trip_with_scripted_model(client, user, db, scripted_llm):
    """The chat helper, the SSE parser and ScriptedLLM work together end to end."""
    from support.factories import chat, create_conversation

    account, headers = user
    conversation = await create_conversation(db, account.id)
    model = scripted_llm([["Hi ", "there"]])

    events = await chat(client, headers, conversation.id, "hello")

    text = "".join(e["delta"] for e in events if e["type"] == "text-delta")
    assert text == "Hi there"
    assert events[-1]["type"] == "done"
    assert len(model.calls) == 1
    assert model.calls[0]["prompt"] == "hello"


async def test_database_is_empty_at_the_start_of_each_test(db):
    """Rows from the tests above are gone; roles and permissions are kept."""
    from sqlalchemy import func, select

    from schemas.models import Roles, User

    assert await db.scalar(select(func.count()).select_from(User)) == 0
    assert await db.scalar(select(func.count()).select_from(Roles)) == 2
