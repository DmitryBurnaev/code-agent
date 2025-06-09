"""User: new table and initial admin

Revision ID: 0002
Revises: 0001
Create Date: 2025-06-09 10:07:31.291278

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.settings import get_app_settings

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=128), nullable=False),
        sa.Column("password", sa.String(length=128), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _add_initial_admin(connection=op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users")


def _add_initial_admin(connection: sa.Connection) -> None:
    app_settings = get_app_settings()
    query = """
        INSERT INTO users (login, password)
        VALUES (:login, :password)            
    """
    users_data = {
        "login": app_settings.admin_login,
        "password": app_settings.admin_password,
    }
    connection.execute(sa.text(query), users_data)
