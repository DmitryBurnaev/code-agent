"""Database module for the application."""

from src.db.dependencies import get_db_session, get_transactional_session, get_uow_with_session
from src.db.models import BaseModel, Client, Project, Vendor, User, Token, Tag, TimeEntry
from src.db.repositories import (
    UserRepository,
    VendorRepository,
    TokenRepository,
    TagRepository,
    ClientRepository,
    ProjectRepository,
    TimeEntryRepository,
)
from src.db.services import SASessionUOW
from src.db.session import get_session_factory, initialize_database, close_database

__all__ = (
    # Models
    "BaseModel",
    "Vendor",
    "User",
    "Token",
    "Tag",
    "Client",
    "Project",
    "TimeEntry",
    # Repositories
    "UserRepository",
    "VendorRepository",
    "TokenRepository",
    "TagRepository",
    "ClientRepository",
    "ProjectRepository",
    "TimeEntryRepository",
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
