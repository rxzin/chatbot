"""The agent loop: choosing tools, surviving their failures, and its limits."""

import asyncio

import httpx
import pytest
from sqlalchemy import func, select

from schemas.models import PendingJiraTicket
from services.base import ToolCall
from services.fallback import FallbackLLM
from support.factories import chat
from support.fakes import ScriptedLLM

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
PARIS = {
    "results": [
        {"latitude": 48.85, "longitude": 2.35, "name": "Paris", "country": "France"}
    ]
}


def weather(city="Paris", call_id="c1") -> list[ToolCall]:
    return [ToolCall(call_id, "get_weather", {"city": city})]


def bug_report(call_id="c1") -> list[ToolCall]:
    return [
        ToolCall(
            call_id,
            "report_bug",
            {"title": "Upload button", "description": "Nothing happens on click."},
        )
    ]


def types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def result_for(events: list[dict], call_id: str) -> dict:
    (event,) = [
        e for e in events if e["type"] == "tool-result" and e["toolCallId"] == call_id
    ]
    return event


@pytest.fixture
def weather_service(respx_mock):
    """Open-Meteo answering normally. Tests override a route to make it fail."""
    respx_mock.get(GEOCODE).respond(json=PARIS)
    respx_mock.get(FORECAST).respond(json={"current": {"temperature_2m": 21.5}})
    return respx_mock


async def test_model_calls_a_tool_and_answers_from_its_result(
    client, user, conversation, scripted_llm, weather_service, stored_messages
):
    _, headers = user
    model = scripted_llm([["Let me check.", weather()], ["Sunny."]])

    events = await chat(client, headers, conversation.id, "weather in Paris?")

    assert types(events) == [
        "text-delta",  # "Let me check."
        "text-delta",  # the blank line that separates the lead-in from the answer
        "tool-start",
        "tool-result",
        "text-delta",  # "Sunny."
        "done",
    ]
    start = events[2]
    assert (start["toolName"], start["toolCallId"]) == ("get_weather", "c1")
    assert start["input"] == {"city": "Paris"}
    assert events[3]["isError"] is False

    second_call = model.calls[1]
    (exchange,) = second_call["exchanges"]
    assert exchange.text == "Let me check."
    assert "Paris" in exchange.results[0].content
    assert "21.5" in exchange.results[0].content
    _, model_row = await stored_messages(conversation.id)
    assert model_row.content == "Let me check.\n\nSunny."


async def test_tool_result_reaches_the_model_marked_as_untrusted(
    client, user, conversation, scripted_llm, weather_service
):
    """Text from outside must arrive as data, so it cannot give the model orders."""
    from services.graph.prompts import wrap_untrusted

    _, headers = user
    model = scripted_llm([[weather()], ["Sunny."]])

    await chat(client, headers, conversation.id, "weather in Paris?")

    content = model.calls[1]["exchanges"][0].results[0].content
    marker = wrap_untrusted("weather service", "X").split("X")[0]
    assert content.startswith(marker)


async def test_failing_tool_becomes_an_error_result_and_the_reply_continues(
    client, user, conversation, scripted_llm, weather_service
):
    _, headers = user
    weather_service.get(GEOCODE).respond(500)
    model = scripted_llm([[weather()], ["I couldn't check the weather."]])

    events = await chat(client, headers, conversation.id, "weather in Paris?")

    assert result_for(events, "c1")["isError"] is True
    assert types(events)[-1] == "done"
    assert "unavailable" in model.calls[1]["exchanges"][0].results[0].content


async def test_unknown_city_is_reported_to_the_model(
    client, user, conversation, scripted_llm, weather_service
):
    _, headers = user
    weather_service.get(GEOCODE).respond(json={"results": []})
    model = scripted_llm([[weather("Atlantis")], ["Which city?"]])

    events = await chat(client, headers, conversation.id, "weather in Atlantis?")

    assert result_for(events, "c1")["isError"] is True
    assert "Atlantis" in model.calls[1]["exchanges"][0].results[0].content


async def test_unknown_tool_name_is_an_error_result(
    client, user, conversation, scripted_llm
):
    _, headers = user
    scripted_llm([[[ToolCall("c1", "delete_everything", {})]], ["I can't do that."]])

    events = await chat(client, headers, conversation.id, "do it")

    assert result_for(events, "c1")["isError"] is True
    assert types(events)[-1] == "done"


async def test_slow_tool_times_out(
    client, user, conversation, scripted_llm, weather_service, settings_override
):
    settings_override(TOOL_TIMEOUT_SECONDS=0.05)
    _, headers = user

    async def slow(request):
        await asyncio.sleep(0.5)
        return httpx.Response(200, json=PARIS)

    weather_service.get(GEOCODE).mock(side_effect=slow)
    model = scripted_llm([[weather()], ["I couldn't check."]])

    events = await chat(client, headers, conversation.id, "weather in Paris?")

    assert result_for(events, "c1")["isError"] is True
    assert "took too long" in model.calls[1]["exchanges"][0].results[0].content
    assert types(events)[-1] == "done"


async def test_tools_are_withdrawn_after_the_round_limit(
    client, user, conversation, scripted_llm, weather_service, settings_override
):
    settings_override(AGENT_MAX_TOOL_ROUNDS=1)
    _, headers = user
    model = scripted_llm([[weather()], ["Sunny."]])

    await chat(client, headers, conversation.id, "weather in Paris?")

    assert model.calls[0]["allow_tools"] is True
    assert model.calls[1]["allow_tools"] is False


async def test_calls_beyond_the_per_round_limit_are_skipped(
    client, user, conversation, scripted_llm, weather_service, settings_override
):
    settings_override(AGENT_MAX_CALLS_PER_ROUND=1)
    _, headers = user
    two_calls = weather("Paris", "c1") + weather("Lyon", "c2")
    model = scripted_llm([[two_calls], ["Sunny."]])

    events = await chat(client, headers, conversation.id, "weather?")

    assert result_for(events, "c1")["isError"] is False
    assert result_for(events, "c2")["isError"] is True
    results = model.calls[1]["exchanges"][0].results
    assert [r.call_id for r in results] == ["c1", "c2"]
    assert "at most 1 tool calls" in results[1].content


async def test_only_available_tools_are_offered(
    client, user, conversation, scripted_llm
):
    """No documents and no search provider: only the two always-on tools."""
    _, headers = user
    model = scripted_llm([["hello"]])

    await chat(client, headers, conversation.id, "hi")

    assert {tool.name for tool in model.calls[0]["tools"]} == {
        "get_weather",
        "report_bug",
    }


async def test_bug_report_is_saved_once_per_window(
    client, user, conversation, scripted_llm, db
):
    account, headers = user
    model = scripted_llm(
        [[bug_report("c1")], ["Reported."], [bug_report("c2")], ["Please wait."]]
    )

    first = await chat(client, headers, conversation.id, "the upload button is broken")
    second = await chat(client, headers, conversation.id, "report it again")

    assert result_for(first, "c1")["isError"] is False
    assert result_for(second, "c2")["isError"] is True
    assert "must wait" in model.calls[3]["exchanges"][0].results[0].content
    tickets = (await db.execute(select(PendingJiraTicket))).scalars().all()
    assert len(tickets) == 1
    assert tickets[0].user_id == account.id
    assert tickets[0].conversation_id == conversation.id
    assert (tickets[0].title, tickets[0].status) == ("Upload button", "pending")


async def test_incomplete_bug_report_is_not_saved(
    client, user, conversation, scripted_llm, db
):
    _, headers = user
    scripted_llm([[[ToolCall("c1", "report_bug", {"title": "No details"})]], ["ok"]])

    events = await chat(client, headers, conversation.id, "broken")

    assert result_for(events, "c1")["isError"] is True
    assert await db.scalar(select(func.count()).select_from(PendingJiraTicket)) == 0


async def test_fallback_model_answers_when_the_primary_fails(
    client, user, conversation, app_state_override, stored_messages
):
    _, headers = user
    app_state_override(
        llm_service=FallbackLLM(
            primary=ScriptedLLM([RuntimeError("primary down")]),
            fallback=ScriptedLLM([["from fallback"]]),
            should_fallback=lambda error: True,
        )
    )

    events = await chat(client, headers, conversation.id, "hi")

    assert types(events) == ["text-delta", "done"]
    _, model_row = await stored_messages(conversation.id)
    assert model_row.content == "from fallback"
