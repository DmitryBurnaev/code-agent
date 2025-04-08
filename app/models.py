from datetime import datetime

from pydantic import BaseModel


class SystemInfo(BaseModel):
    """Response model for system information endpoint."""

    current_time: datetime
    os_version: str
    providers: list[str]


class HealthCheck(BaseModel):
    """Response model for health check endpoint."""

    status: str
    timestamp: datetime
