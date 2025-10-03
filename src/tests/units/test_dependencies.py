from inspect import Traceback
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.services import SASessionUOW
from src.db.dependencies import get_db_session, get_transactional_session, get_uow_with_session


class MockSessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(
        self,
        exc_type: type[Exception],
        exc_val: Exception,
        exc_tb: Traceback,
    ) -> None:
        pass


@pytest.fixture
def mock_session() -> AsyncSession:
    s = AsyncMock(spec=AsyncSession)
    s.begin = AsyncMock()
    return s


@pytest.fixture
def mock_session_factory(mock_session: AsyncSession) -> Generator[MagicMock, None]:
    mock_session_factory = MagicMock(return_value=MockSessionFactory(mock_session))
    with patch("src.db.dependencies.get_session_factory", return_value=mock_session_factory):
        yield mock_session_factory


@pytest.fixture
def mock_logger() -> Generator[MagicMock, None]:
    with patch("src.db.dependencies.logger") as mock_logger:
        yield mock_logger


class TestGetDbSession:

    @pytest.mark.asyncio
    async def test_get_db_session_success(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        session = await anext(get_db_session())
        assert session == mock_session

        mock_session_factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_session_with_exception(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:

        async def session_generator() -> AsyncGenerator[AsyncSession, None]:
            _ = await anext(get_db_session())
            raise ValueError("Test error")
            # noinspection PyUnreachableCode
            yield _

        with pytest.raises(ValueError, match="Test error"):
            await anext(session_generator())

    @pytest.mark.asyncio
    async def test_get_db_session_context_manager(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        session_generator = get_db_session()
        session = await anext(session_generator)

        assert session == mock_session

        with pytest.raises(StopAsyncIteration):
            await anext(session_generator)


class TestGetTransactionalSession:

    @pytest.mark.asyncio
    async def test_get_transactional_session_success(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = False
        session = await anext(get_transactional_session())
        assert session == mock_session

        mock_session_factory.assert_called_once()
        mock_session.begin.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_transactional_session_with_exception(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = False

        async def session_generator() -> AsyncGenerator[AsyncSession, None]:
            _ = await anext(get_transactional_session())
            raise ValueError("Test error")
            yield _  # noqa

        with pytest.raises(ValueError, match="Test error"):
            await anext(session_generator())

        mock_session.begin.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_transactional_session_uncommitted_warning(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = True  # Transaction still active

        session_generator = get_transactional_session()
        session = await anext(session_generator)
        assert session == mock_session

        # Close the generator to trigger finally block
        await session_generator.aclose()

        # Verify warning was logged (check if it was called at least once)
        assert mock_logger.warning.called

    @pytest.mark.asyncio
    async def test_get_transactional_session_no_warning_when_committed(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = False  # Transaction completed
        await anext(get_transactional_session())

        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_transactional_session_context_manager(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = False
        session_generator = get_transactional_session()
        session = await anext(session_generator)

        assert session == mock_session

        with pytest.raises(StopAsyncIteration):
            await anext(session_generator)


class TestGetUowWithSession:

    @pytest.mark.asyncio
    async def test_get_uow_with_session_success(self, mock_session: AsyncMock) -> None:
        async for uow in get_uow_with_session(session=mock_session):
            assert isinstance(uow, SASessionUOW)
            assert uow.session == mock_session
            break

    @pytest.mark.asyncio
    async def test_get_uow_with_session_context_manager(self, mock_session: AsyncMock) -> None:
        # Test that we can iterate through the generator
        uow_generator = get_uow_with_session(session=mock_session)
        uow = await uow_generator.__anext__()

        assert isinstance(uow, SASessionUOW)
        assert uow.session == mock_session

        # Test that generator raises StopAsyncIteration when done
        with pytest.raises(StopAsyncIteration):
            await uow_generator.__anext__()

    @pytest.mark.asyncio
    async def test_get_uow_with_session_multiple_iterations(self, mock_session: AsyncMock) -> None:
        # First iteration
        async for uow in get_uow_with_session(session=mock_session):
            assert isinstance(uow, SASessionUOW)
            break

        # Second iteration
        async for uow in get_uow_with_session(session=mock_session):
            assert isinstance(uow, SASessionUOW)
            break

    @pytest.mark.asyncio
    async def test_get_uow_with_session_dependency_injection(self, mock_session: AsyncMock) -> None:
        # Test that the function accepts a session parameter
        async for uow in get_uow_with_session(session=mock_session):
            assert isinstance(uow, SASessionUOW)
            assert uow.session == mock_session
            break

    @pytest.mark.asyncio
    async def test_get_uow_with_session_uow_lifecycle(self, mock_session: AsyncMock) -> None:
        async for uow in get_uow_with_session(session=mock_session):
            # Test that UOW is properly initialized
            assert uow.session == mock_session

            # Test that UOW can be used (basic functionality)
            # Note: We don't test the actual UOW methods here as they're tested elsewhere
            assert hasattr(uow, "session")
            assert hasattr(uow, "mark_for_commit")
            break

    @pytest.mark.asyncio
    async def test_get_uow_with_session_finally_block(self, mock_session: AsyncMock) -> None:
        with patch("src.db.dependencies.SASessionUOW") as mock_uow_class:
            mock_uow_instance = MagicMock()
            mock_uow_class.return_value = mock_uow_instance

            async for uow in get_uow_with_session(session=mock_session):
                assert uow == mock_uow_instance
                break

            # Verify UOW was created with correct session
            mock_uow_class.assert_called_once_with(session=mock_session)


class TestDependenciesIntegration:

    @pytest.mark.asyncio
    async def test_dependencies_work_together(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = False
        session = await anext(get_db_session())
        assert session == mock_session

        tr_session = await anext(get_transactional_session())
        assert tr_session == mock_session

        uow = await anext(get_uow_with_session(session=mock_session))
        assert isinstance(uow, SASessionUOW)
        assert uow.session == mock_session

    @pytest.mark.asyncio
    async def test_dependencies_error_handling(
        self,
        mock_session: MagicMock,
        mock_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_session.in_transaction.return_value = False

        test_exception = ValueError("Test error")

        async def t_get_db_session() -> AsyncGenerator[AsyncSession, None]:
            _ = await anext(get_db_session())
            raise test_exception
            yield _  # noqa

        with pytest.raises(ValueError, match="Test error"):
            await anext(t_get_db_session())

        # Test that exceptions are properly handled in get_transactional_session
        async def t_get_db_transactional_session() -> AsyncGenerator[AsyncSession, None]:
            _ = await anext(get_transactional_session())
            raise test_exception
            yield _  # noqa

        with pytest.raises(ValueError, match="Test error"):
            await anext(t_get_db_transactional_session())
