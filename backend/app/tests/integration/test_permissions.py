"""Who may call what: no token, the wrong role, and permissions changed mid-session."""

import re
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from schemas.models import AuditLog, user_roles_table
from support.factories import auth_headers, create_user, login

ANY_ID = uuid4()

ADMIN_ROUTES = [
    ("GET", "/api/admin/users"),
    ("GET", f"/api/admin/users/{ANY_ID}/sessions"),
    ("DELETE", f"/api/admin/sessions/{ANY_ID}"),
    ("POST", f"/api/admin/users/{ANY_ID}/revoke-sessions"),
    ("POST", f"/api/admin/users/{ANY_ID}/ban"),
    ("POST", f"/api/admin/users/{ANY_ID}/unban"),
    ("GET", "/api/admin/pending-tickets"),
    ("POST", f"/api/admin/approve-ticket/{ANY_ID}"),
    ("POST", f"/api/admin/reject-ticket/{ANY_ID}"),
    ("GET", "/api/admin/summary"),
    ("GET", "/api/admin/audit-logs"),
    ("GET", "/api/admin/usage"),
]

USER_ROUTES = [
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/conversations"),
    ("POST", "/api/conversations"),
    ("GET", f"/api/conversations/{ANY_ID}"),
    ("GET", f"/api/conversations/{ANY_ID}/messages"),
    ("POST", "/api/chat"),
    ("POST", f"/api/conversations/{ANY_ID}/documents/upload"),
    ("GET", f"/api/conversations/{ANY_ID}/documents"),
    ("DELETE", f"/api/conversations/{ANY_ID}/documents/{ANY_ID}"),
]


def route_id(route) -> str:
    return f"{route[0]} {route[1].replace(str(ANY_ID), '{id}')}"


PUBLIC_ROUTES = {
    "GET /health/",
    "POST /api/auth/login",
    "POST /api/auth/register",
    "POST /api/auth/refresh",
    "POST /api/auth/clear-session",
}


def test_every_route_is_either_public_or_checked_below(app):
    """A new route must be added to a list here, or the checks below silently skip it."""
    in_app = {
        f"{method.upper()} {re.sub(r'{[^}]+}', '{id}', path)}"
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    listed = {route_id(route) for route in ADMIN_ROUTES + USER_ROUTES}

    assert in_app == listed | PUBLIC_ROUTES


@pytest.mark.parametrize(
    "method, path",
    ADMIN_ROUTES + USER_ROUTES,
    ids=[route_id(route) for route in ADMIN_ROUTES + USER_ROUTES],
)
async def test_no_token_is_rejected(client, method, path):
    response = await client.request(method, path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    # Pins current behaviour: a missing token is rejected by FastAPI's own security
    # helper, so the body is not the app's usual {"success", "error"} shape.
    assert response.json() == {"detail": "Not authenticated"}


async def test_invalid_token_uses_the_app_error_body(client):
    response = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-token"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "method, path", ADMIN_ROUTES, ids=[route_id(route) for route in ADMIN_ROUTES]
)
async def test_ordinary_user_cannot_use_admin_routes(client, user, method, path):
    _, headers = user

    response = await client.request(method, path, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/users",
        "/api/admin/pending-tickets",
        "/api/admin/summary",
        "/api/admin/audit-logs",
        "/api/admin/usage",
    ],
)
async def test_admin_can_read_admin_pages(client, admin, path):
    _, admin_headers = admin

    response = await client.get(path, headers=admin_headers)

    assert response.status_code == 200


async def test_user_without_a_role_has_no_access(client, db):
    account = await create_user(db, role=None)
    headers = auth_headers(await login(client, account.email))

    me = await client.get("/api/auth/me", headers=headers)
    conversations = await client.get("/api/conversations", headers=headers)

    assert me.json()["permissions"] == []
    assert conversations.status_code == 403


async def test_removing_a_role_takes_effect_on_the_next_request(client, user, db):
    """Permissions are read from the database each time, not stored in the token."""
    account, headers = user
    assert (await client.get("/api/conversations", headers=headers)).status_code == 200

    await db.execute(
        delete(user_roles_table).where(user_roles_table.c.user_id == account.id)
    )
    await db.commit()

    response = await client.get("/api/conversations", headers=headers)

    assert response.status_code == 403


async def test_denied_request_is_attributed_in_the_audit_log(
    client, user, db, flush_audit
):
    account, headers = user

    await client.get("/api/admin/users", headers=headers)
    await flush_audit()

    rows = await db.execute(
        select(AuditLog).where(AuditLog.path == "/api/admin/users")
    )
    (entry,) = rows.scalars().all()
    assert entry.user_id == account.id
    assert entry.status_code == 403
    assert entry.method == "GET"


async def test_unauthenticated_request_is_logged_without_a_user(
    client, db, flush_audit
):
    await client.get("/api/conversations")
    await flush_audit()

    rows = await db.execute(
        select(AuditLog).where(AuditLog.path == "/api/conversations")
    )
    (entry,) = rows.scalars().all()
    assert entry.user_id is None
    assert entry.status_code == 401
