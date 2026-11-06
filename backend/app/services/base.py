from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional, Sequence, Union

import tiktoken
from fastapi.concurrency import run_in_threadpool

from schemas.chat import MessageParam

# An approximation: no provider's tokenizer is exactly cl100k_base. The budget in
# context_budget.py keeps a safety margin (SUMMARIZE_THRESHOLD) to absorb the error.
_ENCODING = tiktoken.get_encoding("cl100k_base")

# Mirrored by context_budget.PER_MESSAGE_TOKENS.
_PER_MESSAGE_TOKENS = 4

_SUMMARY_INSTRUCTION = (
    "Merge the conversation history into a concise rolling summary. "
    "Preserve key facts, names, decisions, and user preferences. "
    "Output only the summary text."
)
_SUMMARY_MAX_OUTPUT_TOKENS = 4096


@dataclass
class ToolSpec:
    """A tool the model may call. parameters is a JSON Schema object."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """One call the model asked for. id comes from the provider and links the result."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    content: str


@dataclass
class ToolExchange:
    """One round of a turn: any text the model wrote, its tool calls, and their results."""

    text: str
    calls: list[ToolCall]
    results: list[ToolResult] = field(default_factory=list)


# stream_turn yields text fragments, then at most one list of tool calls at the end.
TurnChunk = Union[str, list[ToolCall]]


def _count_texts_tokens_sync(texts: list[str]) -> list[int]:
    return [len(_ENCODING.encode(text)) if text else 0 for text in texts]


class AIPlatform(ABC):
    """
    The contract the rest of the app depends on.

    A provider implements stream_turn and _complete_text. Token counting,
    system-instruction assembly and summarization are provider-independent.
    """

    def __init__(self, system_prompt: Optional[str] = None):
        self.system_prompt = system_prompt or ""

    @abstractmethod
    def stream_turn(
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
        """
        One model step of an agent turn.

        Sends the history, the user's prompt and this turn's earlier tool exchanges.
        Yields text as it streams, then a list of ToolCall if the model wants tools.
        With allow_tools False the tools are still described but can't be called, so
        the model has to answer.
        """

    @abstractmethod
    async def _complete_text(
        self, system_instruction: str, prompt: str, max_output_tokens: int
    ) -> str:
        """Return a complete, non-streamed reply. May be empty."""

    def _build_system_instruction(
        self, context_summary: Optional[str] = None, instructions: str = ""
    ) -> str:
        parts = [self.system_prompt, instructions]
        if context_summary:
            parts.append(f"Conversation context so far:\n{context_summary}")
        return "\n\n".join(p for p in parts if p)

    async def count_texts_tokens(self, texts: list[str]) -> list[int]:
        """Token counts for many texts in a single threadpool round-trip."""
        if not texts:
            return []
        return await run_in_threadpool(_count_texts_tokens_sync, texts)

    async def count_messages_tokens(
        self,
        history: Sequence[MessageParam],
        prompt: str = "",
        context_summary: Optional[str] = None,
    ) -> int:
        system_instruction = self._build_system_instruction(context_summary)
        texts = [system_instruction, *(m.content for m in history), prompt]
        counts = await self.count_texts_tokens(texts)
        num_messages = len(history) + (1 if prompt else 0)
        return sum(counts) + num_messages * _PER_MESSAGE_TOKENS

    async def summarize_messages(
        self,
        evicted_messages: list[MessageParam],
        existing_summary: Optional[str] = None,
    ) -> str:
        lines = []
        if existing_summary:
            lines.append(f"Previous summary:\n{existing_summary}\n")
        lines.append("New messages to incorporate into the summary:\n")
        for msg in evicted_messages:
            lines.append(f"{msg.role}: {msg.content}\n")

        summary = await self._complete_text(
            _SUMMARY_INSTRUCTION, "".join(lines), _SUMMARY_MAX_OUTPUT_TOKENS
        )
        return summary or existing_summary or ""
