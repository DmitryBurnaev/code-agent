"""Verify the real PostgreSQL migration chain in a rolled-back private schema."""

import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.constants import APP_DIR
from src.db.models import User
from src.modules.auth.permissions import Permission
from src.settings.db import get_db_settings


@pytest.mark.postgresql
async def test_permission_schema_at_migration_head() -> None:
    if os.getenv("TEST_POSTGRES_MIGRATIONS") != "1":
        pytest.skip("Set TEST_POSTGRES_MIGRATIONS=1 to run the PostgreSQL migration-chain check")
    engine = create_async_engine(get_db_settings().database_dsn)
    schema = f"permission_test_{uuid4().hex}"

    def upgrade_and_check(connection: sa.Connection) -> None:
        config = Config()
        config.set_main_option("script_location", str(APP_DIR / "migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        columns = {column["name"]: column for column in sa.inspect(connection).get_columns("users")}
        permission_names = {permission.value for permission in Permission}
        assert {name for name in columns if name.startswith("can_")} == permission_names
        assert {
            column.key for column in sa.inspect(User).columns if column.key.startswith("can_")
        } == permission_names
        for name in permission_names:
            assert isinstance(columns[name]["type"], sa.Boolean)
            assert columns[name]["nullable"] is False
            assert columns[name]["default"] == "false"

    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                # Generated identifier; no input or application tables enter this schema.
                await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                await connection.run_sync(upgrade_and_check)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
