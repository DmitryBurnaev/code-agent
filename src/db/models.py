from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from src.constants import VendorAuthType, VENDOR_DEFAULT_TIMEOUT
from src.utils import utcnow


class BaseModel(AsyncAttrs, DeclarativeBase):
    id: Mapped[int]


class Vendor(BaseModel):
    """User model representing a Telegram user in the system."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(255))
    url: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    auth_type: Mapped[str] = mapped_column(sa.String(50), default=VendorAuthType.BEARER)
    timeout: Mapped[int] = mapped_column(sa.Integer, default=VENDOR_DEFAULT_TIMEOUT)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, onupdate=utcnow)

    # Relationships
    settings: Mapped[list["VendorSettings"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"Vendor #{self.id} {self.name} "

    def __repr__(self) -> str:
        return f"Vendor(id={self.id!r}, name={self.name!r}, url={self.url!r})"


class VendorSettings(BaseModel):
    """Vendor settings model for storing encrypted API keys and other sensitive data."""

    __tablename__ = "vendor_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(sa.ForeignKey("vendors.id", ondelete="CASCADE"))
    api_key: Mapped[str] = mapped_column(sa.String(1024))  # Store an encrypted API key
    public_key: Mapped[str] = mapped_column(sa.String(1024))  # Store a public key for encryption
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, onupdate=utcnow)

    # Relationships
    vendor: Mapped["Vendor"] = relationship(back_populates="settings")

    def __repr__(self) -> str:
        return f"VendorSettings(id={self.id!r})"
