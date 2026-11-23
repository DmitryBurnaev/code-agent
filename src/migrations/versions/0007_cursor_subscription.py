"""Add Cursor subscription vendor settings and a separate user grant.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_use_ai_subscriptions", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    with op.batch_alter_table("vendors") as batch:
        batch.add_column(
            sa.Column("auth_mode", sa.String(16), nullable=False, server_default="api_key")
        )
        batch.add_column(
            sa.Column(
                "subscription_models", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch.alter_column("api_url", existing_type=sa.String(255), nullable=True)
        batch.alter_column("api_key", existing_type=sa.String(1024), nullable=True)
        batch.create_check_constraint(
            "ck_vendor_auth_mode",
            "(auth_mode = 'api_key' AND api_url IS NOT NULL AND api_key IS NOT NULL) "
            "OR (auth_mode = 'subscription' AND slug = 'cursor')",
        )


def downgrade() -> None:
    missing_fields = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM vendors WHERE api_url IS NULL OR api_key IS NULL")
    )
    if missing_fields:
        raise RuntimeError("Configure an API URL and key or remove subscription-only vendors first")
    with op.batch_alter_table("vendors") as batch:
        batch.drop_constraint("ck_vendor_auth_mode", type_="check")
        batch.alter_column("api_url", existing_type=sa.String(255), nullable=False)
        batch.alter_column("api_key", existing_type=sa.String(1024), nullable=False)
        batch.drop_column("subscription_models")
        batch.drop_column("auth_mode")
    op.drop_column("users", "can_use_ai_subscriptions")
