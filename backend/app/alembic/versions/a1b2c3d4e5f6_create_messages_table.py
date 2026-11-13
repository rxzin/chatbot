"""create messages table

Revision ID: a1b2c3d4e5f6
Revises: 6090023d1049
Create Date: 2026-06-04 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func, text
from core.ids import id_server_default
from sqlalchemy.dialects.postgresql import UUID


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6090023d1049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column(
            "conversation_id",
            UUID(as_uuid=True),
            ForeignKey(
                "conversations.id",
                name="fk_messages_conversations_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column("role", String(16), nullable=False),
        Column("content", Text, nullable=False),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    op.create_index(
        "ix_messages_conversation_id", "messages", ["conversation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_constraint("fk_messages_conversations_id", "messages", type_="foreignkey")
    op.drop_table("messages")
