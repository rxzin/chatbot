"""create documents tables

Revision ID: b7c8d9e0f1a2
Revises: af7d28136461
Create Date: 2026-06-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func, text
from core.ids import id_server_default
from sqlalchemy.dialects.postgresql import JSON, UUID


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "af7d28136461"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column(
            "user_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", name="fk_documents_users_id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("filename", String(255), nullable=False),
        Column("content_type", String(100), nullable=False),
        Column("size_bytes", Integer, nullable=False),
        Column("status", String(32), nullable=False, server_default="processing"),
        Column("chunk_count", Integer, nullable=False, server_default="0"),
        Column("error_message", Text, nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_constraint("fk_documents_users_id", "documents", type_="foreignkey")
    op.drop_table("documents")
