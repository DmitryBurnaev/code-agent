from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


class Vendor(Base):
    """Vendor model for storing vendor information."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auth_type: Mapped[str] = mapped_column(String(50), default="Bearer")
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    settings: Mapped[list["VendorSettings"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )


class VendorSettings(Base):
    """Vendor settings model for storing encrypted API keys and other sensitive data."""

    __tablename__ = "vendor_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"))
    encrypted_api_key: Mapped[str] = mapped_column(String(1024))  # Store encrypted API key
    public_key: Mapped[str] = mapped_column(String(1024))  # Store public key for encryption
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    vendor: Mapped["Vendor"] = relationship(back_populates="settings")
