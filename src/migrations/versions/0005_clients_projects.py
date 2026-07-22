"""Add configurable clients and projects.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create client/project configuration and link existing entries safely."""
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_projects_client_id", "projects", ["client_id"], unique=False)
    op.add_column("time_entries", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_index("ix_time_entries_project_id", "time_entries", ["project_id"], unique=False)
    op.create_foreign_key(
        "fk_time_entries_project_id_projects",
        "time_entries",
        "projects",
        ["project_id"],
        ["id"],
    )

    op.execute("""
        INSERT INTO projects (name, created_at)
        SELECT DISTINCT project, NOW()
        FROM time_entries
        ON CONFLICT (name) DO NOTHING
        """)
    op.execute("""
        UPDATE time_entries
        SET project_id = projects.id
        FROM projects
        WHERE projects.name = time_entries.project
        """)


def downgrade() -> None:
    """Remove client/project configuration."""
    op.drop_constraint("fk_time_entries_project_id_projects", "time_entries", type_="foreignkey")
    op.drop_index("ix_time_entries_project_id", table_name="time_entries")
    op.drop_column("time_entries", "project_id")
    op.drop_index("ix_projects_client_id", table_name="projects")
    op.drop_table("projects")
    op.drop_table("clients")
