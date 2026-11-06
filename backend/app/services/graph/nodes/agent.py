import asyncio

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

from core.config import getSettings
from services.base import ToolExchange, ToolResult
from services.context_budget import apply_token_budget
from services.graph.state import AgentState
from services.graph.tools import instructions_for, run_tool, tools_for


async def agent(state: AgentState, config: RunnableConfig) -> dict:
    """One model step: stream text, and either finish or ask for tool calls."""
    writer = get_stream_writer()
    llm = config["configurable"]["llm"]
    updates: dict = {}

    history = state["prepared_history"]
    summary = state["prepared_summary"]
    if history is None:
        prepared = await apply_token_budget(
            llm=llm,
            history=state["history"],
            prompt=state["user_message"],
            summary=state["context_summary"],
        )
        history, summary = prepared.messages, prepared.summary
        updates.update(prepared_history=history, prepared_summary=summary)

    exchanges = state["exchanges"]
    allow_tools = len(exchanges) < getSettings().AGENT_MAX_TOOL_ROUNDS

    text = ""
    calls = []
    async for chunk in llm.stream_turn(
        prompt=state["user_message"],
        history=history,
        context_summary=summary,
        instructions=instructions_for(state),
        exchanges=exchanges,
        tools=tools_for(state),
        allow_tools=allow_tools,
    ):
        if isinstance(chunk, list):
            calls = chunk
        else:
            text += chunk
            writer({"event": "token", "content": chunk})

    if calls:
        # Keep a lead-in like "Let me check." apart from the answer that follows.
        if text and not text.endswith("\n"):
            writer({"event": "token", "content": "\n\n"})
        return {**updates, "pending": ToolExchange(text=text, calls=calls)}

    writer(
        {
            "event": "done",
            "prepared_messages": history,
            "context_summary": summary,
        }
    )
    return {**updates, "pending": None, "final_response": text}


async def tools(state: AgentState, config: RunnableConfig) -> dict:
    """Run the pending calls together and record the round."""
    writer = get_stream_writer()
    exchange = state["pending"]
    limit = getSettings().AGENT_MAX_CALLS_PER_ROUND

    async def run(index: int, call) -> ToolResult:
        writer({"event": "tool-start", "id": call.id, "name": call.name, "input": call.arguments})
        if index >= limit:
            outcome_content, is_error, sources = (
                f"Skipped: at most {limit} tool calls per step.", True, []
            )
        else:
            outcome = await run_tool(call, state, config)
            outcome_content, is_error, sources = outcome.content, outcome.is_error, outcome.sources
        if sources:
            writer({"event": "sources", "sources": [s.model_dump(by_alias=True) for s in sources]})
        writer({"event": "tool-result", "id": call.id, "name": call.name, "is_error": is_error})
        return ToolResult(call_id=call.id, name=call.name, content=outcome_content)

    exchange.results = list(
        await asyncio.gather(*(run(i, call) for i, call in enumerate(exchange.calls)))
    )
    return {"exchanges": [*state["exchanges"], exchange], "pending": None}
