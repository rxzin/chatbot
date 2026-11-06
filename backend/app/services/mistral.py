from typing import Any, AsyncGenerator, Optional, Sequence

import httpx2
from mistralai.client import Mistral
from mistralai.client.errors import NoResponseError, SDKError
from mistralai.client.models import TextChunk
from pydantic import BaseModel

from core.config import getSettings
from core.logging import logger
from schemas.chat import MessageParam
from services.base import AIPlatform

# Storage and the frontend use "model" for the assistant; Mistral expects "assistant".
_API_ROLES = {"user": "user", "model": "assistant"}

# Applies per read while streaming, so it bounds a stalled stream, not a long reply.
_TIMEOUT_MS = 120_000


def is_transient_error(exc: Exception) -> bool:
    """True for rate limits, server errors and network failures another model may avoid."""
    if isinstance(exc, SDKError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, (NoResponseError, httpx2.TransportError))


def _to_api_messages(
    system_instruction: str,
    history: Sequence[MessageParam],
    prompt: str,
) -> list[dict[str, str]]:
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    for message in history:
        messages.append(
            {"role": _API_ROLES[message.role], "content": message.content}
        )
    messages.append({"role": "user", "content": prompt})
    return messages


def _extract_text(content: Any) -> str:
    """
    Return the user-visible text of a message or stream delta.

    Content is either a plain string or a list of typed chunks. Reasoning models send
    ThinkChunks in that list, which must not reach the user.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.text for c in content if isinstance(c, TextChunk))
    return ""


def _finish_notice(finish_reason: Optional[str]) -> Optional[str]:
    """
    Decide what the user sees once a stream has ended.

    finish_reason is "stop" (normal), "length" (hit MODEL_OUTPUT_TOKEN_LIMIT, so the
    reply was cut off), "error", or a value this SDK version does not recognize.

    Return text to append to the reply, return None to end silently, or raise to make
    run_graph_stream send STREAM_GENERATION_FAILED. Whatever is returned here is also
    saved to Redis and Postgres as part of the reply; raising saves nothing.
    """
    if finish_reason in (None, "stop"):
        return None
    if finish_reason == "length":
        # Kept in the saved reply too, so a follow-up "continue" has context.
        return (
            "\n\n*[Reply cut off at the length limit. "
            'Say "continue" to get the rest.]*'
        )
    if finish_reason == "error":
        # A reply broken by a model error shouldn't be remembered as an answer.
        raise RuntimeError("Mistral ended the stream with finish_reason=error")
    logger.warning("Unexpected Mistral finish_reason: %s", finish_reason)
    return None


class MistralProvider(AIPlatform):
    def __init__(self, api_key: str, model: str, system_prompt: Optional[str] = None):
        super().__init__(system_prompt)
        self.model = model
        self._client = Mistral(api_key=api_key, timeout_ms=_TIMEOUT_MS)

    async def chat(
        self,
        prompt: str,
        history: Optional[Sequence[MessageParam]] = None,
        context_summary: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Yields chunks of text asynchronously for SSE streaming."""
        stream = await self._client.chat.stream_async(
            model=self.model,
            messages=_to_api_messages(
                self._build_system_instruction(context_summary),
                history or [],
                prompt,
            ),
            max_tokens=getSettings().MODEL_OUTPUT_TOKEN_LIMIT,
        )

        finish_reason = None
        # The context manager releases the connection if the client disconnects
        # and this generator is closed part-way through.
        async with stream as events:
            async for event in events:
                if not event.data.choices:
                    continue
                choice = event.data.choices[0]
                text = _extract_text(choice.delta.content)
                if text:
                    yield text
                finish_reason = choice.finish_reason or finish_reason

        notice = _finish_notice(finish_reason)
        if notice:
            yield notice

    async def classify_json(
        self, system_prompt: str, user_prompt: str, schema: type[BaseModel]
    ) -> BaseModel:
        response = await self._client.chat.parse_async(
            response_format=schema,
            model=self.model,
            messages=_to_api_messages(system_prompt, [], user_prompt),
            temperature=0,
        )
        parsed = response.choices[0].message.parsed if response.choices else None
        if parsed is None:
            raise ValueError(f"Mistral returned no {schema.__name__} output")
        return parsed

    async def _complete_text(
        self, system_instruction: str, prompt: str, max_output_tokens: int
    ) -> str:
        response = await self._client.chat.complete_async(
            model=self.model,
            messages=_to_api_messages(system_instruction, [], prompt),
            max_tokens=max_output_tokens,
        )
        if not response.choices:
            return ""
        return _extract_text(response.choices[0].message.content)
