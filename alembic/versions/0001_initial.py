"""Initial: Users added

Revision ID: 0001
Revises:
Create Date: 2025-06-10 10:19:38.627169

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.services.auth import PBKDF2PasswordHasher
from src.settings import get_app_settings


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint("users_username_uq", "users", ["username"])
    _add_initial_admin(connection=op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users")


def _add_initial_admin(connection: sa.Connection) -> None:
    app_settings = get_app_settings()
    query = """
        INSERT INTO users (username, password, is_admin, is_active)
        VALUES (:username, :password, :is_admin, :is_active)            
    """
    users_data = {
        "username": app_settings.admin_username,
        "password": PBKDF2PasswordHasher().encode(app_settings.admin_password.get_secret_value()),
        "is_admin": True,
        "is_active": False,
    }
    connection.execute(sa.text(query), users_data)
