import asyncio
import re

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from core.config import getSettings
from core.logging import logger
from services.graph.state import AgentState

_INSTRUCTION = (
    "Suggest follow-up questions the user might ask next, based on their question and "
    "the answer. Write exactly three, one per line, each under 80 characters, in the "
    "user's language. Write them as the user would type them. No numbering, quotes or "
    "other text."
)
_MAX_ANSWER_CHARS = 3000
_MAX_SUGGESTION_CHARS = 120
_LEADING_MARKS = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def parse_suggestions(text: str, limit: int = 3) -> list[str]:
    """Clean the model's lines into at most limit distinct, short questions."""
    suggestions: list[str] = []
    for line in text.splitlines():
        cleaned = _LEADING_MARKS.sub("", line).strip().strip("\"'“”").strip()
        if not 3 <= len(cleaned) <= _MAX_SUGGESTION_CHARS:
            continue
        if cleaned.lower() in (s.lower() for s in suggestions):
            continue
        suggestions.append(cleaned)
        if len(suggestions) == limit:
            break
    return suggestions


async def suggest(state: AgentState, config: RunnableConfig) -> dict:
    """
    Offer follow-up questions after the answer. Optional by design: a slow or failed
    call only means no suggestions, and the answer is already sent.
    """
    settings = getSettings()
    answer = (state.get("final_response") or "").strip()
    if not settings.SUGGESTIONS_ENABLED or not answer:
        return {}

    llm = config["configurable"]["llm"]
    prompt = (
        f"User's question:\n{state['user_message']}\n\n"
        f"Answer:\n{answer[:_MAX_ANSWER_CHARS]}"
    )
    try:
        text = await asyncio.wait_for(
            llm.complete_text(_INSTRUCTION, prompt, 200),
            timeout=settings.SUGGESTIONS_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("Suggested questions skipped", exc_info=True)
        return {}

    suggestions = parse_suggestions(text)
    if suggestions:
        get_stream_writer()({"event": "suggestions", "suggestions": suggestions})
    return {}
