import logging
import contextlib
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.settings import get_settings

logger = logging.getLogger(__name__)


def make_sa_session() -> AsyncSession:
    """
    Create a new SQLAlchemy session for connection to SQLite database.
    """
    logger.debug("Creating new async SQLAlchemy session")
    settings = get_settings()

    try:
        engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            echo=settings.database_echo,
        )
        logger.debug("Successfully created async engine")
        return AsyncSession(engine)
    except Exception as e:
        logger.error("Failed to create async session: %s", str(e))
        raise


@contextlib.asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Simple context manager that creates a new session for SQLAlchemy."""
    session = make_sa_session()
    try:
        yield session
    finally:
        await session.close()
        logger.debug("Session closed")
