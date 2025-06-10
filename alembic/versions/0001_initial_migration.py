"""Initial: Users added

Revision ID: 0001
Revises:
Create Date: 2025-06-10 10:19:38.627169

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.services.auth_hasher import PBKDF2PasswordHasher
from src.settings import get_app_settings


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=128), nullable=False),
        sa.Column("password", sa.String(length=128), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _add_initial_admin(connection=op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users")


def _add_initial_admin(connection: sa.Connection) -> None:
    app_settings = get_app_settings()
    query = """
        INSERT INTO users (first_name, login, password)
        VALUES (:first_name, :login, :password)            
    """
    users_data = {
        "first_name": app_settings.admin_login,
        "login": app_settings.admin_login,
        "password": PBKDF2PasswordHasher().encode(app_settings.admin_password),
    }
    connection.execute(sa.text(query), users_data)
