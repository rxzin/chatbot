"""The tools the agent can call, and how each one runs."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Union
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from core.config import getSettings
from core.database import SessionLocal
from core.logging import logger
from schemas.models import PendingJiraTicket
from schemas.rag import SourceReference, WebSource
from services.base import ToolCall, ToolSpec
from services.graph.prompts import SECURITY_RULES, today_line
from services.graph.state import AgentState
from services.rag import retrieve_context, to_sources
from services.search import SearchUnavailableError, is_web_url
from services.weather import CityNotFoundError, fetch_open_meteo

_MAX_QUERY_CHARS = 500
_MAX_TITLE_CHARS = 200
_MAX_DESCRIPTION_CHARS = 4000


@dataclass
class Citation:
    """A passage or page the model may cite. key identifies it across searches."""

    key: str
    label: str
    text: str
    source: Union[SourceReference, WebSource]


@dataclass
class ToolOutcome:
    """
    What a tool returns. A search returns citations instead of content; the tools node
    numbers them for the whole turn and builds the content from them.
    """

    content: str = ""
    is_error: bool = False
    citations: list[Citation] = field(default_factory=list)


def number_citations(
    outcome: ToolOutcome, registry: dict[str, int]
) -> tuple[str, list[SourceReference], list[WebSource]]:
    """
    Give each citation a number for the whole turn and build the text the model reads.

    registry maps a citation's key to its number and is updated in place, so a passage
    found by two searches keeps its first number and numbers never repeat.
    """
    blocks: list[str] = []
    sources: list[SourceReference] = []
    web_sources: list[WebSource] = []
    for citation in outcome.citations:
        number = registry.setdefault(citation.key, len(registry) + 1)
        blocks.append(f"[{number}] {citation.label}\n{citation.text}")
        numbered = citation.source.model_copy(update={"number": number})
        if isinstance(numbered, WebSource):
            web_sources.append(numbered)
        else:
            sources.append(numbered)
    return "\n\n---\n\n".join(blocks), sources, web_sources


SEARCH_DOCUMENTS = ToolSpec(
    name="search_documents",
    description=(
        "Search the documents the user uploaded to this conversation. Use it for any "
        "question their documents might answer. Returns numbered passages with the file "
        "name and page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, as a standalone search query.",
            }
        },
        "required": ["query"],
    },
)

WEB_SEARCH = ToolSpec(
    name="web_search",
    description=(
        "Search the web. Use it for recent events and for facts that may have changed or "
        "that you aren't sure of. Returns numbered excerpts with their URLs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A standalone search query, as you'd type it into a search engine.",
            }
        },
        "required": ["query"],
    },
)

GET_WEATHER = ToolSpec(
    name="get_weather",
    description="Get the current weather and the daily forecast for a city.",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name, e.g. 'Lisbon'."}
        },
        "required": ["city"],
    },
)

REPORT_BUG = ToolSpec(
    name="report_bug",
    description=(
        "File a bug report about this chat app for an administrator to review. Only use "
        "it when the user is reporting something broken in this app and wants it "
        "reported. Not for errors in their own code, documents or other software."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "A short summary of the problem."},
            "description": {
                "type": "string",
                "description": "What happened, what was expected, and steps to reproduce if given.",
            },
        },
        "required": ["title", "description"],
    },
)


# Tools whose results are text from outside: documents, web pages, a weather service.
UNTRUSTED_SOURCES = {
    "search_documents": "uploaded documents",
    "web_search": "web pages",
    "get_weather": "weather service",
}


def _read_untrusted(state: AgentState) -> bool:
    """True once this turn has read documents or web pages, which could carry injected text."""
    return any(
        call.name in ("search_documents", "web_search")
        for exchange in state["exchanges"]
        for call in exchange.calls
    )


def tools_for(state: AgentState, config: RunnableConfig) -> list[ToolSpec]:
    """
    The tools offered this step.

    search_documents needs indexed documents and web_search a configured provider.
    report_bug is withdrawn once documents or web pages have been read this turn, so
    text inside them can't talk the model into filing tickets.
    """
    tools = []
    if state["has_documents"]:
        tools.append(SEARCH_DOCUMENTS)
    if config["configurable"].get("search_provider") is not None:
        tools.append(WEB_SEARCH)
    tools.append(GET_WEATHER)
    if not _read_untrusted(state):
        tools.append(REPORT_BUG)
    return tools


def instructions_for(state: AgentState, config: RunnableConfig) -> str:
    lines = [
        today_line(),
        "",
        SECURITY_RULES,
        "",
        "You can call tools to help answer. Answer directly when no tool is needed.",
    ]
    if config["configurable"].get("search_provider") is not None:
        lines.append(
            "Use web_search for recent events, or facts you are unsure of or that may "
            "have changed. Base the answer on the results."
        )
    if state["has_documents"]:
        names = ", ".join(state["document_filenames"])
        lines.append(
            f"The user has uploaded these documents: {names}. Use search_documents for "
            "questions they might answer, answer from the passages it returns, and say "
            "so when the passages don't contain the answer."
        )
    lines.append(
        "Search results are numbered like [1]. When you use one, cite its number in "
        "square brackets right after the claim, e.g. 'It opened in 2019 [2].' or "
        "'[1][3]'. Only cite numbers that appear in the results, and don't add a "
        "separate list of sources: the app shows them."
    )
    lines.append(
        "Use get_weather for weather questions. If no city is given, ask which city."
    )
    lines.append(
        "Use report_bug only when the user reports a problem with this app and wants it "
        "reported. Mentioning an error is not enough. Afterwards, tell them an "
        "administrator will review the report."
    )
    return "\n".join(lines)


async def _search_documents(
    args: dict[str, Any], state: AgentState, config: RunnableConfig
) -> ToolOutcome:
    services = config["configurable"]
    query = str(args.get("query") or "").strip()[:_MAX_QUERY_CHARS] or state["user_message"]
    results = await retrieve_context(
        embedding_service=services["embedding_service"],
        reranker_service=services["reranker_service"],
        vector_store=services["vector_store"],
        user_id=state["user_id"],
        message=query,
        top_k=getSettings().RAG_TOP_K,
        document_ids=state["document_ids"],
    )
    if not results:
        return ToolOutcome("No matching passages were found in the uploaded documents.")

    citations = [
        Citation(
            key=f"doc:{source.document_id}:{source.chunk_index}",
            label=result.filename + (f", page {result.page}" if result.page else ""),
            text=result.parent_content,
            source=source,
        )
        for result, source in zip(results, to_sources(results))
    ]
    return ToolOutcome(citations=citations)


async def _get_weather(
    args: dict[str, Any], state: AgentState, config: RunnableConfig
) -> ToolOutcome:
    city = str(args.get("city") or "").strip()
    if not city:
        return ToolOutcome("No city was given. Ask the user which city.", is_error=True)
    try:
        data = await fetch_open_meteo(city)
    except CityNotFoundError:
        return ToolOutcome(
            f"No place called '{city}' was found. Ask the user to check the city name.",
            is_error=True,
        )
    except Exception:
        logger.warning("Weather lookup failed for %r", city, exc_info=True)
        return ToolOutcome(
            "The weather service is unavailable right now. Tell the user to try again "
            "later; the city name is not the problem.",
            is_error=True,
        )
    return ToolOutcome(json.dumps(data))


async def _web_search(
    args: dict[str, Any], state: AgentState, config: RunnableConfig
) -> ToolOutcome:
    provider = config["configurable"].get("search_provider")
    query = " ".join(str(args.get("query") or "").split())[:_MAX_QUERY_CHARS]
    if provider is None:
        return ToolOutcome("Web search is not available.", is_error=True)
    if not query:
        return ToolOutcome("A search query is required.", is_error=True)

    settings = getSettings()
    memory_service = config["configurable"]["memory_service"]
    if not await memory_service.consume_daily_quota(
        state["user_id"], action="web_search", limit=settings.WEB_SEARCH_DAILY_LIMIT_PER_USER
    ):
        return ToolOutcome(
            "The user has used today's web searches. Answer without searching, and say "
            "the answer may be out of date.",
            is_error=True,
        )

    try:
        results = await provider.search(query, settings.WEB_SEARCH_RESULTS)
    except SearchUnavailableError:
        return ToolOutcome(
            "Web search is unavailable right now. Answer without it, and say so.",
            is_error=True,
        )
    if not results:
        return ToolOutcome("The web search found nothing for that query.")

    citations = []
    for result in results:
        if not is_web_url(result.url):
            continue
        dated = f" ({result.published_date[:10]})" if result.published_date else ""
        citations.append(
            Citation(
                key=f"web:{result.url}",
                label=f"{result.title}{dated}\n{result.url}",
                text=result.snippet,
                source=WebSource(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet[:300],
                    published_date=result.published_date,
                ),
            )
        )
    if not citations:
        return ToolOutcome("The web search found nothing for that query.")
    return ToolOutcome(citations=citations)


def _rate_limit_message(remaining_seconds: int | None) -> str:
    message = "The user filed a bug report recently and must wait before filing another."
    if remaining_seconds:
        minutes = max(1, (remaining_seconds + 59) // 60)
        message += f" They can try again in about {minutes} minute(s)."
    return message


async def _report_bug(
    args: dict[str, Any], state: AgentState, config: RunnableConfig
) -> ToolOutcome:
    title = str(args.get("title") or "").strip()[:_MAX_TITLE_CHARS]
    description = str(args.get("description") or "").strip()[:_MAX_DESCRIPTION_CHARS]
    if not title or not description:
        return ToolOutcome("A title and a description are both required.", is_error=True)

    memory_service = config["configurable"]["memory_service"]
    user_id = state["user_id"]
    acquired = await memory_service.try_acquire_rate_limit(
        user_id,
        action="bug_report",
        limit_seconds=getSettings().BUG_REPORT_RATE_LIMIT_SECONDS,
    )
    if not acquired:
        ttl = await memory_service.get_rate_limit_ttl(user_id, action="bug_report")
        return ToolOutcome(_rate_limit_message(ttl), is_error=True)

    try:
        async with SessionLocal() as db:
            db.add(
                PendingJiraTicket(
                    user_id=UUID(str(user_id)),
                    conversation_id=UUID(str(state["conversation_id"])),
                    title=title,
                    description=description,
                    status="pending",
                )
            )
            await db.commit()
    except Exception:
        # A failed attempt shouldn't use up the user's report allowance.
        await memory_service.release_rate_limit(user_id, action="bug_report")
        logger.exception("Failed to save bug report")
        return ToolOutcome("The bug report could not be saved.", is_error=True)

    return ToolOutcome(
        f"Bug report '{title}' was saved for an administrator to review. The user gets "
        "an email when it is approved."
    )


_EXECUTORS: dict[
    str, Callable[[dict[str, Any], AgentState, RunnableConfig], Awaitable[ToolOutcome]]
] = {
    SEARCH_DOCUMENTS.name: _search_documents,
    GET_WEATHER.name: _get_weather,
    REPORT_BUG.name: _report_bug,
    WEB_SEARCH.name: _web_search,
}


async def run_tool(call: ToolCall, state: AgentState, config: RunnableConfig) -> ToolOutcome:
    """Run one call. Errors become results the model can read, never exceptions."""
    if call.name not in {t.name for t in tools_for(state, config)}:
        return ToolOutcome(f"There is no tool called '{call.name}'.", is_error=True)
    timeout = getSettings().TOOL_TIMEOUT_SECONDS
    try:
        return await asyncio.wait_for(_EXECUTORS[call.name](call.arguments, state, config), timeout)
    except asyncio.TimeoutError:
        logger.warning("Tool %s timed out after %ss", call.name, timeout)
        return ToolOutcome(
            f"The {call.name} tool took too long to respond. Answer without it, and tell "
            "the user that part couldn't be checked right now.",
            is_error=True,
        )
    except Exception:
        logger.exception("Tool %s failed", call.name)
        return ToolOutcome(f"The {call.name} tool failed.", is_error=True)
