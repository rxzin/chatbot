"""create permissions and roles tables

Revision ID: af7d28136461
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 11:11:43.084806

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, ForeignKey, String, Text, text
from core.ids import id_server_default
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "af7d28136461"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "permissions",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column("name", String(100), nullable=False, unique=True),
        Column("resource", String(50), nullable=False),
        Column("action", String(50), nullable=False),
        Column("description", Text),
    )
    op.create_table(
        "roles",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=id_server_default(),
        ),
        Column("name", String(20), nullable=False, unique=True),
    )

    op.create_table(
        "role_permissions",
        Column(
            "role_id",
            UUID(as_uuid=True),
            ForeignKey("roles.id", name="fk_rp_r_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "permission_id",
            UUID(as_uuid=True),
            ForeignKey("permissions.id", name="fk_rp_p_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    op.create_table(
        "users_roles",
        Column(
            "user_id",
            UUID(as_uuid=True),
            ForeignKey("users.id", name="fk_ur_u_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "role_id",
            UUID(as_uuid=True),
            ForeignKey("roles.id", name="fk_ur_r_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
