"""Session lifetime, the per-user session cap, and admin control over sessions."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from schemas.models import Session
from support.factories import DEFAULT_PASSWORD, auth_headers, create_user, login

ME = "/api/auth/me"


async def session_count(db, user_id=None) -> int:
    query = select(func.count()).select_from(Session)
    if user_id is not None:
        query = query.where(Session.user_id == user_id)
    return await db.scalar(query)


async def session_ids(db, user_id) -> list:
    rows = await db.execute(
        select(Session.id)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at)
    )
    return list(rows.scalars())


# --- expiry ------------------------------------------------------------------------


@pytest.mark.parametrize("column", ["expires_at", "absolute_expires_at"])
async def test_expired_session_stops_working_and_is_removed(client, user, db, column):
    _, headers = user
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.execute(update(Session).values({column: past}))
    await db.commit()

    me = await client.get(ME, headers=headers)
    refresh = await client.post("/api/auth/refresh")

    assert me.status_code == 401
    assert refresh.status_code == 401
    assert refresh.json()["error"]["message"] == "Refresh token has expired"
    assert await session_count(db) == 0


# --- several sessions --------------------------------------------------------------


async def test_each_login_is_its_own_session(make_client, db):
    account = await create_user(db)
    laptop, phone = make_client(), make_client()
    laptop_headers = auth_headers(await login(laptop, account.email))
    phone_headers = auth_headers(await login(phone, account.email))
    assert await session_count(db) == 2

    logout = await laptop.post("/api/auth/logout", headers=laptop_headers)

    assert logout.status_code == 200
    assert await session_count(db) == 1
    assert (await laptop.get(ME, headers=laptop_headers)).status_code == 401
    assert (await phone.get(ME, headers=phone_headers)).status_code == 200
    assert (await phone.post("/api/auth/refresh")).status_code == 200


async def test_oldest_session_is_dropped_at_the_cap(make_client, db, settings_override):
    settings_override(MAX_REFRESH_SESSIONS_PER_USER=5)
    account = await create_user(db)

    tokens = [await login(make_client(), account.email) for _ in range(6)]

    assert await session_count(db) == 5
    first = await make_client().get(ME, headers=auth_headers(tokens[0]))
    newest = await make_client().get(ME, headers=auth_headers(tokens[-1]))
    assert first.status_code == 401
    assert newest.status_code == 200


# --- admin revocation --------------------------------------------------------------


async def test_admin_revokes_one_session(client, make_client, user, admin, db):
    account, headers = user
    _, admin_headers = admin
    other_device = auth_headers(await login(make_client(), account.email))
    first_session, second_session = await session_ids(db, account.id)

    response = await client.delete(
        f"/api/admin/sessions/{first_session}", headers=admin_headers
    )

    assert response.status_code == 200
    assert (await client.get(ME, headers=headers)).status_code == 401
    assert (await client.get(ME, headers=other_device)).status_code == 200
    assert await session_ids(db, account.id) == [second_session]


async def test_admin_cannot_revoke_their_own_current_session(client, admin, db):
    admin_account, admin_headers = admin
    (own_session,) = await session_ids(db, admin_account.id)

    response = await client.delete(
        f"/api/admin/sessions/{own_session}", headers=admin_headers
    )

    assert response.status_code == 400
    assert await session_count(db, admin_account.id) == 1


async def test_admin_revokes_all_of_a_users_sessions(
    client, make_client, user, admin, db
):
    account, headers = user
    _, admin_headers = admin
    other_device = auth_headers(await login(make_client(), account.email))

    response = await client.post(
        f"/api/admin/users/{account.id}/revoke-sessions", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Revoked 2 session(s)."
    assert (await client.get(ME, headers=headers)).status_code == 401
    assert (await client.get(ME, headers=other_device)).status_code == 401
    assert await session_count(db, account.id) == 0
    # Signed out, not banned: the user can log straight back in.
    await login(make_client(), account.email)


# --- ban ---------------------------------------------------------------------------


async def test_ban_ends_sessions_and_blocks_login_until_unbanned(
    client, make_client, user, admin, db
):
    account, headers = user
    _, admin_headers = admin
    credentials = {"username": account.email, "password": DEFAULT_PASSWORD}

    ban = await client.post(
        f"/api/admin/users/{account.id}/ban", headers=admin_headers
    )

    assert ban.status_code == 200
    assert (await client.get(ME, headers=headers)).status_code == 401
    assert await session_count(db, account.id) == 0
    blocked = await make_client().post("/api/auth/login", data=credentials)
    assert blocked.status_code == 401

    unban = await client.post(
        f"/api/admin/users/{account.id}/unban", headers=admin_headers
    )

    assert unban.status_code == 200
    restored = await make_client().post("/api/auth/login", data=credentials)
    assert restored.status_code == 200


async def test_admin_cannot_ban_themselves_or_another_admin(client, admin, db):
    admin_account, admin_headers = admin
    other_admin = await create_user(db, role="admin")

    own = await client.post(
        f"/api/admin/users/{admin_account.id}/ban", headers=admin_headers
    )
    peer = await client.post(
        f"/api/admin/users/{other_admin.id}/ban", headers=admin_headers
    )

    assert own.status_code == 400
    assert peer.status_code == 400
