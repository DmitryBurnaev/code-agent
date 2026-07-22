from datetime import datetime
import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column, backref

from src.exceptions import VendorEncryptionError
from src.utils import utcnow
from src.modules.auth.hashers import PBKDF2PasswordHasher
from src.modules.encrypt.encryption import VendorKeyEncryption
from src.settings import get_app_settings

logger = logging.getLogger(__name__)


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
            f"email='{self.email}', "
            f"is_active='{self.is_active}', "
            f"is_admin='{self.is_admin}')"
        )


time_entry_tags = sa.Table(
    "time_entry_tags",
    BaseModel.metadata,
    sa.Column("time_entry_id", sa.ForeignKey("time_entries.id"), primary_key=True),
    sa.Column("tag_id", sa.ForeignKey("tags.id"), primary_key=True),
)


class Tag(BaseModel):
    """A reusable, application-wide label for work records."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Client(BaseModel):
    """A customer that can own one or more projects."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    def __str__(self) -> str:
        return self.name


class Project(BaseModel):
    """A configurable work project, optionally associated with a client."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False, unique=True)
    client_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("clients.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    client: Mapped[Client | None] = relationship(
        Client,
        backref=backref("projects", lazy="selectin"),
        lazy="joined",
    )

    def __str__(self) -> str:
        return self.name


class TimeEntry(BaseModel):
    """A user's completed or currently running work session."""

    __tablename__ = "time_entries"
    __table_args__ = (
        sa.Index(
            "uq_time_entries_one_active_timer",
            "user_id",
            unique=True,
            postgresql_where=sa.text("ended_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("projects.id"), nullable=True, index=True
    )
    project: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    task: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    user: Mapped[User] = relationship(
        User,
        backref=backref("time_entries", cascade="all, delete-orphan"),
        lazy="joined",
    )
    project_entity: Mapped[Project | None] = relationship(
        Project,
        backref=backref("time_entries", lazy="selectin"),
        lazy="joined",
    )
    tags: Mapped[list[Tag]] = relationship(Tag, secondary=time_entry_tags, lazy="selectin")

    @property
    def is_running(self) -> bool:
        """Return whether the entry represents the user's active timer."""
        return self.ended_at is None


class Token(BaseModel):
    """Simple token storage for authorizing and API usages"""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(sa.String(128))
    token: Mapped[str] = mapped_column(sa.String(512), unique=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=True, onupdate=utcnow)

    # relations
    user: Mapped[User] = relationship(
        User,
        backref=backref("tokens", cascade="all, delete-orphan"),
        lazy="joined",
    )

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return (
            f"Token("
            f"id={self.id}, "
            f"name={self.name}, "
            f"user_id={self.user_id}, "
            f"token='[MASKED]', "
            f"expires_at={self.expires_at}, "
            f"created_at={self.created_at}, "
            f"updated_at={self.updated_at}"
            f")"
        )

    @property
    def raw_token(self) -> str | None:
        return getattr(self, "__raw_token", None)

    @raw_token.setter
    def raw_token(self, value: str) -> None:
        setattr(self, "__raw_token", value)


class Vendor(BaseModel):
    """User model representing a Telegram user in the system."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
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
        """Get decrypted API key for vendor authentication."""
        try:
            settings = get_app_settings()
            encryption = VendorKeyEncryption(settings.vendor_encryption_key)
            decrypted_key = encryption.decrypt(self.api_key)

        except (ValueError, KeyError) as exc:
            logger.error("Failed to decrypt API key for vendor %s: %s", self.slug, exc)
            raise VendorEncryptionError(
                f"Failed to decrypt API key for vendor '{self.slug}'"
            ) from exc

        return decrypted_key
