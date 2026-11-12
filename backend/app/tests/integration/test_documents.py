"""Uploading, indexing, listing, deleting and searching documents."""

import os

import pytest
import pytest_asyncio
from sqlalchemy import func, select

import api.routes.documents as documents_route
from schemas.models import Document
from services.base import ToolCall
from services.fakes import FakeEmbeddingService
from support.factories import (
    auth_headers,
    chat,
    create_conversation,
    create_user,
    login,
)

NOTES = b"The warranty lasts two years. Returns are accepted within thirty days."


def text_file(name="notes.txt", body=NOTES, content_type="text/plain") -> dict:
    return {"file": (name, body, content_type)}


def upload_url(conversation_id) -> str:
    return f"/api/conversations/{conversation_id}/documents/upload"


def list_url(conversation_id) -> str:
    return f"/api/conversations/{conversation_id}/documents"


class FailingEmbeddings(FakeEmbeddingService):
    async def embed_texts(self, texts):
        raise RuntimeError("embedding provider is down")


@pytest_asyncio.fixture
async def conversation(user, db):
    account, _ = user
    return await create_conversation(db, account.id, title="Existing chat")


@pytest.fixture
def vector_store(app):
    return app.state.vector_store_service


@pytest.fixture
def temp_files(monkeypatch):
    """The temp files uploads were saved to, so a test can check they were removed."""
    paths: list[str] = []
    original = documents_route.save_uploaded_file_to_temp

    async def recording(file):
        path, size = await original(file)
        paths.append(path)
        return path, size

    monkeypatch.setattr(documents_route, "save_uploaded_file_to_temp", recording)
    return paths


async def document_count(db) -> int:
    return await db.scalar(select(func.count()).select_from(Document))


# --- upload and indexing -----------------------------------------------------------


async def test_upload_is_accepted_then_indexed(
    client, user, conversation, vector_store, temp_files
):
    account, headers = user

    accepted = await client.post(
        upload_url(conversation.id), headers=headers, files=text_file()
    )

    assert accepted.status_code == 202
    body = accepted.json()
    assert body["status"] == "processing"
    assert body["filename"] == "notes.txt"
    assert body["conversationId"] == str(conversation.id)
    assert body["size_bytes"] == len(NOTES)

    # Indexing runs as a background task, which has finished by the time the test
    # client returns the response.
    listed = await client.get(list_url(conversation.id), headers=headers)

    (document,) = listed.json()
    assert document["id"] == body["id"]
    assert document["status"] == "indexed"
    assert document["chunkCount"] >= 1
    assert document["errorMessage"] is None
    (chunks,) = vector_store.chunks.values()
    assert len(chunks) == document["chunkCount"]
    assert chunks[0].user_id == account.id
    assert "warranty" in chunks[0].content
    (temp_path,) = temp_files
    assert not os.path.exists(temp_path)


@pytest.mark.parametrize(
    "files, limit",
    [
        (text_file(body=b""), None),
        (text_file("evil.exe", b"MZ...", "application/octet-stream"), None),
        (text_file(body=b"x" * 11), 10),
    ],
    ids=["empty", "wrong type", "too large"],
)
async def test_invalid_uploads_are_rejected(
    client, user, conversation, db, settings_override, temp_files, files, limit
):
    _, headers = user
    if limit is not None:
        settings_override(MAX_UPLOAD_BYTES=limit)

    response = await client.post(
        upload_url(conversation.id), headers=headers, files=files
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNPROCESSABLE_ENTITY"
    assert await document_count(db) == 0
    assert temp_files == []


async def test_upload_to_another_users_conversation_is_refused(
    client, make_client, user, conversation, db, vector_store, temp_files
):
    stranger = await create_user(db)
    stranger_headers = auth_headers(await login(make_client(), stranger.email))

    response = await client.post(
        upload_url(conversation.id), headers=stranger_headers, files=text_file()
    )

    assert response.status_code == 404
    assert await document_count(db) == 0
    assert vector_store.chunks == {}
    (temp_path,) = temp_files
    assert not os.path.exists(temp_path)


async def test_indexing_failure_is_recorded_on_the_document(
    client, user, conversation, vector_store, app_state_override, temp_files
):
    _, headers = user
    app_state_override(embedding_service=FailingEmbeddings())

    accepted = await client.post(
        upload_url(conversation.id), headers=headers, files=text_file()
    )
    listed = await client.get(list_url(conversation.id), headers=headers)

    assert accepted.status_code == 202
    (document,) = listed.json()
    assert document["status"] == "failed"
    assert document["errorMessage"] == "embedding provider is down"
    assert document["chunkCount"] == 0
    assert vector_store.chunks == {}
    assert not os.path.exists(temp_files[0])


async def test_file_with_no_readable_text_fails_indexing(client, user, conversation):
    _, headers = user

    await client.post(
        upload_url(conversation.id), headers=headers, files=text_file(body=b"  \n \n")
    )
    listed = await client.get(list_url(conversation.id), headers=headers)

    (document,) = listed.json()
    assert document["status"] == "failed"
    assert "No readable text" in document["errorMessage"]


# --- list and delete ---------------------------------------------------------------


async def test_list_shows_only_this_conversations_documents(client, user, db):
    account, headers = user
    first = await create_conversation(db, account.id, title="first")
    second = await create_conversation(db, account.id, title="second")
    await client.post(upload_url(first.id), headers=headers, files=text_file("a.txt"))
    await client.post(upload_url(second.id), headers=headers, files=text_file("b.txt"))

    listed = await client.get(list_url(first.id), headers=headers)

    assert [d["filename"] for d in listed.json()] == ["a.txt"]


async def test_delete_removes_the_row_and_its_chunks(
    client, user, conversation, db, vector_store
):
    _, headers = user
    uploaded = await client.post(
        upload_url(conversation.id), headers=headers, files=text_file()
    )
    assert vector_store.chunks != {}

    response = await client.delete(
        f"{list_url(conversation.id)}/{uploaded.json()['id']}", headers=headers
    )

    assert response.status_code == 204
    assert await document_count(db) == 0
    assert vector_store.chunks == {}


async def test_another_user_cannot_see_or_delete_a_document(
    client, make_client, user, conversation, db, vector_store
):
    _, headers = user
    uploaded = await client.post(
        upload_url(conversation.id), headers=headers, files=text_file()
    )
    stranger = await create_user(db)
    stranger_headers = auth_headers(await login(make_client(), stranger.email))
    own_conversation = await create_conversation(db, stranger.id)
    document_id = uploaded.json()["id"]

    listed = await client.get(list_url(conversation.id), headers=stranger_headers)
    deleted = await client.delete(
        f"{list_url(conversation.id)}/{document_id}", headers=stranger_headers
    )
    via_own_conversation = await client.delete(
        f"{list_url(own_conversation.id)}/{document_id}", headers=stranger_headers
    )

    assert listed.status_code == 404
    assert deleted.status_code == 404
    assert via_own_conversation.status_code == 404
    assert await document_count(db) == 1
    assert vector_store.chunks != {}


# --- retrieval ---------------------------------------------------------------------


async def test_chat_can_search_an_indexed_document(
    client, user, conversation, db, scripted_llm
):
    _, headers = user
    uploaded = await client.post(
        upload_url(conversation.id), headers=headers, files=text_file()
    )
    search = [ToolCall("c1", "search_documents", {"query": "how long is the warranty"})]
    model = scripted_llm([[search], ["Two years [1]."]])

    events = await chat(client, headers, conversation.id, "how long is the warranty?")

    kinds = [event["type"] for event in events]
    assert kinds == ["tool-start", "tool-result", "text-delta", "sources", "done"]
    (source,) = events[3]["sources"]
    assert source["number"] == 1
    assert source["filename"] == "notes.txt"
    assert source["documentId"] == uploaded.json()["id"]
    assert "warranty" in source["snippet"]

    assert "search_documents" in {tool.name for tool in model.calls[0]["tools"]}
    assert "notes.txt" in model.calls[0]["instructions"]
    passage = model.calls[1]["exchanges"][0].results[0].content
    assert "[1] notes.txt" in passage
    assert "warranty lasts two years" in passage

    from schemas.models import Message

    parts = await db.scalar(select(Message.parts).where(Message.role == "model"))
    assert [part["type"] for part in parts] == ["text", "sources"]
    assert parts[1]["sources"][0]["number"] == 1


async def test_search_is_not_offered_while_a_document_is_unindexed(
    client, user, conversation, scripted_llm, app_state_override
):
    _, headers = user
    app_state_override(embedding_service=FailingEmbeddings())
    await client.post(upload_url(conversation.id), headers=headers, files=text_file())
    model = scripted_llm([["hello"]])

    await chat(client, headers, conversation.id, "hi")

    assert "search_documents" not in {tool.name for tool in model.calls[0]["tools"]}


async def test_search_cannot_reach_another_users_document(
    client, make_client, user, conversation, db, scripted_llm
):
    """Each user's chunks are kept apart, so a search never crosses accounts."""
    _, headers = user
    await client.post(upload_url(conversation.id), headers=headers, files=text_file())
    stranger = await create_user(db)
    stranger_headers = auth_headers(await login(make_client(), stranger.email))
    theirs = await create_conversation(db, stranger.id, title="Existing chat")
    await client.post(
        upload_url(theirs.id),
        headers=stranger_headers,
        files=text_file("other.txt", b"Nothing about warranties here."),
    )
    search = [ToolCall("c1", "search_documents", {"query": "warranty"})]
    model = scripted_llm([[search], ["done"]])

    events = await chat(client, stranger_headers, theirs.id, "warranty?")

    (sources_event,) = [e for e in events if e["type"] == "sources"]
    assert [s["filename"] for s in sources_event["sources"]] == ["other.txt"]
    assert "two years" not in model.calls[1]["exchanges"][0].results[0].content
