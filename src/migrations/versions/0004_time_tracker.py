"""Add time entries and reusable tags.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project", sa.String(length=128), nullable=False),
        sa.Column("task", sa.String(length=128), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_time_entries_user_id", "time_entries", ["user_id"], unique=False)
    op.create_index("ix_time_entries_started_at", "time_entries", ["started_at"], unique=False)
    op.create_index("ix_time_entries_ended_at", "time_entries", ["ended_at"], unique=False)
    op.create_index(
        "uq_time_entries_one_active_timer",
        "time_entries",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_table(
        "time_entry_tags",
        sa.Column("time_entry_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.ForeignKeyConstraint(["time_entry_id"], ["time_entries.id"]),
        sa.PrimaryKeyConstraint("time_entry_id", "tag_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("time_entry_tags")
    op.drop_index("uq_time_entries_one_active_timer", table_name="time_entries")
    op.drop_index("ix_time_entries_ended_at", table_name="time_entries")
    op.drop_index("ix_time_entries_started_at", table_name="time_entries")
    op.drop_index("ix_time_entries_user_id", table_name="time_entries")
    op.drop_table("time_entries")
    op.drop_table("tags")
