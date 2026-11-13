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
    assert set(codes) <= {201, 409, 500}
    assert await count(db, User) == 1


@pytest.mark.xfail(reason="F16", strict=False)
async def test_concurrent_duplicate_registration_never_returns_500(make_client, db):
    responses = await register_many(make_client, 20, "race2@example.com")

    assert 500 not in {r.status_code for r in responses}


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


async def test_concurrent_logins_all_succeed_and_session_cap_is_not_exact(
    make_client, db, settings_override
):
    """Pins F15: all logins succeed; the cap of 5 is not enforced under concurrency."""
    settings_override(MAX_REFRESH_SESSIONS_PER_USER=5)

    _, responses = await concurrent_logins(make_client, db, 10)

    assert [r.status_code for r in responses] == [200] * 10
    assert await count(db, Session) >= 5


@pytest.mark.xfail(reason="F15", strict=False)
async def test_concurrent_logins_respect_the_session_cap(
    make_client, db, settings_override
):
    settings_override(MAX_REFRESH_SESSIONS_PER_USER=5)

    _, responses = await concurrent_logins(make_client, db, 10)

    assert [r.status_code for r in responses] == [200] * 10
    assert await count(db, Session) <= 5
