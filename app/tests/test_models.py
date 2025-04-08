from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import SystemInfo, HealthCheck


def test_system_info_model() -> None:
    """Test SystemInfo model validation."""
    now = datetime.now()
    info = SystemInfo(current_time=now, os_version="test-os")
    assert info.current_time == now
    assert info.os_version == "test-os"


def test_system_info_model_validation() -> None:
    """Test SystemInfo model validation errors."""
    with pytest.raises(ValidationError):
        SystemInfo(current_time="invalid-date", os_version="test-os")


def test_health_check_model() -> None:
    """Test HealthCheck model validation."""
    now = datetime.now()
    health = HealthCheck(status="healthy", timestamp=now)
    assert health.status == "healthy"
    assert health.timestamp == now


def test_health_check_model_validation() -> None:
    """Test HealthCheck model validation errors."""
    with pytest.raises(ValidationError):
        HealthCheck(status="healthy", timestamp="invalid-date")
