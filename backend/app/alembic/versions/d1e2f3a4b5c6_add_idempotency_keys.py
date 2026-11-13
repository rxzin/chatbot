"""add idempotency keys to conversations and messages

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-11-13 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, and Postgres treats nulls as distinct in a unique index, so existing
    # rows and requests without a key are unaffected.
    op.add_column(
        "conversations", sa.Column("idempotency_key", sa.String(128), nullable=True)
    )
    op.add_column(
        "messages", sa.Column("idempotency_key", sa.String(128), nullable=True)
    )
    op.create_index(
        "uq_conversations_user_idem",
        "conversations",
        ["user_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_messages_conversation_idem",
        "messages",
        ["conversation_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_messages_conversation_idem", table_name="messages")
    op.drop_index("uq_conversations_user_idem", table_name="conversations")
    op.drop_column("messages", "idempotency_key")
    op.drop_column("conversations", "idempotency_key")
