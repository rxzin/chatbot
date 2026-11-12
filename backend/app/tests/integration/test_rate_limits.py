"""The daily chat quota, login failure limits and sign-up limits."""

from uuid import uuid4

from support.factories import DEFAULT_PASSWORD, chat, create_conversation, create_user

LOGIN = "/api/auth/login"
REGISTER = "/api/auth/register"
TWO_DAYS = 2 * 86400


async def post_chat(client, headers, conversation_id, message="hello"):
    return await client.post(
        "/api/chat",
        headers=headers,
        json={"message": message, "conversationId": str(conversation_id)},
    )


def signup(index: int) -> dict:
    return {"email": f"new{index}@example.com", "password": DEFAULT_PASSWORD}


# --- chat quota --------------------------------------------------------------------


async def test_chat_is_refused_once_the_daily_quota_is_used(
    client, user, db, redis, scripted_llm, settings_override
):
    settings_override(CHAT_DAILY_LIMIT_PER_USER=2)
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    model = scripted_llm([["one"], ["two"], ["never sent"]])

    await chat(client, headers, conversation.id, "first")
    await chat(client, headers, conversation.id, "second")
    refused = await post_chat(client, headers, conversation.id, "third")

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    assert "limit of 2 messages" in refused.json()["error"]["message"]
    assert len(model.calls) == 2
    (key,) = await redis.keys(f"quota:chat:{account.id}:*")
    assert 0 < await redis.ttl(key) <= TWO_DAYS


async def test_quota_is_counted_per_user(
    client, make_client, user, db, scripted_llm, settings_override
):
    from support.factories import auth_headers, login

    settings_override(CHAT_DAILY_LIMIT_PER_USER=1)
    account, headers = user
    other = await create_user(db)
    other_headers = auth_headers(await login(make_client(), other.email))
    mine = await create_conversation(db, account.id, title="Existing chat")
    theirs = await create_conversation(db, other.id, title="Existing chat")
    scripted_llm([["one"], ["two"]])

    await chat(client, headers, mine.id, "first")
    await chat(client, other_headers, theirs.id, "first")

    assert (await post_chat(client, headers, mine.id)).status_code == 429


async def test_a_limit_of_zero_turns_the_quota_off(
    client, user, db, redis, scripted_llm, settings_override
):
    settings_override(CHAT_DAILY_LIMIT_PER_USER=0)
    account, headers = user
    conversation = await create_conversation(db, account.id, title="Existing chat")
    model = scripted_llm([["one"], ["two"], ["three"]])

    for message in ["first", "second", "third"]:
        await chat(client, headers, conversation.id, message)

    assert len(model.calls) == 3
    assert await redis.keys("quota:chat:*") == []


# --- login failures ----------------------------------------------------------------


async def test_account_is_locked_after_repeated_failures(client, db, settings_override):
    settings_override(LOGIN_MAX_FAILURES_PER_ACCOUNT=3)
    account = await create_user(db)
    wrong = {"username": account.email, "password": "wrong-password"}
    right = {"username": account.email, "password": DEFAULT_PASSWORD}

    failures = [await client.post(LOGIN, data=wrong) for _ in range(3)]
    locked = await client.post(LOGIN, data=right)

    assert [r.status_code for r in failures] == [401, 401, 401]
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "TOO_MANY_REQUESTS"


async def test_a_successful_login_clears_the_failure_count(
    client, db, redis, settings_override
):
    settings_override(LOGIN_MAX_FAILURES_PER_ACCOUNT=3)
    account = await create_user(db)
    wrong = {"username": account.email, "password": "wrong-password"}
    right = {"username": account.email, "password": DEFAULT_PASSWORD}

    for _ in range(2):
        await client.post(LOGIN, data=wrong)
    assert (await client.post(LOGIN, data=right)).status_code == 200
    assert await redis.keys("login_failures:*") == []

    for _ in range(2):
        await client.post(LOGIN, data=wrong)
    assert (await client.post(LOGIN, data=right)).status_code == 200


async def test_failures_for_one_account_do_not_lock_another(
    client, db, settings_override
):
    settings_override(LOGIN_MAX_FAILURES_PER_ACCOUNT=1)
    target = await create_user(db)
    bystander = await create_user(db)

    await client.post(LOGIN, data={"username": target.email, "password": "wrong"})
    response = await client.post(
        LOGIN, data={"username": bystander.email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 200


# --- registration ------------------------------------------------------------------


async def test_signups_pause_at_the_global_cap(client, settings_override):
    settings_override(REGISTRATION_MAX_GLOBAL=2)

    first = await client.post(REGISTER, json=signup(1))
    second = await client.post(REGISTER, json=signup(2))
    third = await client.post(REGISTER, json=signup(3))

    assert [first.status_code, second.status_code] == [201, 201]
    assert third.status_code == 429
    assert third.json()["error"]["message"].startswith("Sign-ups are paused")


async def test_per_ip_cap_is_ignored_unless_the_proxy_is_trusted(
    client, settings_override
):
    settings_override(REGISTRATION_MAX_PER_IP=1)
    headers = {"X-Real-IP": "203.0.113.7"}

    first = await client.post(REGISTER, json=signup(1), headers=headers)
    second = await client.post(REGISTER, json=signup(2), headers=headers)

    assert [first.status_code, second.status_code] == [201, 201]


async def test_per_ip_cap_applies_when_the_proxy_is_trusted(client, settings_override):
    settings_override(REGISTRATION_MAX_PER_IP=1, TRUST_PROXY_HEADERS=True)
    headers = {"X-Real-IP": "203.0.113.7"}

    first = await client.post(REGISTER, json=signup(1), headers=headers)
    second = await client.post(REGISTER, json=signup(2), headers=headers)
    other_network = await client.post(
        REGISTER, json=signup(3), headers={"X-Real-IP": "198.51.100.4"}
    )

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["message"].startswith("Too many sign-ups from this")
    assert other_network.status_code == 201


# --- one-at-a-time slots -----------------------------------------------------------


async def test_rate_limit_slot_is_exclusive_until_released(app):
    memory = app.state.redis_service
    user_id = uuid4()

    assert await memory.try_acquire_rate_limit(user_id, "bug_report", 60) is True
    assert await memory.try_acquire_rate_limit(user_id, "bug_report", 60) is False
    assert 0 < await memory.get_rate_limit_ttl(user_id, "bug_report") <= 60

    await memory.release_rate_limit(user_id, "bug_report")

    assert await memory.try_acquire_rate_limit(user_id, "bug_report", 60) is True
