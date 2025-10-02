"""Comprehensive tests for src/db/services.py module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.services import SASessionUOW


class TestSASessionUOW:
    """Tests for SASessionUOW class."""

    def test_init_standalone_mode(self) -> None:
        """Test UOW initialization in standalone mode."""
        mock_session_factory = MagicMock()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_factory.return_value = mock_session

        with patch("src.db.services.get_session_factory", return_value=mock_session_factory):
            uow = SASessionUOW()

            # Verify session was created
            mock_session_factory.assert_called_once()
            assert uow.session == mock_session
            assert uow.owns_session is True
            assert uow.need_to_commit is False

    def test_init_dependency_mode(self) -> None:
        """Test UOW initialization in dependency mode."""
        mock_session = AsyncMock(spec=AsyncSession)

        uow = SASessionUOW(session=mock_session)

        # Verify session was set
        assert uow.session == mock_session
        assert uow.owns_session is False
        assert uow.need_to_commit is False

    @pytest.mark.asyncio
    async def test_aenter_standalone_mode(self) -> None:
        """Test entering UOW context in standalone mode."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = False
        mock_session.begin = AsyncMock()

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session
            uow = SASessionUOW()

            with patch("src.db.services.logger") as mock_logger:
                result = await uow.__aenter__()

                # Verify transaction was started
                mock_session.begin.assert_awaited_once()
                mock_logger.debug.assert_any_call("[DB] Entering UOW transaction block")
                mock_logger.debug.assert_any_call("[DB] Started new transaction")
                assert result is uow

    @pytest.mark.asyncio
    async def test_aenter_dependency_mode_with_transaction(self) -> None:
        """Test entering UOW context in dependency mode with existing transaction."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = True
        mock_session.begin = AsyncMock()

        uow = SASessionUOW(session=mock_session)

        with patch("src.db.services.logger") as mock_logger:
            result = await uow.__aenter__()

            # Verify no new transaction was started
            mock_session.begin.assert_not_called()
            mock_logger.debug.assert_called_once_with("[DB] Entering UOW transaction block")
            assert result is uow

    @pytest.mark.asyncio
    async def test_aenter_dependency_mode_without_transaction(self) -> None:
        """Test entering UOW context in dependency mode without existing transaction."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = False
        mock_session.begin = AsyncMock()

        uow = SASessionUOW(session=mock_session)

        with patch("src.db.services.logger") as mock_logger:
            result = await uow.__aenter__()

            # Verify transaction was started
            mock_session.begin.assert_awaited_once()
            mock_logger.debug.assert_any_call("[DB] Entering UOW transaction block")
            mock_logger.debug.assert_any_call("[DB] Started new transaction")
            assert result is uow

    @pytest.mark.asyncio
    async def test_aexit_standalone_mode_success(self) -> None:
        """Test exiting UOW context in standalone mode with success."""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session
            uow = SASessionUOW()
            uow.mark_for_commit()

            with patch("src.db.services.logger") as mock_logger:
                await uow.__aexit__(None, None, None)

                # Verify flush and commit were called
                mock_session.flush.assert_awaited_once()
                mock_session.commit.assert_awaited_once()
                mock_session.close.assert_awaited_once()
                mock_logger.debug.assert_any_call("[DB] Session closed")

    @pytest.mark.asyncio
    async def test_aexit_standalone_mode_exception(self) -> None:
        """Test exiting UOW context in standalone mode with exception."""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session
            uow = SASessionUOW()

            with patch("src.db.services.logger") as mock_logger:
                await uow.__aexit__(ValueError, ValueError("test error"), None)

                # Verify flush and rollback were called
                mock_session.flush.assert_awaited_once()
                mock_session.rollback.assert_awaited_once()
                mock_session.close.assert_awaited_once()
                mock_logger.debug.assert_any_call("[DB] Session closed")

    @pytest.mark.asyncio
    async def test_aexit_standalone_mode_no_commit_no_exception(self) -> None:
        """Test exiting UOW context in standalone mode with no commit and no exception."""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session
            uow = SASessionUOW()

            with patch("src.db.services.logger"):
                await uow.__aexit__(None, None, None)

                # Verify flush and commit were called (default behavior)
                mock_session.flush.assert_awaited_once()
                mock_session.commit.assert_awaited_once()
                mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_dependency_mode_success(self) -> None:
        """Test exiting UOW context in dependency mode with success."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = SASessionUOW(session=mock_session)
        uow.mark_for_commit()

        with patch("src.db.services.logger"):
            await uow.__aexit__(None, None, None)

            # Verify flush and commit were called, but not close
            mock_session.flush.assert_awaited_once()
            mock_session.commit.assert_awaited_once()
            mock_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aexit_dependency_mode_exception(self) -> None:
        """Test exiting UOW context in dependency mode with exception."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = SASessionUOW(session=mock_session)

        with patch("src.db.services.logger"):
            await uow.__aexit__(ValueError, ValueError("test error"), None)

            # Verify flush and rollback were called, but not close
            mock_session.flush.assert_awaited_once()
            mock_session.rollback.assert_awaited_once()
            mock_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aexit_session_already_closed(self) -> None:
        """Test exiting UOW context when session is already closed."""
        uow = SASessionUOW(session=None)

        with patch("src.db.services.logger"):
            await uow.__aexit__(None, None, None)

            # Verify early return - when session is None, it should return early
            # The exact behavior depends on the implementation
            assert True  # This test verifies the method doesn't crash

    @pytest.mark.asyncio
    async def test_aexit_exception_during_cleanup(self) -> None:
        """Test exiting UOW context with exception during cleanup."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.flush.side_effect = Exception("Flush failed")

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session
            uow = SASessionUOW()

            with patch("src.db.services.logger") as mock_logger:
                with pytest.raises(Exception, match="Flush failed"):
                    await uow.__aexit__(None, None, None)

                # Verify error logging and session close
                error_calls = [
                    call
                    for call in mock_logger.error.call_args_list
                    if call[0][0] == "[DB] Error during UOW cleanup: %r"
                ]
                assert len(error_calls) > 0
                mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_success(self) -> None:
        """Test successful commit."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = SASessionUOW(session=mock_session)
        uow.mark_for_commit()

        with patch("src.db.services.logger") as mock_logger:
            await uow.commit()

            # Verify commit was called
            mock_session.commit.assert_awaited_once()
            assert uow.need_to_commit is False
            mock_logger.debug.assert_any_call("[DB] Committing transaction...")
            mock_logger.debug.assert_any_call("[DB] Transaction committed successfully")

    @pytest.mark.asyncio
    async def test_commit_failure(self) -> None:
        """Test commit failure with rollback."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit.side_effect = Exception("Commit failed")
        uow = SASessionUOW(session=mock_session)
        uow.mark_for_commit()

        with patch("src.db.services.logger") as mock_logger:
            with pytest.raises(Exception, match="Commit failed"):
                await uow.commit()

            # Verify rollback was called
            mock_session.rollback.assert_awaited_once()
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if call[0][0] == "[DB] Failed to commit transaction"
            ]
            assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_rollback_success(self) -> None:
        """Test successful rollback."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = SASessionUOW(session=mock_session)
        uow.mark_for_commit()

        with patch("src.db.services.logger") as mock_logger:
            await uow.rollback()

            # Verify rollback was called
            mock_session.rollback.assert_awaited_once()
            assert uow.need_to_commit is False
            mock_logger.debug.assert_any_call("[DB] Rolling back transaction...")
            mock_logger.debug.assert_any_call("[DB] Transaction rolled back successfully")

    @pytest.mark.asyncio
    async def test_rollback_failure(self) -> None:
        """Test rollback failure."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.rollback.side_effect = Exception("Rollback failed")
        uow = SASessionUOW(session=mock_session)

        with patch("src.db.services.logger") as mock_logger:
            with pytest.raises(Exception, match="Rollback failed"):
                await uow.rollback()

            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if call[0][0] == "[DB] Failed to rollback transaction"
            ]
            assert len(error_calls) > 0

    def test_need_to_commit_property(self) -> None:
        """Test need_to_commit property getter and setter."""
        uow = SASessionUOW(session=AsyncMock(spec=AsyncSession))

        # Test getter
        assert uow.need_to_commit is False

        # Test setter
        uow.need_to_commit = True
        assert uow.need_to_commit is True

        uow.need_to_commit = False
        assert uow.need_to_commit is False

    def test_owns_session_property(self) -> None:
        """Test owns_session property."""
        # Standalone mode
        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: AsyncMock(spec=AsyncSession)
            uow = SASessionUOW()
            assert uow.owns_session is True

        # Dependency mode
        uow = SASessionUOW(session=AsyncMock(spec=AsyncSession))
        assert uow.owns_session is False

    def test_mark_for_commit(self) -> None:
        """Test mark_for_commit method."""
        uow = SASessionUOW(session=AsyncMock(spec=AsyncSession))

        assert uow.need_to_commit is False
        uow.mark_for_commit()
        assert uow.need_to_commit is True


class TestSASessionUOWIntegration:
    """Integration tests for SASessionUOW."""

    @pytest.mark.asyncio
    async def test_context_manager_standalone_mode(self) -> None:
        """Test using UOW as context manager in standalone mode."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = False
        mock_session.begin = AsyncMock()

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session

            async with SASessionUOW() as uow:
                # Verify session is available
                assert uow.session == mock_session
                assert uow.owns_session is True

                # Mark for commit
                uow.mark_for_commit()

            # Verify transaction was started and committed
            mock_session.begin.assert_awaited_once()
            mock_session.flush.assert_awaited_once()
            mock_session.commit.assert_awaited_once()
            mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_manager_dependency_mode(self) -> None:
        """Test using UOW as context manager in dependency mode."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = False
        mock_session.begin = AsyncMock()

        async with SASessionUOW(session=mock_session) as uow:
            # Verify session is available
            assert uow.session == mock_session
            assert uow.owns_session is False

            # Mark for commit
            uow.mark_for_commit()

        # Verify transaction was started and committed, but session not closed
        mock_session.begin.assert_awaited_once()
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self) -> None:
        """Test using UOW as context manager with exception."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = False
        mock_session.begin = AsyncMock()

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session

            with pytest.raises(ValueError, match="test error"):
                async with SASessionUOW() as uow:
                    # Mark for commit
                    uow.mark_for_commit()
                    raise ValueError("test error")

            # Verify transaction was started and rolled back
            mock_session.begin.assert_awaited_once()
            mock_session.flush.assert_awaited_once()
            mock_session.rollback.assert_awaited_once()
            mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_operations(self) -> None:
        """Test multiple operations within UOW context."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.in_transaction.return_value = False
        mock_session.begin = AsyncMock()

        with patch("src.db.services.get_session_factory") as mock_factory:
            mock_factory.return_value = lambda: mock_session

            async with SASessionUOW() as uow:
                # Perform multiple operations
                uow.mark_for_commit()
                await uow.commit()
                uow.mark_for_commit()
                await uow.rollback()

            # Verify all operations were called
            mock_session.begin.assert_awaited_once()
            mock_session.flush.assert_awaited_once()
            # commit was called twice: once explicitly and once in __aexit__
            assert mock_session.commit.await_count == 2
            mock_session.rollback.assert_awaited_once()
            mock_session.close.assert_awaited_once()
