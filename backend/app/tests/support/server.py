"""Serve the app on a real socket, for tests that must drop a connection mid-stream."""

import asyncio
import socket
from contextlib import asynccontextmanager

import uvicorn


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@asynccontextmanager
async def serve(app):
    """
    Run `app` under uvicorn inside the current event loop and yield its base URL.

    The app must already be started: lifespan is off here, because the app's database
    engine and Redis client belong to this loop and are started by the `app` fixture.
    """
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, lifespan="off", log_level="warning"
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(500):
            if server.started:
                break
            if task.done():
                task.result()
            await asyncio.sleep(0.01)
        else:
            raise RuntimeError("test server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
