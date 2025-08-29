"""Database dependencies for FastAPI application."""

import logging
from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session_factory
from src.db.services import SASessionUOW

logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session for each request.

    This dependency creates a new session from the current context session factory
    and ensures it's properly closed after the request is processed.

    Use this for simple CRUD operations where automatic commit/rollback is acceptable.

    Example:
        async def get_user(id: int, session: AsyncSession = Depends(get_db_session)):
            user_repo = UserRepository(session=session)
            return await user_repo.get(id)
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            logger.debug("[DB] Session closed via dependency")


async def get_transactional_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session with explicit transaction control.

    This dependency creates a session but does NOT automatically commit/rollback.
    You must explicitly control the transaction using UOW or manual commit/rollback.

    Use this for complex operations where you need fine-grained transaction control.

    Example:
        async def complex_operation(session: AsyncSession = Depends(get_transactional_session)):
            user_repo = UserRepository(session=session)
            token_repo = TokenRepository(session=session)

            user = await user_repo.create(user_data)
            token = await token_repo.create(token_data)

            await session.commit()  # Manual commit required
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            # Start transaction
            await session.begin()
            logger.debug("[DB] Started transaction via dependency")
            yield session
        except Exception:
            await session.rollback()
            logger.debug("[DB] Transaction rolled back due to exception")
            raise
        finally:
            # Note: We don't commit here - caller must handle it
            if session.in_transaction():
                logger.warning("[DB] Transaction not committed - caller should handle it")
            await session.close()
            logger.debug("[DB] Transactional session closed")


async def get_uow_with_session(
    session: AsyncSession = Depends(get_transactional_session),
) -> AsyncGenerator[SASessionUOW, None]:
    """
    Dependency that provides a UOW instance with a session from dependency injection.

    This combines the benefits of dependency injection with UOW transaction control.
    The session lifecycle is managed by the dependency, but transaction control
    is handled by UOW.

    Use this for complex atomic operations requiring multiple repository operations.

    Example:
        async def complex_operation(uow: SASessionUOW = Depends(get_uow_with_session)):
            async with uow:
                user_repo = UserRepository(session=uow.session)
                token_repo = TokenRepository(session=uow.session)

                user = await user_repo.create(user_data)
                token = await token_repo.create(token_data)

                uow.mark_for_commit()  # Explicit commit control
    """
    uow = SASessionUOW(session=session)
    try:
        yield uow
    finally:
        # UOW will handle transaction control, dependency will handle session lifecycle
        pass
