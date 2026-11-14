"""The wire format of stream events."""

from schemas.chat import DoneEvent, TextDeltaEvent, sse
from support.sse import parse_sse


def test_done_event_frame():
    assert sse(DoneEvent()) == 'data: {"type":"done","finishReason":"stop"}\n\n'


def test_frames_round_trip_through_the_test_parser():
    body = sse(TextDeltaEvent(delta="line one\nline two")) + sse(DoneEvent())

    assert parse_sse(body) == [
        {"type": "text-delta", "delta": "line one\nline two"},
        {"type": "done", "finishReason": "stop"},
    ]
