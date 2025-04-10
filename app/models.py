from datetime import datetime

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    """Response model for system information endpoint."""

    status: str = "ok"
    os_version: str
    providers: list[str] = Field(default_factory=list)


class HealthCheck(BaseModel):
    """Response model for health check endpoint."""

    status: str
    timestamp: datetime
