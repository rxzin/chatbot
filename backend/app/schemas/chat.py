from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from schemas.rag import SourceReference

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Payload received from the client."""

    message: str = Field(
        ..., description="The raw input message from the user.", min_length=1
    )
    role: str = "user"
    conversation_id: UUID = Field(
        ...,
        alias="conversationId",
        description="Database conversation thread identifier.",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "message": "Tell me a short story about an AI agent.",
                "conversationId": "550e8400-e29b-41d4-a716-446655440000",
            }
        },
    }


class MessageParam(BaseModel):
    """Represents an individual chat turn stored in memory."""

    role: Literal["user", "model"] = Field(
        ...,
        description="The author of this message turn. 'model' is the assistant; providers map it to their own role name.",
    )
    content: str = Field(..., description="The textual content of the message.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token_count: Optional[int] = Field(
        None,
        alias="tokenCount",
        description="Pre-calculated token count for fast sliding-window budget checks.",
    )

    model_config = {"populate_by_name": True}


# --- Stream events ---------------------------------------------------------------
# Each SSE "data:" line is one ChatStreamEvent. Features that add tools or suggestions
# add their own event types to the union.


class TextDeltaEvent(BaseModel):
    """A fragment of the reply's text, in order."""

    type: Literal["text-delta"] = "text-delta"
    delta: str


class SourcesEvent(BaseModel):
    """Documents the reply was based on. Sent once, after the text."""

    type: Literal["sources"] = "sources"
    sources: list[SourceReference]


class DoneEvent(BaseModel):
    """The reply finished normally. A stream without it was interrupted."""

    type: Literal["done"] = "done"
    finish_reason: Literal["stop"] = Field(default="stop", alias="finishReason")

    model_config = {"populate_by_name": True}


class StreamError(BaseModel):
    code: str
    message: str


class ErrorEvent(BaseModel):
    """The reply failed. Ends the stream; nothing is saved."""

    type: Literal["error"] = "error"
    error: StreamError


ChatStreamEvent = Annotated[
    Union[TextDeltaEvent, SourcesEvent, DoneEvent, ErrorEvent],
    Field(discriminator="type"),
]


def sse(event: BaseModel) -> str:
    """Format one event as an SSE frame."""
    return f"data: {event.model_dump_json(by_alias=True)}\n\n"


# --- Stored message parts ----------------------------------------------------------
# A message's content in display order. "content" keeps the plain text for the model's
# memory; parts add what the UI needs, such as sources, so it survives a reload.


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class SourcesPart(BaseModel):
    type: Literal["sources"] = "sources"
    sources: list[SourceReference]


MessagePart = Annotated[Union[TextPart, SourcesPart], Field(discriminator="type")]
