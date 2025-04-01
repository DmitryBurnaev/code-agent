from datetime import datetime
import os
import platform
from typing import Dict

from fastapi import FastAPI, HTTPException, Depends
from pydantic_settings import BaseSettings
from pydantic import BaseModel


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    API_TOKEN: str
    SERVICE_TOKENS: Dict[str, str]
    ENABLE_SWAGGER: bool = False

    class Config:
        env_file = ".env"


class SystemInfo(BaseModel):
    """Response model for system information endpoint."""
    current_time: datetime
    os_version: str


class HealthCheck(BaseModel):
    """Response model for health check endpoint."""
    status: str
    timestamp: datetime


settings = Settings()
app = FastAPI(
    title="System Info API",
    description="API for retrieving system information",
    docs_url="/docs" if settings.ENABLE_SWAGGER else None,
    redoc_url="/redoc" if settings.ENABLE_SWAGGER else None,
)


def verify_token(token: str) -> bool:
    """Verify the API token."""
    return token == settings.API_TOKEN


async def get_token(authorization: str = Depends(lambda x: x.headers.get("Authorization", ""))) -> str:
    """Dependency for token verification."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ")[1]
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return token


@app.get("/system-info", response_model=SystemInfo)
async def get_system_info(_: str = Depends(get_token)) -> SystemInfo:
    """Get current system information."""
    return SystemInfo(
        current_time=datetime.now(),
        os_version=platform.platform(),
    )


@app.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now(),
    ) 