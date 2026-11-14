"""create user and conversation tables

Revision ID: c4cd36485924
Revises:
Create Date: 2026-06-04 19:34:00.807661

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, ForeignKey, Boolean, DateTime, String, func, text
from core.ids import id_server_default
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "c4cd36485924"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column("email", String(255), nullable=False, unique=True),
        Column("password", String(255), nullable=False),
        Column("is_active", Boolean, nullable=False, default=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "conversations",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column(
            "user_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", name="fk_users_id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("title", String(100), nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    op.create_index(
        "ix_conversations_user_id", "conversations", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("fk_users_id", "conversations", type_="foreignkey")
    op.drop_table("conversations")
    op.drop_table("users")
