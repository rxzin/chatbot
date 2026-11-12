"""Creating, listing and reading conversations, and keeping users apart."""

from support.factories import auth_headers, create_conversation, create_user, login


async def test_create_uses_the_default_title(client, user):
    _, headers = user

    response = await client.post("/api/conversations", headers=headers, json={})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "title", "created_at"}
    assert body["title"] == "New Conversation"


async def test_create_with_a_title(client, user):
    _, headers = user

    response = await client.post(
        "/api/conversations", headers=headers, json={"title": "Trip plans"}
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Trip plans"


async def test_create_rejects_a_title_over_100_characters(client, user):
    _, headers = user

    at_limit = await client.post(
        "/api/conversations", headers=headers, json={"title": "x" * 100}
    )
    over_limit = await client.post(
        "/api/conversations", headers=headers, json={"title": "x" * 101}
    )

    assert at_limit.status_code == 201
    assert over_limit.status_code == 422


async def test_list_returns_only_the_callers_conversations_newest_first(
    client, make_client, user, db
):
    _, headers = user
    stranger = await create_user(db)
    await create_conversation(db, stranger.id, title="not yours")
    for title in ["first", "second", "third"]:
        await client.post("/api/conversations", headers=headers, json={"title": title})

    response = await client.get("/api/conversations", headers=headers)

    assert response.status_code == 200
    assert [c["title"] for c in response.json()] == ["third", "second", "first"]


async def test_get_one_conversation(client, user, db):
    account, headers = user
    conversation = await create_conversation(db, account.id, title="mine")

    response = await client.get(f"/api/conversations/{conversation.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(conversation.id)
    assert response.json()["title"] == "mine"


async def test_another_users_conversation_looks_like_it_does_not_exist(
    client, make_client, user, db
):
    """404, not 403: the response must not confirm that the id belongs to someone."""
    account, _ = user
    conversation = await create_conversation(db, account.id)
    stranger = await create_user(db)
    stranger_headers = auth_headers(await login(make_client(), stranger.email))

    one = await client.get(
        f"/api/conversations/{conversation.id}", headers=stranger_headers
    )
    messages = await client.get(
        f"/api/conversations/{conversation.id}/messages", headers=stranger_headers
    )

    assert one.status_code == messages.status_code == 404
    assert one.json()["error"]["code"] == "NOT_FOUND"
    assert messages.json()["error"]["code"] == "NOT_FOUND"


async def test_messages_of_a_new_conversation_are_empty(client, user, db):
    account, headers = user
    conversation = await create_conversation(db, account.id)

    response = await client.get(
        f"/api/conversations/{conversation.id}/messages", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_malformed_id_is_a_validation_error(client, user):
    _, headers = user

    one = await client.get("/api/conversations/not-a-uuid", headers=headers)
    messages = await client.get(
        "/api/conversations/not-a-uuid/messages", headers=headers
    )

    assert one.status_code == messages.status_code == 422
