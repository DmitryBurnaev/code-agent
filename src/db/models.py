from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from src.utils import utcnow
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


class Vendor(BaseModel):
    """User model representing a Telegram user in the system."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    timeout: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    api_key: Mapped[str] = mapped_column(sa.String(1024))  # Store an encrypted API key
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=True, onupdate=utcnow)

    # Relationships
    settings: Mapped[list["VendorSettings"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"Vendor '{self.slug}'"

    def __repr__(self) -> str:
        return f"Vendor(id={self.id!r}, slug={self.slug!r}, url={self.url!r})"


class VendorSettings(BaseModel):
    """Vendor settings model for storing encrypted API keys and other sensitive data."""

    __tablename__ = "vendor_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(sa.ForeignKey("vendors.id", ondelete="CASCADE"))
    api_key: Mapped[str] = mapped_column(sa.String(1024))  # Store an encrypted API key
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, onupdate=utcnow)

    # Relationships
    vendor: Mapped["Vendor"] = relationship(back_populates="settings", lazy="joined")

    def __str__(self) -> str:
        return f"VendorSettings for '{self.vendor.slug}'"

    def __repr__(self) -> str:
        return f"VendorSettings(id={self.id!r}, vendor_id={self.vendor_id!r})"
