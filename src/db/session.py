import logging
import contextlib
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm.session import sessionmaker, Session

from src.settings import get_db_settings

logger = logging.getLogger(__name__)


def get_async_sessionmaker() -> sessionmaker[Session]:
    """Create async session to database from SQLALCHEMY_DATABASE_URI"""
    db_settings = get_db_settings()
    engine = create_async_engine(db_settings.database_dsn)

    return sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)  # type: ignore


def make_sa_session() -> AsyncSession:
    """
    Create a new SQLAlchemy session for connection to SQLite database.
    """
    logger.debug("Creating new async SQLAlchemy session")
    db_settings = get_db_settings()

    try:
        engine = create_async_engine(
            db_settings.database_dsn,
            pool_size=db_settings.pool_min_size,
            echo=db_settings.echo,
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
