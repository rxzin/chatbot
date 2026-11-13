"""A model whose every reply is written by the test."""

import asyncio
from typing import AsyncGenerator, Optional, Sequence

from schemas.chat import MessageParam
from services.base import AIPlatform, ToolExchange, ToolSpec, TurnChunk


class ScriptedLLM(AIPlatform):
    """
    Plays back `turns`, one entry per model call.

    An entry that is a list is streamed chunk by chunk: strings are text, a list of
    ToolCall asks for tools. An entry that is an Exception is raised instead. A call
    with no entries left fails the test, so an unexpected model call cannot go unseen.

    `calls` records the arguments of each stream_turn call. Set `gate` to an
    asyncio.Event to hold a reply open after its first chunk until the event is set.
    """

    def __init__(
        self,
        turns: list[list[TurnChunk] | Exception],
        completion: str | Exception = "Test Title",
    ):
        super().__init__()
        self._turns = list(turns)
        self._completion = completion
        self.calls: list[dict] = []
        self.completions: list[dict] = []
        self.gate: asyncio.Event | None = None

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
        self.calls.append(
            {
                "prompt": prompt,
                "history": list(history),
                "context_summary": context_summary,
                "instructions": instructions,
                "exchanges": list(exchanges),
                "tools": list(tools),
                "allow_tools": allow_tools,
            }
        )
        if not self._turns:
            raise AssertionError("unexpected model call")
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        for index, chunk in enumerate(turn):
            yield chunk
            if index == 0 and self.gate is not None:
                await self.gate.wait()

    async def _complete_text(
        self, system_instruction: str, prompt: str, max_output_tokens: int
    ) -> str:
        self.completions.append(
            {"system_instruction": system_instruction, "prompt": prompt}
        )
        if isinstance(self._completion, Exception):
            raise self._completion
        return self._completion
