"""create session  table

Revision ID: 6090023d1049
Revises: c4cd36485924
Create Date: 2026-06-04 20:36:34.985182

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, ForeignKey, DateTime, func, text, Text
from core.ids import id_server_default
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "6090023d1049"
down_revision: Union[str, Sequence[str], None] = "c4cd36485924"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column(
            "user_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", name="fk_session_users_id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("refresh_token", Text, nullable=False),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "expires_at",
            DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index("ix_session_user_id", "session", ["user_id"], unique=False)
    op.create_index("ix_session_token", "session", ["refresh_token"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_session_user_id", table_name="session")
    op.drop_index("ix_session_token", table_name="session")
    op.drop_constraint("fk_session_users_id", "session", type_="foreignkey")
    op.drop_table("session")
