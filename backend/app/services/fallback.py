from typing import AsyncGenerator, Awaitable, Callable, TypeVar


from core.logging import logger
from services.base import AIPlatform, TurnChunk

T = TypeVar("T")


class FallbackLLM(AIPlatform):
    """Try the primary model, and use the fallback when should_fallback(error) is true."""

    def __init__(
        self,
        primary: AIPlatform,
        fallback: AIPlatform,
        should_fallback: Callable[[Exception], bool],
    ):
        super().__init__(primary.system_prompt)
        self._primary = primary
        self._fallback = fallback
        self._should_fallback = should_fallback

    async def _with_fallback(self, call: Callable[[AIPlatform], Awaitable[T]]) -> T:
        try:
            return await call(self._primary)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            logger.warning("Primary LLM failed, using fallback: %s", type(exc).__name__)
        return await call(self._fallback)

    async def stream_turn(self, **kwargs) -> AsyncGenerator[TurnChunk, None]:
        # Same rule as chat: switch models only before anything has been yielded.
        has_output = False
        try:
            async for chunk in self._primary.stream_turn(**kwargs):
                has_output = True
                yield chunk
            return
        except Exception as exc:
            if has_output or not self._should_fallback(exc):
                raise
            logger.warning("Primary LLM failed, using fallback: %s", type(exc).__name__)

        async for chunk in self._fallback.stream_turn(**kwargs):
            yield chunk

    async def _complete_text(
        self, system_instruction: str, prompt: str, max_output_tokens: int
    ) -> str:
        return await self._with_fallback(
            lambda llm: llm._complete_text(system_instruction, prompt, max_output_tokens)
        )
