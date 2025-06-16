"""Vendors: vendor and vendor-settings

Revision ID: 0002
Revises: 0001
Create Date: 2025-06-10 10:20:31.899184

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.utils import utcnow
from src.constants import PROVIDER_URLS, VendorSlug

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("api_url", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.String(length=1024), nullable=False),
        sa.Column("timeout", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint("vendors_slug_uq", "vendors", ["slug"])
    # op.create_table(
    #     "vendor_settings",
    #     sa.Column("id", sa.Integer(), nullable=False),
    #     sa.Column("vendor_id", sa.Integer(), nullable=False),
    #     sa.Column("api_key", sa.String(length=1024), nullable=False),
    #     sa.Column("created_at", sa.DateTime(), nullable=False),
    #     sa.Column("updated_at", sa.DateTime(), nullable=False),
    #     sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
    #     sa.PrimaryKeyConstraint("id"),
    # )
    _add_initial_vendors(op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("vendors")


def _add_initial_vendors(connection: sa.Connection) -> None:
    query = """
        INSERT INTO vendors (slug, api_url, api_key, is_active, created_at)
        VALUES (:slug, :api_url, :api_key, :is_active, :created_at)            
    """
    now_time = utcnow()
    vendors_data = [
        {
            "slug": vendor_slug,
            "api_url": vendor_url,
            "api_key": "",
            "is_active": False,
            "created_at": now_time,
        }
        for vendor_slug, vendor_url in PROVIDER_URLS.items()
        if vendor_slug != VendorSlug.CUSTOM
    ]
    connection.execute(sa.text(query), vendors_data)
