"""Shared test setup. The first lines must run before anything from the app is imported."""

import os
import subprocess
import sys
from pathlib import Path

# The app reads its settings when modules are first imported. Pointing it at test.env
# here keeps every test away from backend/app/.env, which holds real keys.
os.environ.setdefault("APP_ENV_FILE", str(Path(__file__).parent / "test.env"))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.config import getSettings  # noqa: E402
from support.factories import auth_headers, create_user, login  # noqa: E402
from support.fakes import ScriptedLLM  # noqa: E402
from support.guard import assert_safe_test_target  # noqa: E402

# Refuse to go any further unless the process is pointed at the disposable test stack.
assert_safe_test_target(getSettings())

APP_DIR = Path(__file__).resolve().parents[1]

# Every table tests write to. Roles and permissions are seeded once and kept.
_TRUNCATE = (
    "TRUNCATE audit_logs, llm_usage, pending_jira_tickets, documents, messages, "
    "session, conversations, users CASCADE"
)


@pytest.fixture(scope="session")
def _schema():
    """
    Build the schema with the real migrations, which also proves they apply to an
    empty database. A subprocess, because alembic's env.py starts its own event loop.
    """
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=APP_DIR,
        check=True,
        capture_output=True,
    )


@pytest_asyncio.fixture(scope="session")
async def app(_schema):
    """The real application, started once, with fake external services."""
    import seed
    from core.database import SessionLocal, engine
    from main import app as application

    async with SessionLocal() as session:
        await seed.seed_roles(session, await seed.seed_permissions(session))

    async with LifespanManager(application):
        yield application
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean(request):
    """
    Give each test that uses the app an empty database, Redis and audit queue.

    Tests that never ask for the app (the unit tests) skip this, so they run without
    Docker. Session fixtures are set up first, so the app is already running here.
    """
    if "app" not in request.fixturenames:
        yield
        return

    from core.database import engine
    from main import app as application

    writer = application.state.audit_writer
    while writer._drain():
        pass
    async with engine.begin() as connection:
        await connection.execute(text(_TRUNCATE))
    await application.state.redis_service.redis_client.flushdb()
    # The fake vector store lives as long as the app, so empty it too.
    application.state.vector_store_service.chunks.clear()
    yield


@pytest_asyncio.fixture
async def make_client(app):
    """A factory for clients. Each has its own cookie jar, like a separate browser."""
    clients: list[AsyncClient] = []

    def factory() -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()


@pytest_asyncio.fixture
async def client(make_client) -> AsyncClient:
    return make_client()


@pytest_asyncio.fixture
async def db(app):
    from core.database import SessionLocal

    async with SessionLocal() as session:
        yield session


@pytest.fixture
def redis(app):
    return app.state.redis_service.redis_client


@pytest.fixture
def settings_override(monkeypatch):
    """Change settings for one test: settings_override(CHAT_DAILY_LIMIT_PER_USER=2)."""
    settings = getSettings()

    def override(**values) -> None:
        for name, value in values.items():
            assert hasattr(settings, name), f"unknown setting {name}"
            monkeypatch.setattr(settings, name, value)

    return override


@pytest.fixture
def app_state_override(app):
    """
    Replace a service on app.state for one test: app_state_override(llm_service=...).

    Not monkeypatch: app.state keeps its values in an inner dict, so monkeypatch
    cannot see the original and deletes the attribute when the test ends.
    """
    original: dict = {}

    def override(**services) -> None:
        for name, service in services.items():
            original.setdefault(name, getattr(app.state, name))
            setattr(app.state, name, service)

    yield override
    for name, service in original.items():
        setattr(app.state, name, service)


@pytest.fixture
def scripted_llm(app_state_override):
    """Replace the model for one test: scripted_llm([["Hi ", "there"]])."""

    def install(turns, completion="Test Title") -> ScriptedLLM:
        model = ScriptedLLM(turns, completion)
        app_state_override(llm_service=model)
        return model

    return install


@pytest_asyncio.fixture
async def user(client, db):
    """A logged-in user with the "users" role. The refresh cookie is in `client`."""
    account = await create_user(db)
    return account, auth_headers(await login(client, account.email))


@pytest_asyncio.fixture
async def admin(make_client, db):
    """A logged-in admin. Uses its own client, so `client` keeps the user's cookie."""
    account = await create_user(db, role="admin")
    return account, auth_headers(await login(make_client(), account.email))


@pytest.fixture
def flush_audit(app):
    """Write queued audit rows now, instead of waiting for the one-second timer."""

    async def flush() -> None:
        writer = app.state.audit_writer
        while batch := writer._drain():
            await writer._flush(batch)

    return flush
