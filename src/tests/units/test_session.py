"""Comprehensive tests for src/db/session.py module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.db.session import (
    AsyncDBConnectors,
    get_session_factory,
    initialize_database,
    close_database,
)


class TestAsyncDBConnectors:
    """Tests for AsyncDBConnectors class."""

    def test_init(self) -> None:
        """Test AsyncDBConnectors initialization."""
        # Test that we can create a new instance (even if singleton)
        connectors = AsyncDBConnectors()

        # Verify basic attributes exist
        assert hasattr(connectors, "engine")
        assert hasattr(connectors, "session_factory")
        assert hasattr(connectors, "settings")
        assert hasattr(connectors, "exc")

    @pytest.mark.asyncio
    async def test_init_connection_success(self) -> None:
        """Test successful database connection initialization."""
        mock_settings = MagicMock()
        mock_settings.echo = True
        mock_settings.pool_min_size = 5
        mock_settings.pool_max_size = 20
        mock_settings.database_dsn = "postgresql+asyncpg://test:test@localhost/test"

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_session_factory = MagicMock(spec=async_sessionmaker)

        with patch("src.db.session.get_db_settings", return_value=mock_settings):
            with patch(
                "src.db.session.create_async_engine", return_value=mock_engine
            ) as mock_create_engine:
                with patch(
                    "src.db.session.async_sessionmaker", return_value=mock_session_factory
                ) as mock_session_maker:
                    with patch("src.db.session.logger") as mock_logger:
                        connectors = AsyncDBConnectors()

                        # Mock the _ping_connection method
                        connectors._ping_connection = AsyncMock()

                        await connectors.init_connection()

                        # Verify engine creation
                        mock_create_engine.assert_called_once()

                        # Verify session factory creation
                        mock_session_maker.assert_called_once()

                        # Verify attributes are set
                        assert connectors.engine == mock_engine
                        assert connectors.session_factory == mock_session_factory

                        # Verify ping was called
                        connectors._ping_connection.assert_awaited_once()

                        # Verify logging
                        mock_logger.info.assert_any_call(
                            "[DB] Initializing database engine and session factory..."
                        )
                        mock_logger.info.assert_any_call(
                            "[DB] Database engine and session factory initialized successfully"
                        )

    @pytest.mark.asyncio
    async def test_init_connection_without_pool_settings(self) -> None:
        """Test database connection initialization without pool settings."""
        mock_settings = MagicMock()
        mock_settings.echo = False
        mock_settings.pool_min_size = None
        mock_settings.pool_max_size = None
        mock_settings.database_dsn = "postgresql+asyncpg://test:test@localhost/test"

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_session_factory = MagicMock(spec=async_sessionmaker)

        with patch("src.db.session.get_db_settings", return_value=mock_settings):
            with patch(
                "src.db.session.create_async_engine", return_value=mock_engine
            ) as mock_create_engine:
                with patch("src.db.session.async_sessionmaker", return_value=mock_session_factory):
                    with patch("src.db.session.logger"):
                        connectors = AsyncDBConnectors()
                        connectors._ping_connection = AsyncMock()

                        await connectors.init_connection()

                        # Verify engine creation without pool settings
                        mock_create_engine.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_connection_with_exception(self) -> None:
        """Test database connection initialization with exception."""
        mock_settings = MagicMock()
        mock_settings.database_dsn = "invalid://dsn"

        test_exception = Exception("Connection failed")

        with patch("src.db.session.get_db_settings", return_value=mock_settings):
            with patch("src.db.session.create_async_engine", side_effect=test_exception):
                with patch("src.db.session.logger") as mock_logger:
                    connectors = AsyncDBConnectors()
                    connectors.close_connection = AsyncMock()

                    with pytest.raises(Exception, match="Connection failed"):
                        await connectors.init_connection()

                    # Verify close_connection was called
                    connectors.close_connection.assert_awaited_once()

                    # Verify error logging
                    mock_logger.error.assert_called_with(
                        "[DB] Failed to initialize database: %r", test_exception
                    )


class TestSessionFactory:
    """Tests for get_session_factory function."""

    def test_get_session_factory_success(self) -> None:
        """Test successful session factory retrieval."""
        mock_session_factory = MagicMock(spec=async_sessionmaker)

        with patch("src.db.session._db_connectors") as mock_connectors:
            mock_connectors.session_factory = mock_session_factory

            result = get_session_factory()

            assert result == mock_session_factory

    def test_get_session_factory_not_initialized(self) -> None:
        """Test session factory retrieval when not initialized."""
        with patch("src.db.session._db_connectors") as mock_connectors:
            with patch("src.db.session.logger") as mock_logger:
                mock_connectors.session_factory = None

                with pytest.raises(RuntimeError, match="Session factory not initialized"):
                    get_session_factory()

                # Verify warning was logged
                mock_logger.warning.assert_called_with("[DB] Session factory not initialized!")


class TestDatabaseFunctions:
    """Tests for database initialization and cleanup functions."""

    @pytest.mark.asyncio
    async def test_initialize_database(self) -> None:
        """Test database initialization function."""
        with patch("src.db.session._db_connectors") as mock_connectors:
            mock_connectors.init_connection = AsyncMock()

            await initialize_database()

            mock_connectors.init_connection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_database(self) -> None:
        """Test database cleanup function."""
        with patch("src.db.session._db_connectors") as mock_connectors:
            mock_connectors.close_connection = AsyncMock()

            await close_database()

            mock_connectors.close_connection.assert_awaited_once()


class TestSingletonBehavior:
    """Tests for singleton behavior of AsyncDBConnectors."""

    def test_singleton_behavior(self) -> None:
        """Test that AsyncDBConnectors is a singleton."""
        # Create two instances
        instance1 = AsyncDBConnectors()
        instance2 = AsyncDBConnectors()

        # They should be the same instance
        assert instance1 is instance2


class TestIntegration:
    """Integration tests for session module."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Test full database lifecycle."""
        mock_settings = MagicMock()
        mock_settings.echo = False
        mock_settings.pool_min_size = None
        mock_settings.pool_max_size = None
        mock_settings.database_dsn = "postgresql+asyncpg://test:test@localhost/test"

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_session_factory = MagicMock(spec=async_sessionmaker)

        with patch("src.db.session.get_db_settings", return_value=mock_settings):
            with patch("src.db.session.create_async_engine", return_value=mock_engine):
                with patch("src.db.session.async_sessionmaker", return_value=mock_session_factory):
                    with patch("src.db.session.close_all_sessions", new_callable=AsyncMock):
                        with patch("src.db.session.logger"):
                            # Test initialization
                            await initialize_database()

                            # Test session factory retrieval
                            factory = get_session_factory()
                            assert factory == mock_session_factory

                            # Test cleanup
                            await close_database()

    @pytest.mark.asyncio
    async def test_error_handling_flow(self) -> None:
        """Test error handling throughout the lifecycle."""
        mock_settings = MagicMock()
        mock_settings.database_dsn = "invalid://dsn"

        with patch("src.db.session.get_db_settings", return_value=mock_settings):
            with patch(
                "src.db.session.create_async_engine", side_effect=Exception("Connection failed")
            ):
                with patch("src.db.session.logger"):
                    # Test that initialization fails properly
                    with pytest.raises(Exception, match="Connection failed"):
                        await initialize_database()

                    # Test that session factory retrieval fails
                    with patch("src.db.session._db_connectors") as mock_connectors:
                        mock_connectors.session_factory = None
                        with pytest.raises(RuntimeError, match="Session factory not initialized"):
                            get_session_factory()
