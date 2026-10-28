"""Add independent user feature permissions, disabled by default.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: str = "0005"
branch_labels: None = None
depends_on: None = None

PERMISSION_COLUMNS = (
    "can_access_admin",
    "can_access_system_api",
    "can_use_llm",
    "can_use_time_tracking",
    "can_access_billing",
)


def upgrade() -> None:
    for name in PERMISSION_COLUMNS:
        op.add_column(
            "users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    for name in reversed(PERMISSION_COLUMNS):
        op.drop_column("users", name)
