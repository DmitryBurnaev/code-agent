"""Execute the permission migration and verify stored data and defaults."""

from importlib import import_module
from datetime import datetime

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from src.application import CodeAgentAPP
from src.main import make_app
from src.settings import AppSettings

# Historical expectations must not grow with the live Permission enum or User model.
PERMISSIONS_0006 = (
    "can_access_admin",
    "can_access_system_api",
    "can_use_llm",
    "can_use_time_tracking",
    "can_access_billing",
)


@pytest.fixture
def test_app(app_settings_test: AppSettings) -> CodeAgentAPP:
    # Schema tests use a disposable SQL database and do not need application startup.
    return make_app(app_settings_test)


def test_upgrade_defaults_preserves_data_and_supports_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("src.migrations.versions.0006_user_permissions")
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username VARCHAR(128) UNIQUE NOT NULL,
                password VARCHAR(128) NOT NULL, email VARCHAR(128),
                is_admin BOOLEAN NOT NULL DEFAULT FALSE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at DATETIME NOT NULL
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO users VALUES
            (1, 'superuser', 'existing-hash', 'admin@example.test', TRUE, TRUE, '2026-10-27'),
            (2, 'member', 'existing-hash', 'member@example.test', FALSE, TRUE, '2026-10-27')
        """)
        connection.exec_driver_sql(
            "CREATE TABLE tokens (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), token TEXT)"
        )
        connection.exec_driver_sql("INSERT INTO tokens VALUES (1, 2, 'existing-token-hash')")
        connection.exec_driver_sql(
            "CREATE TABLE time_entries (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), task TEXT)"
        )
        connection.exec_driver_sql("INSERT INTO time_entries VALUES (1, 2, 'Existing work')")
        users_before = connection.exec_driver_sql("SELECT * FROM users ORDER BY id").all()
        tokens_before = connection.exec_driver_sql("SELECT * FROM tokens").all()
        entries_before = connection.exec_driver_sql("SELECT * FROM time_entries").all()
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))

        migration.upgrade()

        users_table = sa.Table("users", sa.MetaData(), autoload_with=connection)
        users = (
            connection.execute(sa.select(users_table).order_by(users_table.c.id)).mappings().all()
        )
        assert [user["is_admin"] for user in users] == [True, False]
        assert all(user[name] is False for user in users for name in PERMISSIONS_0006)
        connection.execute(
            users_table.insert().values(
                username="new-user",
                password="new-hash",
                created_at=datetime(2026, 10, 28),
            )
        )
        new_user = (
            connection.execute(sa.select(users_table).where(users_table.c.username == "new-user"))
            .mappings()
            .one()
        )
        assert new_user["is_admin"] is False
        assert all(new_user[name] is False for name in PERMISSIONS_0006)

        # A non-ORM insert must also receive disabled permissions from server defaults.
        connection.exec_driver_sql(
            "INSERT INTO users (id, username, password, created_at) VALUES (4, 'raw-user', 'hash', '2026-10-28')"
        )
        assert not any(
            connection.execute(
                sa.select(*(users_table.c[name] for name in PERMISSIONS_0006)).where(
                    users_table.c.id == 4
                )
            ).one()
        )

        migration.downgrade()

        assert (
            connection.exec_driver_sql("SELECT * FROM users WHERE id <= 2 ORDER BY id").all()
            == users_before
        )
        assert connection.exec_driver_sql("SELECT * FROM tokens").all() == tokens_before
        assert connection.exec_driver_sql("SELECT * FROM time_entries").all() == entries_before
        assert not set(PERMISSIONS_0006) & {
            c["name"] for c in sa.inspect(connection).get_columns("users")
        }
    engine.dispose()
