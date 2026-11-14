"""id column defaults follow the ID_STRATEGY setting

Revision ID: e3f5a7b9c1d2
Revises: d1e2f3a4b5c6
Create Date: 2026-11-13 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

from core.ids import id_server_default

# revision identifiers, used by Alembic.
revision: str = "e3f5a7b9c1d2"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "users",
    "conversations",
    "messages",
    "llm_usage",
    "session",
    "audit_logs",
    "roles",
    "permissions",
    "documents",
    "pending_jira_tickets",
)


def _set_default(sql: str) -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT {sql}")


def upgrade() -> None:
    """With the default strategy this changes nothing."""
    _set_default(str(id_server_default()))


def downgrade() -> None:
    """Back to uuidv7(), what the migrations before this one create."""
    _set_default("uuidv7()")
