"""Reading a Server-Sent Events body the way the frontend does."""

import json


def parse_sse(body: str) -> list[dict]:
    """The events in a response body, in order. Each frame is 'data: <json>' + blank line."""
    events = []
    for frame in body.split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    return events
