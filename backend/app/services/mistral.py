import json
import uuid
from typing import Any, AsyncGenerator, Optional, Sequence

import httpx2
from mistralai.client import Mistral
from mistralai.client.errors import NoResponseError, SDKError
from mistralai.client.models import TextChunk

from core.config import getSettings
from core.logging import logger
from schemas.chat import MessageParam
from services import tracing, usage
from services.base import AIPlatform, ToolCall, ToolExchange, ToolSpec, TurnChunk

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


def _record_usage(generation: Any, model: str, tokens: Any) -> None:
    """Save the call's token counts for the usage dashboard and the trace."""
    if tokens is None:
        return
    prompt_tokens = getattr(tokens, "prompt_tokens", 0) or 0
    completion_tokens = getattr(tokens, "completion_tokens", 0) or 0
    usage.record(model, prompt_tokens, completion_tokens)
    generation.update(usage_details={"input": prompt_tokens, "output": completion_tokens})


def _tool_param(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _exchange_messages(exchanges: Sequence[ToolExchange]) -> list[dict[str, Any]]:
    """This turn's earlier rounds: the assistant's tool calls, then each result."""
    messages: list[dict[str, Any]] = []
    for exchange in exchanges:
        messages.append(
            {
                "role": "assistant",
                "content": exchange.text,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in exchange.calls
                ],
            }
        )
        for result in exchange.results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.call_id,
                    "name": result.name,
                    "content": result.content,
                }
            )
    return messages


def _merge_tool_call(pending: dict[int, dict[str, Any]], call: Any) -> None:
    index = call.index if isinstance(call.index, int) else len(pending)
    entry = pending.setdefault(index, {"id": None, "name": "", "arguments": ""})
    if call.id and call.id != "null":
        entry["id"] = call.id
    if call.function.name:
        entry["name"] = call.function.name
    arguments = call.function.arguments
    if isinstance(arguments, dict):
        entry["arguments"] = arguments
    elif arguments:
        entry["arguments"] = (
            entry["arguments"] if isinstance(entry["arguments"], str) else ""
        ) + arguments


def _to_tool_call(entry: dict[str, Any]) -> ToolCall:
    arguments = entry["arguments"]
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            logger.warning("Tool call %s had unparseable arguments", entry["name"])
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(
        id=entry["id"] or uuid.uuid4().hex[:9],
        name=entry["name"],
        arguments=arguments,
    )


def _finish_notice(finish_reason: Optional[str]) -> Optional[str]:
    """
    Decide what the user sees once a stream has ended.

    finish_reason is "stop" (normal), "length" (hit MODEL_OUTPUT_TOKEN_LIMIT, so the
    reply was cut off), "error", or a value this SDK version does not recognize.

    Return text to append to the reply, return None to end silently, or raise to make
    run_graph_stream send STREAM_GENERATION_FAILED. Whatever is returned here is also
    saved to Redis and Postgres as part of the reply; raising saves nothing.
    """
    if finish_reason in (None, "stop", "tool_calls"):
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

    async def stream_turn(
        self,
        *,
        prompt: str,
        history: Sequence[MessageParam],
        context_summary: Optional[str],
        instructions: str,
        exchanges: Sequence[ToolExchange],
        tools: Sequence[ToolSpec],
        allow_tools: bool,
    ) -> AsyncGenerator[TurnChunk, None]:
        messages: list[dict[str, Any]] = _to_api_messages(
            self._build_system_instruction(context_summary, instructions),
            history,
            prompt,
        )
        messages.extend(_exchange_messages(exchanges))

        tool_args: dict[str, Any] = {}
        if tools:
            tool_args = {
                "tools": [_tool_param(t) for t in tools],
                "tool_choice": "auto" if allow_tools else "none",
            }
        with tracing.observe(
            usage.current_purpose(),
            as_type="generation",
            input=messages,
            model=self.model,
            metadata={"tools": [t.name for t in tools], "tools_allowed": allow_tools},
        ) as generation:
            stream = await self._client.chat.stream_async(
                model=self.model,
                messages=messages,
                max_tokens=getSettings().MODEL_OUTPUT_TOKEN_LIMIT,
                **tool_args,
            )

            finish_reason = None
            tokens = None
            text_out = ""
            # Tool calls may arrive split across chunks; they're joined by index.
            pending: dict[int, dict[str, Any]] = {}
            async with stream as events:
                async for event in events:
                    # Usage can come on a final chunk that has no choices.
                    tokens = getattr(event.data, "usage", None) or tokens
                    if not event.data.choices:
                        continue
                    choice = event.data.choices[0]
                    text = _extract_text(choice.delta.content)
                    if text:
                        text_out += text
                        yield text
                    for call in choice.delta.tool_calls or []:
                        _merge_tool_call(pending, call)
                    finish_reason = choice.finish_reason or finish_reason

            calls = [_to_tool_call(p) for _, p in sorted(pending.items())]
            _record_usage(generation, self.model, tokens)
            generation.update(
                output={"text": text_out, "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in calls]},
                metadata={"finish_reason": finish_reason},
            )
            if calls and allow_tools:
                yield calls
                return
            notice = _finish_notice(finish_reason)
            if notice:
                yield notice

    async def _complete_text(
        self, system_instruction: str, prompt: str, max_output_tokens: int
    ) -> str:
        messages = _to_api_messages(system_instruction, [], prompt)
        with tracing.observe(
            usage.current_purpose(), as_type="generation", input=messages, model=self.model
        ) as generation:
            response = await self._client.chat.complete_async(
                model=self.model,
                messages=messages,
                max_tokens=max_output_tokens,
            )
            text = _extract_text(response.choices[0].message.content) if response.choices else ""
            _record_usage(generation, self.model, response.usage)
            generation.update(output=text)
            return text
