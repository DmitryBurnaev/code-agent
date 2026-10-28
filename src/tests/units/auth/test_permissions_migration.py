"""Execute the permission migration and verify stored data and defaults."""

from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.db.models import User
from src.main import CodeAgentAPP, make_app
from src.modules.auth.permissions import Permission, has_permission
from src.settings import AppSettings


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

        with Session(connection) as session:
            users: list[User] = list(session.scalars(sa.select(User).order_by(User.id)))
            assert [user.is_admin for user in users] == [True, False]
            assert all(
                getattr(user, permission.value) is False
                for user in users
                for permission in Permission
            )
            assert all(has_permission(users[0], permission) for permission in Permission)
            assert not any(has_permission(users[1], permission) for permission in Permission)
            new_user = User(username="new-user", password="new-hash")
            session.add(new_user)
            session.flush()
            session.refresh(new_user)
            assert new_user.is_admin is False
            assert all(getattr(new_user, permission.value) is False for permission in Permission)

        # A non-ORM insert must also receive disabled permissions from server defaults.
        connection.exec_driver_sql(
            "INSERT INTO users (id, username, password, created_at) VALUES (4, 'raw-user', 'hash', '2026-10-28')"
        )
        assert not any(
            connection.execute(
                sa.select(*(User.__table__.c[p.value] for p in Permission)).where(User.id == 4)
            ).one()
        )

        migration.downgrade()

        assert (
            connection.exec_driver_sql("SELECT * FROM users WHERE id <= 2 ORDER BY id").all()
            == users_before
        )
        assert connection.exec_driver_sql("SELECT * FROM tokens").all() == tokens_before
        assert connection.exec_driver_sql("SELECT * FROM time_entries").all() == entries_before
        assert not {p.value for p in Permission} & {
            c["name"] for c in sa.inspect(connection).get_columns("users")
        }
    engine.dispose()
