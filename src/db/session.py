import logging
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    close_all_sessions,
)

from src.settings import get_db_settings

logger = logging.getLogger(__name__)
type sm_type = async_sessionmaker[AsyncSession]

_async_engine: AsyncEngine | None = None
_async_session_factory: sm_type | None = None

_async_engine_var: ContextVar[AsyncEngine | None] = ContextVar("db_async_engine", default=None)
_async_session_factory_var: ContextVar[sm_type | None] = ContextVar(
    "db_async_session_factory", default=None
)


def get_session_factory() -> sm_type:
    """Get the session factory instance from current context"""
    logger.debug("[DB] Getting session maker from current context")
    global _async_engine, _async_session_factory
    # TODO: use for all other cases too
    session_factory = _async_session_factory
    # session_factory = _async_session_factory_var.get()
    if session_factory is None:
        # session_factory = async_sessionmaker()
        # Try to initialize lazily for backward compatibility
        logger.warning("[DB] Session factory not initialized, attempting lazy initialization...")
        try:
            import asyncio

            # Check if we're in an async context
            asyncio.get_running_loop()
            raise RuntimeError(
                "Session factory not initialized. Make sure lifespan is properly set up."
            )

        except RuntimeError:
            # We're not in an async context, create a temporary factory
            logger.warning("[DB] Creating temporary session factory for non-async context")
            session_factory = _create_temporary_session_factory()
            # return _create_temporary_session_factory()

    return session_factory


def _create_temporary_session_factory() -> sm_type:
    """Create a temporary session factory for non-async contexts (like admin setup)"""
    logger.debug("[DB] Creating temporary session factory for non-async contexts")
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

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    logger.info("[DB] Database engine and session: save to context vars")
    # Set context variables
    # _async_engine_var.set(engine)
    # _async_session_factory_var.set(session_factory)

    return session_factory


async def initialize_database() -> None:
    """Initialize database engine and session factory in current context"""
    logger.info("[DB] Initializing database engine and session factory...")
    db_settings = get_db_settings()

    try:
        extra_kwargs: dict[str, str | int] = {"echo": db_settings.echo}
        if db_settings.pool_min_size:
            extra_kwargs["pool_size"] = db_settings.pool_min_size

        if db_settings.pool_max_size:
            extra_kwargs["max_overflow"] = db_settings.pool_max_size - (
                db_settings.pool_min_size or 5
            )

        engine = create_async_engine(db_settings.database_dsn, **extra_kwargs)
        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        logger.info("[DB] Database engine and session: save to context vars")
        # Set context variables
        _async_engine_var.set(engine)
        _async_session_factory_var.set(session_factory)

        logger.info("[DB] Database engine and session factory initialized successfully")

    except Exception as e:
        logger.error("[DB] Failed to initialize database: %s", str(e))
        raise


async def close_database() -> None:
    """Close database engine and cleanup resources from current context"""
    logger.info("[DB] Closing database engine...")

    try:
        logger.debug("[DB] Closing all async sessions...")
        await close_all_sessions()
    except Exception as exc:
        logger.error("[DB] Failed to close all async sessions: %r", exc)
        raise

    if _async_session_factory_var.get():
        _async_session_factory_var.set(None)

    if engine := _async_engine_var.get():
        await engine.dispose(close=True)
        _async_engine_var.set(None)

    logger.info("[DB] Database engine closed successfully")


# def get_async_sessionmaker() -> async_session_factory_type:
#     """Get async session factory - deprecated, use get_session_factory() instead"""
#     logger.warning("[DB] get_async_sessionmaker() is deprecated, use get_session_factory() instead")
#     return get_session_factory()
#
#
# def make_sa_session() -> AsyncSession:
#     """
#     Create a new SQLAlchemy session using the current context session factory.
#     This method is kept for backward compatibility but should be replaced
#     with dependency injection in new code.
#     """
#     logger.debug("[DB] Creating new async SQLAlchemy session")
#
#     try:
#         session_factory = get_session_factory()
#         return session_factory()
#     except Exception as e:
#         logger.error("[DB] Failed to create async session: %s", str(e))
#         raise
#
#
# @contextlib.asynccontextmanager
# async def session_scope() -> AsyncGenerator[AsyncSession, None]:
#     """Simple context manager that creates a new session for SQLAlchemy."""
#     session = make_sa_session()
#     try:
#         yield session
#     finally:
#         await session.close()
#         logger.debug("[DB] Session closed")
