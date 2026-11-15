from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import os
import tempfile
import aiofiles

import fitz
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import getSettings
from core.database import SessionLocal
from core.errors import BadRequest, NotFoundError, ValidationError
from core.logging import logger
from schemas.models import Document
from services.conversation import get_user_conversation
from services.embeddings import EmbeddingService
from services.tokenizer import ENCODING
from services.vector_store import VectorChunk, VectorStoreService


ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


@dataclass
class ExtractedPage:
    text: str
    page_number: Optional[int]


@dataclass
class ExtractedChunk:
    text: str
    parent_id: str
    parent_text: str
    page_number: Optional[int]


def _file_extension(filename: str) -> str:
    return f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""


def validate_upload(file: UploadFile, size_bytes: int) -> None:
    settings = getSettings()
    extension = _file_extension(file.filename or "")
    content_type = file.content_type or ""

    if size_bytes <= 0:
        raise ValidationError("Uploaded file is empty")
    if size_bytes > settings.MAX_UPLOAD_BYTES:
        raise ValidationError("Uploaded file is too large")
    if (
        content_type not in ALLOWED_CONTENT_TYPES
        and extension not in ALLOWED_EXTENSIONS
    ):
        raise ValidationError("Only PDF and TXT files are supported")


async def save_uploaded_file_to_temp(file: UploadFile) -> tuple[str, int]:
    """
    Save the upload body to a temp file and return its path and byte size.
    Since the file is already processed by FastAPI into a SpooledTemporaryFile,
    we can determine its size instantly and write it directly.
    """
    settings = getSettings()

    #  Instantly determine file size without reading chunks
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)

    validate_upload(file, size)

    # Create the temp file
    extension = _file_extension(file.filename or "")
    fd, temp_path = tempfile.mkstemp(suffix=extension)
    os.close(fd)

    try:

        async with aiofiles.open(temp_path, "wb") as buffer:
            content = await file.read()
            await buffer.write(content)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return temp_path, size


def extract_text_pages(
    *, filename: str, content_type: str, file_path: str
) -> list[ExtractedPage]:
    extension = _file_extension(filename)

    if content_type == "application/pdf" or extension == ".pdf":
        pages: list[ExtractedPage] = []
        with fitz.open(file_path) as pdf:
            for index, page in enumerate(pdf, start=1):
                text = page.get_text("text").strip()
                if text:
                    pages.append(ExtractedPage(text=text, page_number=index))
        return pages

    if content_type == "text/plain" or extension == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read().strip()
        return [ExtractedPage(text=text, page_number=None)] if text else []

    raise BadRequest("Only PDF and TXT files are supported")


def get_token_length(text: str) -> int:
    return len(ENCODING.encode(text))


def split_pages_hierarchical(pages: list[ExtractedPage]) -> list[ExtractedChunk]:
    settings = getSettings()

    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.PARENT_CHUNK_SIZE_TOKENS,
        chunk_overlap=settings.PARENT_CHUNK_OVERLAP_TOKENS,
        length_function=get_token_length,
    )

    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=20,
        length_function=get_token_length,
    )

    chunks = []
    for page in pages:
        parent_texts = parent_splitter.split_text(page.text)

        for p_idx, parent_text in enumerate(parent_texts):
            parent_id = f"page_{page.page_number or 0}_parent_{p_idx}"

            child_texts = child_splitter.split_text(parent_text)

            for child_text in child_texts:
                cleaned = child_text.strip()
                if cleaned:
                    chunks.append(
                        ExtractedChunk(
                            text=cleaned,
                            parent_id=parent_id,
                            parent_text=parent_text,
                            page_number=page.page_number,
                        )
                    )
    return chunks


async def create_document_record(
    db: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> Document:
    await get_user_conversation(db, conversation_id, user_id)

    document = Document(
        user_id=user_id,
        conversation_id=conversation_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        status="processing",
        chunk_count=0,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def list_conversation_documents(
    db: AsyncSession, user_id: UUID, conversation_id: UUID
) -> list[Document]:
    await get_user_conversation(db, conversation_id, user_id)
    result = await db.execute(
        select(Document)
        .where(
            Document.user_id == user_id,
            Document.conversation_id == conversation_id,
        )
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_conversation_document(
    db: AsyncSession, document_id: UUID, conversation_id: UUID, user_id: UUID
) -> Document:
    await get_user_conversation(db, conversation_id, user_id)
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.conversation_id == conversation_id,
            Document.user_id == user_id,
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found")
    return document


async def validate_documents_for_conversation(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    document_ids: Optional[list[UUID]],
) -> list[UUID]:
    if not document_ids:
        return []

    await get_user_conversation(db, conversation_id, user_id)
    unique_ids = list(dict.fromkeys(document_ids))
    result = await db.execute(
        select(Document.id).where(
            Document.conversation_id == conversation_id,
            Document.user_id == user_id,
            Document.id.in_(unique_ids),
        )
    )
    found = set(result.scalars().all())
    if len(found) != len(unique_ids):
        raise ValidationError(
            "One or more documents do not belong to this conversation"
        )
    return unique_ids


async def delete_conversation_document(
    db: AsyncSession,
    *,
    document_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    vector_store: VectorStoreService,
) -> None:
    document = await get_conversation_document(
        db, document_id, conversation_id, user_id
    )
    await vector_store.delete_document(user_id=user_id, document_id=document_id)
    await db.delete(document)
    await db.commit()


async def process_document_upload(
    *,
    document_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    filename: str,
    content_type: str,
    file_path: str,
    embedding_service: EmbeddingService,
    vector_store: VectorStoreService,
) -> None:
    async with SessionLocal() as db:
        try:
            pages = await run_in_threadpool(
                extract_text_pages,
                filename=filename,
                content_type=content_type,
                file_path=file_path,
            )
            chunks = await run_in_threadpool(split_pages_hierarchical, pages)
            if not chunks:
                raise ValidationError("No readable text was found in the document")

            embeddings = await embedding_service.embed_texts(
                [chunk.text for chunk in chunks]
            )
            if len(embeddings) != len(chunks):
                raise RuntimeError("Embedding provider returned an unexpected result")

            vector_chunks: list[VectorChunk] = []

            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                page_num = chunk.page_number or 0

                # Format: doc_id:parent_id:child_index
                unique_chunk_id = f"{document_id}:{chunk.parent_id}:{index}"

                vector_chunks.append(
                    VectorChunk(
                        id=unique_chunk_id,
                        document_id=document_id,
                        user_id=user_id,
                        filename=filename,
                        page=page_num,
                        chunk_index=index,
                        content=chunk.text,
                        embedding=embedding,
                        parent_id=chunk.parent_id,
                        parent_content=chunk.parent_text,
                    )
                )

            await vector_store.add_chunks(vector_chunks)

            document = await get_conversation_document(
                db, document_id, conversation_id, user_id
            )
            document.status = "indexed"
            document.chunk_count = len(chunks)
            document.error_message = None
            await db.commit()
            logger.info("Indexed document %s with %s chunks", document_id, len(chunks))
        except Exception as exc:
            logger.exception("Document ingestion failed for %s", document_id)
            await db.rollback()
            document = await get_conversation_document(
                db, document_id, conversation_id, user_id
            )
            document.status = "failed"
            document.error_message = str(exc)[:1000]
            document.chunk_count = 0
            await db.commit()
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
