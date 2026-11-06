"""add parts to messages

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-06 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, so existing messages need no backfill; the API treats null as text.
    op.add_column("messages", Column("parts", JSONB, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("messages", "parts")
