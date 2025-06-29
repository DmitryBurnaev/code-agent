import logging
from abc import ABC
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import make_sa_session

logger = logging.getLogger(__name__)


class SASessionUOW(ABC):
    """Unit Of Work around SQLAlchemy-session related items: repositories, ops"""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.__session: AsyncSession = session or make_sa_session()
        self.__need_to_commit: bool = False

    async def __aenter__(self) -> Self:
        logger.debug("[DB] Entering to the transaction block")
        return self

    async def __aexit__(
        self,
        exc_type: type[Exception],
        exc_val: Exception,
        exc_tb: TracebackType | None,
    ) -> None:

        if not self.__session:
            logger.debug("[DB] Session already closed")
            return

        await self.__session.flush()
        if self.__need_to_commit:
            await self.commit()

        await self.__session.close()

    @property
    def session(self) -> AsyncSession:
        """Provide a current session (open if it isn't created yet)"""
        return self.__session

    async def commit(self) -> None:
        """Sending changes to the database."""
        try:
            logger.debug("[DB] Committing changes...")
            await self.session.commit()
        except Exception as exc:
            logger.error("[DB] Failed to commit changes", exc_info=exc)
            await self.session.rollback()
            raise exc
        else:
            logger.debug("[DB] Committed changes")

    @property
    def need_to_commit(self) -> bool:
        return self.__need_to_commit

    @need_to_commit.setter
    def need_to_commit(self, value: bool) -> None:
        self.__need_to_commit = value
