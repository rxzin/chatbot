from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


DocumentStatus = Literal["processing", "indexed", "failed"]


class DocumentResponse(BaseModel):
    id: UUID
    conversation_id: UUID = Field(alias="conversationId")
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    chunk_count: int = Field(alias="chunkCount")
    error_message: Optional[str] = Field(default=None, alias="errorMessage")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class SourceReference(BaseModel):
    document_id: UUID = Field(alias="documentId")
    filename: str
    page: Optional[int] = None
    chunk_index: int = Field(alias="chunkIndex")
    snippet: str
    score: Optional[float] = None

    model_config = {"populate_by_name": True}


class WebSource(BaseModel):
    """A web page the reply used. url is always http or https."""

    url: str
    title: str
    snippet: str
    published_date: Optional[str] = Field(default=None, alias="publishedDate")

    model_config = {"populate_by_name": True}
