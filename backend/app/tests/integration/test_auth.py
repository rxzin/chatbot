"""Registration, login, token refresh and logout through the real endpoints."""

from sqlalchemy import func, select

from schemas.models import Session, User
from support.factories import DEFAULT_PASSWORD, auth_headers, create_user, login

REFRESH_COOKIE = "refresh_token"
BAD_LOGIN = "Incorrect email or password"


def error(response) -> dict:
    """The app's error body is {"success": false, "error": {"code", "message"}}."""
    body = response.json()
    assert body["success"] is False
    return body["error"]


async def session_count(db) -> int:
    return await db.scalar(select(func.count()).select_from(Session))


def cookie_header(refresh_token: str) -> dict[str, str]:
    return {"Cookie": f"{REFRESH_COOKIE}={refresh_token}"}


# --- register ----------------------------------------------------------------------


async def test_register_creates_a_user_with_the_users_role(client, db):
    response = await client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 201
    assert set(response.json()) == {"id", "email"}
    assert response.json()["email"] == "new@example.com"

    token = await login(client, "new@example.com")
    me = await client.get("/api/auth/me", headers=auth_headers(token))
    assert "ai:chat" in me.json()["permissions"]


async def test_register_duplicate_email_conflicts(client, db):
    await create_user(db, email="taken@example.com")

    response = await client.post(
        "/api/auth/register",
        json={"email": "taken@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 409
    assert error(response)["code"] == "CONFLICT"
    assert await db.scalar(select(func.count()).select_from(User)) == 1


async def test_register_rejects_a_short_password(client):
    response = await client.post(
        "/api/auth/register", json={"email": "new@example.com", "password": "1234567"}
    )

    assert response.status_code == 422


async def test_register_can_be_turned_off(client, settings_override):
    settings_override(ALLOW_PUBLIC_REGISTRATION=False)

    response = await client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 403
    assert error(response)["code"] == "FORBIDDEN"


# --- login -------------------------------------------------------------------------


async def test_login_returns_a_token_and_sets_the_refresh_cookie(client, db):
    account = await create_user(db)

    response = await client.post(
        "/api/auth/login",
        data={"username": account.email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type"}
    assert response.json()["token_type"] == "bearer"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{REFRESH_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "Path=/api/auth" in cookie
    assert "SameSite=lax" in cookie
    assert await session_count(db) == 1


async def test_login_failures_do_not_reveal_which_part_was_wrong(client, db):
    account = await create_user(db)

    wrong_password = await client.post(
        "/api/auth/login", data={"username": account.email, "password": "wrong-one"}
    )
    unknown_email = await client.post(
        "/api/auth/login",
        data={"username": "nobody@example.com", "password": DEFAULT_PASSWORD},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert error(wrong_password)["message"] == BAD_LOGIN
    assert error(unknown_email)["message"] == BAD_LOGIN
    assert await session_count(db) == 0


async def test_login_rejects_an_inactive_user(client, db):
    account = await create_user(db, is_active=False)

    response = await client.post(
        "/api/auth/login",
        data={"username": account.email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 401
    assert error(response)["message"] == BAD_LOGIN


# --- me ----------------------------------------------------------------------------


async def test_me_returns_sorted_permissions(client, user):
    account, headers = user

    response = await client.get("/api/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(account.id)
    assert body["email"] == account.email
    assert body["permissions"] == sorted(body["permissions"])
    assert len(body["permissions"]) > 1


async def test_me_requires_a_token(client):
    response = await client.get("/api/auth/me")

    assert response.status_code == 401


async def test_me_rejects_a_refresh_token_used_as_an_access_token(client, user):
    refresh_token = client.cookies.get(REFRESH_COOKIE)

    response = await client.get("/api/auth/me", headers=auth_headers(refresh_token))

    assert response.status_code == 401


# --- refresh -----------------------------------------------------------------------


async def test_refresh_rotates_the_cookie_and_issues_a_new_access_token(client, user):
    _, headers = user
    old_cookie = client.cookies.get(REFRESH_COOKIE)

    response = await client.post("/api/auth/refresh")

    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert auth_headers(new_token) != headers
    assert client.cookies.get(REFRESH_COOKIE) != old_cookie
    me = await client.get("/api/auth/me", headers=auth_headers(new_token))
    assert me.status_code == 200


async def test_refresh_requires_the_cookie(client):
    response = await client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert error(response)["message"] == "Refresh token is required"


async def test_refresh_rejects_an_access_token_in_the_cookie(make_client, user):
    _, headers = user
    access_token = headers["Authorization"].removeprefix("Bearer ")

    response = await make_client().post(
        "/api/auth/refresh", headers=cookie_header(access_token)
    )

    assert response.status_code == 401


async def test_old_cookie_inside_the_grace_period_gets_a_conflict(
    client, make_client, user, db
):
    """Two tabs refreshing together is normal, so the session survives."""
    old_cookie = client.cookies.get(REFRESH_COOKIE)
    assert (await client.post("/api/auth/refresh")).status_code == 200

    replay = await make_client().post(
        "/api/auth/refresh", headers=cookie_header(old_cookie)
    )

    assert replay.status_code == 409
    assert error(replay)["code"] == "CONFLICT"
    assert await session_count(db) == 1


async def test_old_cookie_outside_the_grace_period_revokes_the_session(
    client, make_client, user, db, settings_override
):
    """An old token used later means it was copied, so everyone is logged out."""
    settings_override(REFRESH_REUSE_GRACE_SECONDS=-1)
    old_cookie = client.cookies.get(REFRESH_COOKIE)
    rotated = await client.post("/api/auth/refresh")
    new_access_token = rotated.json()["access_token"]

    replay = await make_client().post(
        "/api/auth/refresh", headers=cookie_header(old_cookie)
    )

    assert replay.status_code == 401
    assert await session_count(db) == 0
    me = await client.get("/api/auth/me", headers=auth_headers(new_access_token))
    assert me.status_code == 401
    assert (await client.post("/api/auth/refresh")).status_code == 401


# --- logout ------------------------------------------------------------------------


async def test_logout_ends_the_session(client, user, db):
    _, headers = user

    response = await client.post("/api/auth/logout", headers=headers)

    assert response.status_code == 200
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f'{REFRESH_COOKIE}=""')
    assert "Max-Age=0" in cleared
    assert await session_count(db) == 0
    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 401


async def test_logout_requires_an_access_token(client, user, db):
    response = await client.post("/api/auth/logout")

    assert response.status_code == 401
    assert await session_count(db) == 1


async def test_clear_session_works_without_an_access_token(client, user, db):
    response = await client.post("/api/auth/clear-session")

    assert response.status_code == 200
    assert await session_count(db) == 0
