"""Database module for the application."""

from src.db.dependencies import get_db_session, get_transactional_session, get_uow_with_session
from src.db.models import BaseModel, Vendor, User, Token
from src.db.repositories import UserRepository, VendorRepository, TokenRepository
from src.db.services import SASessionUOW
from src.db.session import get_session_factory, initialize_database, close_database

__all__ = (
    # Models
    "BaseModel",
    "Vendor",
    "User",
    "Token",
    # Repositories
    "UserRepository",
    "VendorRepository",
    "TokenRepository",
    # Services
    "SASessionUOW",
    # Session management
    "get_session_factory",
    "initialize_database",
    "close_database",
    "get_db_session",
    "get_transactional_session",
    "get_uow_with_session",
)
