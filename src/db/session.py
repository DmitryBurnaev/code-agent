import logging
import contextlib
from contextvars import ContextVar
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.settings import get_db_settings

logger = logging.getLogger(__name__)

# Context variables for async context management
_engine_var: ContextVar[Optional[create_async_engine]] = ContextVar("db_engine", default=None)
_session_factory_var: ContextVar[Optional[async_sessionmaker[AsyncSession]]] = ContextVar("db_session_factory", default=None)


def get_async_engine() -> create_async_engine:
    """Get the async engine instance from current context"""
    engine = _engine_var.get()
    if engine is None:
        raise RuntimeError("Database engine not initialized. Make sure lifespan is properly set up.")
    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory instance from current context"""
    session_factory = _session_factory_var.get()
    if session_factory is None:
        # Try to initialize lazily for backward compatibility
        logger.warning("[DB] Session factory not initialized, attempting lazy initialization...")
        try:
            import asyncio
            # Check if we're in an async context
            asyncio.get_running_loop()
            raise RuntimeError("Session factory not initialized. Make sure lifespan is properly set up.")
        except RuntimeError:
            # We're not in an async context, create a temporary factory
            logger.warning("[DB] Creating temporary session factory for non-async context")
            return _create_temporary_session_factory()
    return session_factory


def _create_temporary_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a temporary session factory for non-async contexts (like admin setup)"""
    db_settings = get_db_settings()
    
    extra_kwargs = {}
    if db_settings.pool_min_size:
        extra_kwargs["pool_size"] = db_settings.pool_min_size
    if db_settings.pool_max_size:
        extra_kwargs["max_overflow"] = db_settings.pool_max_size - (db_settings.pool_min_size or 5)

    engine = create_async_engine(
        db_settings.database_dsn,
        echo=db_settings.echo,
        **extra_kwargs,
    )
    
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def initialize_database() -> None:
    """Initialize database engine and session factory in current context"""
    logger.info("[DB] Initializing database engine and session factory...")
    db_settings = get_db_settings()
    
    try:
        extra_kwargs = {}
        if db_settings.pool_min_size:
            extra_kwargs["pool_size"] = db_settings.pool_min_size
        if db_settings.pool_max_size:
            extra_kwargs["max_overflow"] = db_settings.pool_max_size - (db_settings.pool_min_size or 5)

        engine = create_async_engine(
            db_settings.database_dsn,
            echo=db_settings.echo,
            **extra_kwargs,
        )
        
        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        
        # Set context variables
        _engine_var.set(engine)
        _session_factory_var.set(session_factory)
        
        logger.info("[DB] Database engine and session factory initialized successfully")
        
    except Exception as e:
        logger.error("[DB] Failed to initialize database: %s", str(e))
        raise


async def close_database() -> None:
    """Close database engine and cleanup resources from current context"""
    logger.info("[DB] Closing database engine...")
    
    session_factory = _session_factory_var.get()
    engine = _engine_var.get()
    
    if session_factory:
        await session_factory.close_all()
        _session_factory_var.set(None)
    
    if engine:
        await engine.dispose()
        _engine_var.set(None)
    
    logger.info("[DB] Database engine closed successfully")


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Get async session factory - deprecated, use get_session_factory() instead"""
    logger.warning("[DB] get_async_sessionmaker() is deprecated, use get_session_factory() instead")
    return get_session_factory()


def make_sa_session() -> AsyncSession:
    """
    Create a new SQLAlchemy session using the current context session factory.
    This method is kept for backward compatibility but should be replaced
    with dependency injection in new code.
    """
    logger.debug("[DB] Creating new async SQLAlchemy session")
    
    try:
        session_factory = get_session_factory()
        return session_factory()
    except Exception as e:
        logger.error("[DB] Failed to create async session: %s", str(e))
        raise


@contextlib.asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Simple context manager that creates a new session for SQLAlchemy."""
    session = make_sa_session()
    try:
        yield session
    finally:
        await session.close()
        logger.debug("[DB] Session closed")
