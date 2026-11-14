"""Ordering and pagination that do not depend on ids (D5). Passes under both id strategies."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from schemas.models import AuditLog
from support.factories import chat, create_conversation, create_user


async def test_messages_of_20_turns_alternate_and_keep_send_order(
    client, user, db, scripted_llm
):
    account, headers = user
    scripted_llm([[f"reply {i}"] for i in range(20)])
    conversation = await create_conversation(db, account.id)

    for i in range(20):
        await chat(client, headers, conversation.id, f"question {i}")

    response = await client.get(
        f"/api/conversations/{conversation.id}/messages", headers=headers
    )

    assert response.status_code == 200
    messages = response.json()
    assert [m["role"] for m in messages] == ["user", "model"] * 20
    assert [m["content"] for m in messages] == [
        text for i in range(20) for text in (f"question {i}", f"reply {i}")
    ]


async def _collect_pages(client, url, headers, limit=10):
    pages = []
    cursor = None
    while True:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(url, headers=headers, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages


async def test_audit_logs_page_newest_first_with_every_row_once(client, admin, db):
    _, headers = admin
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    # Far in the future, so the admin's own login/request rows sort first; filter by path.
    ids = []
    for i in range(25):
        row = AuditLog(
            method="GET",
            path="/probe",
            status_code=200,
            duration_ms=1,
            created_at=base + timedelta(seconds=i),
        )
        db.add(row)
        await db.flush()
        ids.append(str(row.id))
    await db.commit()

    pages = []
    cursor = None
    while True:
        params = {"limit": 10, "path": "/probe"}
        if cursor:
            params["cursor"] = cursor
        response = await client.get("/api/admin/audit-logs", headers=headers, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert [len(p) for p in pages] == [10, 10, 5]
    returned = [row["id"] for page in pages for row in page]
    assert returned == list(reversed(ids))


async def test_admin_users_page_newest_first_with_every_row_once(client, admin, db):
    account, headers = admin
    created = [account.id]
    for _ in range(25):
        created.append((await create_user(db)).id)

    pages = await _collect_pages(client, "/api/admin/users", headers)

    assert [len(p) for p in pages] == [10, 10, 6]
    returned = [row["id"] for page in pages for row in page]
    assert returned == [str(i) for i in reversed(created)]


async def test_unknown_cursor_is_a_bad_request(client, admin):
    _, headers = admin
    for url in ("/api/admin/audit-logs", "/api/admin/users"):
        response = await client.get(url, headers=headers, params={"cursor": str(uuid4())})

        assert response.status_code == 400, url
        assert response.json()["error"]["code"] == "BAD_REQUEST"


def test_id_server_default_follows_the_strategy(settings_override):
    from core.config import Settings
    from core.ids import id_server_default

    assert Settings.model_fields["ID_STRATEGY"].default == "uuidv7"
    settings_override(ID_STRATEGY="uuidv7")
    assert str(id_server_default()) == "uuidv7()"
    settings_override(ID_STRATEGY="random")
    assert str(id_server_default()) == "gen_random_uuid()"
