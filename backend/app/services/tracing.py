"""
Langfuse tracing: one trace per chat turn, with an observation for each model call and
tool call. Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set; then every
helper here is a no-op.
"""

from contextlib import contextmanager
from typing import Any, Iterator, Optional

from core.logging import logger

_client = None


class _NoOp:
    def update(self, **_: Any) -> "_NoOp":
        return self


def init_tracing(settings) -> bool:
    global _client
    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return False
    try:
        from langfuse import Langfuse

        options: dict[str, Any] = {
            "public_key": settings.LANGFUSE_PUBLIC_KEY,
            "secret_key": settings.LANGFUSE_SECRET_KEY,
            "base_url": settings.LANGFUSE_BASE_URL,
            "environment": settings.ENVIRONMENT,
        }
        if not settings.LANGFUSE_CAPTURE_CONTENT:
            # Keep timings, models and token counts, but not what users wrote or read.
            options["mask"] = lambda *, data, **_: "[redacted]"
        _client = Langfuse(**options)
        return True
    except Exception:
        logger.exception("Langfuse failed to start; tracing is off")
        _client = None
        return False


def shutdown_tracing() -> None:
    if _client is not None:
        try:
            _client.flush()
            _client.shutdown()
        except Exception:
            logger.exception("Langfuse failed to flush")


@contextmanager
def trace_turn(user_id: Any, conversation_id: Any, message: str) -> Iterator[Any]:
    """The root of a chat turn's trace, grouped by conversation as a Langfuse session."""
    if _client is None:
        yield _NoOp()
        return
    from langfuse import propagate_attributes

    with propagate_attributes(user_id=str(user_id), session_id=str(conversation_id), trace_name="chat-turn"):
        with _client.start_as_current_observation(name="chat-turn", as_type="agent", input=message) as root:
            yield root


@contextmanager
def observe(name: str, as_type: str = "span", input: Optional[Any] = None, **fields: Any) -> Iterator[Any]:
    """A child observation: as_type is "generation" for model calls, "tool" for tools."""
    if _client is None:
        yield _NoOp()
        return
    with _client.start_as_current_observation(name=name, as_type=as_type, input=input, **fields) as obs:
        yield obs


def clip(value: Any, limit: int = 4000) -> Any:
    """Keep traced text to a readable size."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"… [{len(value) - limit} more characters]"
    return value
