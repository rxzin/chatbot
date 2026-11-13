"""Registration, refresh and login fired concurrently, each caller a separate client."""

import asyncio
from collections import Counter

import pytest
from sqlalchemy import func, select

from schemas.models import Session, User
from support.factories import DEFAULT_PASSWORD, auth_headers, create_user

REFRESH_COOKIE = "refresh_token"


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def register_many(make_client, n: int, email: str):
    return await asyncio.gather(
        *[
            make_client().post(
                "/api/auth/register",
                json={"email": email, "password": DEFAULT_PASSWORD},
            )
            for _ in range(n)
        ]
    )


async def test_concurrent_registrations_of_one_email_create_one_user(make_client, db):
    responses = await register_many(make_client, 20, "race@example.com")

    codes = Counter(r.status_code for r in responses)
    assert codes[201] == 1
    # The losers hit the unique index, not the pre-check; still a 409, never a 500 (F16).
    assert codes == {201: 1, 409: 19}
    assert await count(db, User) == 1


async def test_concurrent_refreshes_with_one_cookie_have_one_winner(
    client, make_client, user, db
):
    old_cookie = client.cookies.get(REFRESH_COOKIE)
    clients = [make_client() for _ in range(10)]
    for c in clients:
        c.cookies.set(REFRESH_COOKIE, old_cookie)

    responses = await asyncio.gather(*[c.post("/api/auth/refresh") for c in clients])

    codes = Counter(r.status_code for r in responses)
    assert codes == {200: 1, 409: 9}
    assert await count(db, Session) == 1
    (winning,) = [r for r in responses if r.status_code == 200]
    new_cookie = winning.cookies.get(REFRESH_COOKIE)
    assert new_cookie and new_cookie != old_cookie
    fresh = make_client()
    fresh.cookies.set(REFRESH_COOKIE, new_cookie)
    follow_up = await fresh.post("/api/auth/refresh")
    assert follow_up.status_code == 200
    token = follow_up.json()["access_token"]
    me = await fresh.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 200


async def concurrent_logins(make_client, db, n: int):
    account = await create_user(db)
    responses = await asyncio.gather(
        *[
            make_client().post(
                "/api/auth/login",
                data={"username": account.email, "password": DEFAULT_PASSWORD},
            )
            for _ in range(n)
        ]
    )
    return account, responses


async def test_concurrent_logins_respect_the_session_cap(
    make_client, db, settings_override
):
    settings_override(MAX_REFRESH_SESSIONS_PER_USER=5)

    _, responses = await concurrent_logins(make_client, db, 10)

    assert [r.status_code for r in responses] == [200] * 10
    assert await count(db, Session) <= 5
