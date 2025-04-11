from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models import SystemInfo, HealthCheck


def test_system_info_model() -> None:
    """Test SystemInfo model validation."""
    info = SystemInfo(os_version="test-os")
    assert info.status == "ok"
    assert info.os_version == "test-os"
    assert info.providers == []


def test_system_info_model_validation() -> None:
    """Test SystemInfo model validation errors."""
    with pytest.raises(ValidationError):
        SystemInfo(status="fail", os_version="test-os", providers={})


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
