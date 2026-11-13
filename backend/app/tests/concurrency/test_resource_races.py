"""Conversation creation, listing under pool pressure, and ticket approval."""

import asyncio
from collections import Counter

import respx
from sqlalchemy import func, select

from schemas.models import Conversation, PendingJiraTicket
from support.factories import auth_headers, create_user, login

JIRA_ISSUE = "https://jira.example.com/rest/api/3/issue"


async def test_concurrent_conversation_creation_makes_distinct_rows(
    make_client, user, db
):
    _, headers = user

    responses = await asyncio.gather(
        *[
            make_client().post("/api/conversations", headers=headers, json={})
            for _ in range(50)
        ]
    )

    assert {r.status_code for r in responses} <= {200, 201}
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 50
    assert await db.scalar(select(func.count()).select_from(Conversation)) == 50


async def test_concurrent_listing_beyond_the_pool_size_all_succeed(
    make_client, user, db
):
    _, headers = user

    responses = await asyncio.gather(
        *[make_client().get("/api/conversations", headers=headers) for _ in range(50)]
    )

    assert [r.status_code for r in responses] == [200] * 50


async def test_two_admins_approving_one_ticket_call_jira_once(make_client, user, db):
    account, _ = user
    ticket = PendingJiraTicket(
        user_id=account.id, title="Broken", description="It breaks", status="pending"
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    ticket_id = ticket.id
    admins = []
    for _ in range(2):
        admin = await create_user(db, role="admin")
        admins.append(auth_headers(await login(make_client(), admin.email)))

    with respx.mock(assert_all_called=False) as router:
        route = router.post(JIRA_ISSUE).respond(json={"key": "TEST-1"})
        responses = await asyncio.gather(
            *[
                make_client().post(
                    f"/api/admin/approve-ticket/{ticket_id}", headers=headers
                )
                for headers in admins
            ]
        )

    assert route.call_count == 1
    assert Counter(r.status_code for r in responses)[200] >= 1
    assert sum(1 for r in responses if r.json().get("success") is True) >= 1
    await db.refresh(ticket)
    assert (ticket.status, ticket.jira_key) == ("approved", "TEST-1")
