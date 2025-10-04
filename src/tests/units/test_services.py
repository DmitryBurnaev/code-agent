from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.services import SASessionUOW


@pytest.fixture
def mock_logger() -> Generator[MagicMock, None]:
    with patch("src.db.services.logger") as mock_logger:
        yield mock_logger


class TestSASessionUOW:

    def test_init_standalone_mode(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW()

        # Verify session was created
        mock_db_session_factory.assert_called_once()
        assert uow.session == mock_db_session
        assert uow.owns_session is True
        assert uow.need_to_commit is False

    def test_init_dependency_mode(self) -> None:
        mock_session = AsyncMock(spec=AsyncSession)

        uow = SASessionUOW(session=mock_session)

        # Verify session was set
        assert uow.session == mock_session
        assert uow.owns_session is False
        assert uow.need_to_commit is False

    @pytest.mark.asyncio
    async def test_aenter_standalone_mode(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = False

        uow = SASessionUOW()
        result = await uow.__aenter__()

        # Verify transaction was started
        mock_db_session.begin.assert_awaited_once()
        mock_logger.debug.assert_any_call("[DB] Entering UOW transaction block")
        mock_logger.debug.assert_any_call("[DB] Started new transaction")
        assert result is uow

    @pytest.mark.asyncio
    async def test_aenter_dependency_mode_with_transaction(
        self,
        mock_db_session: AsyncMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = True

        uow = SASessionUOW(session=mock_db_session)
        result = await uow.__aenter__()

        # Verify no new transaction was started
        mock_db_session.begin.assert_not_called()
        mock_logger.debug.assert_called_once_with("[DB] Entering UOW transaction block")
        assert result is uow

    @pytest.mark.asyncio
    async def test_aenter_dependency_mode_without_transaction(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = False

        uow = SASessionUOW(session=mock_db_session)
        result = await uow.__aenter__()

        # Verify transaction was started
        mock_db_session.begin.assert_awaited_once()
        mock_logger.debug.assert_any_call("[DB] Entering UOW transaction block")
        mock_logger.debug.assert_any_call("[DB] Started new transaction")
        assert result is uow

    @pytest.mark.asyncio
    async def test_aexit_standalone_mode_success(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW()
        uow.mark_for_commit()

        await uow.__aexit__(None, None, None)

        # Verify flush and commit were called
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.close.assert_awaited_once()
        mock_logger.debug.assert_any_call("[DB] Session closed")

    @pytest.mark.asyncio
    async def test_aexit_standalone_mode_exception(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW()
        await uow.__aexit__(ValueError, ValueError("test error"), None)

        # Verify flush and rollback were called
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.rollback.assert_awaited_once()
        mock_db_session.close.assert_awaited_once()
        mock_logger.debug.assert_any_call("[DB] Session closed")

    @pytest.mark.asyncio
    async def test_aexit_standalone_mode_no_commit_no_exception(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW()
        await uow.__aexit__(None, None, None)

        # Verify flush and commit were called (default behavior)
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_dependency_mode_success(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW(session=mock_db_session)
        uow.mark_for_commit()

        await uow.__aexit__(None, None, None)

        # Verify flush and commit were called, but not close
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aexit_dependency_mode_exception(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:

        uow = SASessionUOW(session=mock_db_session)

        await uow.__aexit__(ValueError, ValueError("test error"), None)

        # Verify flush and rollback were called, but not close
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.rollback.assert_awaited_once()
        mock_db_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aexit_session_already_closed(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW(session=None)

        await uow.__aexit__(None, None, None)
        assert True  # This test verifies the method doesn't crash

    @pytest.mark.asyncio
    async def test_aexit_exception_during_cleanup(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.flush.side_effect = Exception("Flush failed")

        uow = SASessionUOW()

        with pytest.raises(Exception, match="Flush failed"):
            await uow.__aexit__(None, None, None)

        # Verify error logging and session close
        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if call[0][0] == "[DB] Error during UOW cleanup: %r"
        ]
        assert len(error_calls) > 0
        mock_db_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_success(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW(session=mock_db_session)
        uow.mark_for_commit()

        await uow.commit()

        # Verify commit was called
        mock_db_session.commit.assert_awaited_once()
        assert uow.need_to_commit is False
        mock_logger.debug.assert_any_call("[DB] Committing transaction...")
        mock_logger.debug.assert_any_call("[DB] Transaction committed successfully")

    @pytest.mark.asyncio
    async def test_commit_failure(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.commit.side_effect = Exception("Commit failed")
        uow = SASessionUOW(session=mock_db_session)
        uow.mark_for_commit()

        with pytest.raises(Exception, match="Commit failed"):
            await uow.commit()

        # Verify rollback was called
        mock_db_session.rollback.assert_awaited_once()
        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if call[0][0] == "[DB] Failed to commit transaction"
        ]
        assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_rollback_success(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        uow = SASessionUOW(session=mock_db_session)
        uow.mark_for_commit()

        await uow.rollback()

        # Verify rollback was called
        mock_db_session.rollback.assert_awaited_once()
        assert uow.need_to_commit is False
        mock_logger.debug.assert_any_call("[DB] Rolling back transaction...")
        mock_logger.debug.assert_any_call("[DB] Transaction rolled back successfully")

    @pytest.mark.asyncio
    async def test_rollback_failure(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.rollback.side_effect = Exception("Rollback failed")
        uow = SASessionUOW(session=mock_db_session)

        with pytest.raises(Exception, match="Rollback failed"):
            await uow.rollback()

        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if call[0][0] == "[DB] Failed to rollback transaction"
        ]
        assert len(error_calls) > 0

    def test_need_to_commit_property(self) -> None:
        uow = SASessionUOW(session=AsyncMock(spec=AsyncSession))

        # Test getter
        assert uow.need_to_commit is False

        # Test setter
        uow.need_to_commit = True
        assert uow.need_to_commit is True

        uow.need_to_commit = False
        assert uow.need_to_commit is False

    def test_owns_session_property(self, mock_db_session_factory: MagicMock) -> None:
        uow = SASessionUOW()
        assert uow.owns_session is True

        # Dependency mode
        uow = SASessionUOW(session=AsyncMock(spec=AsyncSession))
        assert uow.owns_session is False

    def test_mark_for_commit(self, mock_db_session: AsyncMock) -> None:
        uow = SASessionUOW(session=mock_db_session)

        assert uow.need_to_commit is False
        uow.mark_for_commit()
        assert uow.need_to_commit is True


class TestSASessionUOWIntegration:
    """Integration tests for SASessionUOW."""

    @pytest.mark.asyncio
    async def test_context_manager_standalone_mode(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = False

        async with SASessionUOW() as uow:
            # Verify session is available
            assert uow.session == mock_db_session
            assert uow.owns_session is True

            # Mark for commit
            uow.mark_for_commit()

        # Verify transaction was started and committed
        mock_db_session.begin.assert_awaited_once()
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_manager_dependency_mode(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = False
        mock_db_session.begin = AsyncMock()

        async with SASessionUOW(session=mock_db_session) as uow:
            # Verify session is available
            assert uow.session == mock_db_session
            assert uow.owns_session is False

            # Mark for commit
            uow.mark_for_commit()

        # Verify transaction was started and committed, but session not closed
        mock_db_session.begin.assert_awaited_once()
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = False

        with pytest.raises(ValueError, match="test error"):
            async with SASessionUOW() as uow:
                # Mark for commit
                uow.mark_for_commit()
                raise ValueError("test error")

        # Verify transaction was started and rolled back
        mock_db_session.begin.assert_awaited_once()
        mock_db_session.flush.assert_awaited_once()
        mock_db_session.rollback.assert_awaited_once()
        mock_db_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_operations(
        self,
        mock_db_session: MagicMock,
        mock_db_session_factory: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        mock_db_session.in_transaction.return_value = False

        async with SASessionUOW() as uow:
            # Perform multiple operations
            uow.mark_for_commit()
            await uow.commit()
            uow.mark_for_commit()
            await uow.rollback()

        # Verify all operations were called
        mock_db_session.begin.assert_awaited_once()
        mock_db_session.flush.assert_awaited_once()
        # commit was called twice: once explicitly and once in __aexit__
        assert mock_db_session.commit.await_count == 2
        mock_db_session.rollback.assert_awaited_once()
        mock_db_session.close.assert_awaited_once()
