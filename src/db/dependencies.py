"""Database dependencies for FastAPI application."""

import logging
from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session_factory

logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session for each request.
    
    This dependency creates a new session from the current context session factory
    and ensures it's properly closed after the request is processed.
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
