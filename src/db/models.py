from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column

from src.utils import utcnow
from src.constants import VendorSlug
from src.services.auth import PBKDF2PasswordHasher


class BaseModel(AsyncAttrs, DeclarativeBase):
    id: Mapped[int]


class User(BaseModel):
    """Users table for an authorization process"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(128), unique=True)
    password: Mapped[str] = mapped_column(sa.String(128))
    email: Mapped[str] = mapped_column(sa.String(128), nullable=True)
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @classmethod
    def make_password(cls, raw_password: str) -> str:
        hasher = PBKDF2PasswordHasher()
        return hasher.encode(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        hasher = PBKDF2PasswordHasher()
        verified, _ = hasher.verify(raw_password, encoded=str(self.password))
        return verified

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self.username

    def __str__(self) -> str:
        return f"User '{self.username}'"

    def __repr__(self) -> str:
        return (
            f"User("
            f"login='{self.username}', "
            f"email='{self.email}'"
            f"is_active='{self.is_active}'"
            f"is_admin='{self.is_admin}')"
        )


class Token(BaseModel):
    """Simple token storage for authorizing and API usages"""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column()
    system: Mapped[bool] = mapped_column(server_default=sa.false())
    token: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=True, onupdate=utcnow)

    # relations
    user: Mapped[User] = relationship(User, cascade="all, delete-orphan")

    def __str__(self) -> str:
        return f"Token for user '{self.user}'"

    def __repr__(self) -> str:
        return (
            f"Token("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"token='[MASKED]', "
            f"expires_at={self.expires_at}, "
            f"created_at={self.created_at}, "
            f"updated_at={self.updated_at}"
            f")"
        )


class Vendor(BaseModel):
    """User model representing a Telegram user in the system."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[VendorSlug] = mapped_column(sa.String(255), nullable=False, unique=True)
    api_url: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(sa.String(1024), nullable=False)  # Encrypted API key
    timeout: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=True, onupdate=utcnow)

    def __str__(self) -> str:
        return f"Vendor '{self.slug}'"

    def __repr__(self) -> str:
        return f"Vendor(id={self.id!r}, slug={self.slug!r}, is_active={self.is_active})"

    @property
    def decrypted_api_key(self) -> str:
        # TODO: use decryption algo (don't save api key in plain mode!)
        return self.api_key
