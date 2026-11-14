import pytest_asyncio

from support.server import serve


@pytest_asyncio.fixture(scope="session")
async def live_server(app):
    """The running app on a real local port, for tests that disconnect mid-stream."""
    async with serve(app) as base_url:
        yield base_url
