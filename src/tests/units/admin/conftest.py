from typing import Generator, Any
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def mock_super_model_view_insert() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.models.ModelView.insert_model") as mock_super:
        yield mock_super


@pytest.fixture
def mock_super_model_view_update() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.models.ModelView.update_model") as mock_super:
        yield mock_super


@pytest.fixture
def mock_super_model_view_get_details() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.models.ModelView.get_object_for_details") as mock_super:
        yield mock_super


@pytest.fixture
def mock_super_model_url_build_for() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.models.ModelView._build_url_for") as mock_build_url_for:
        yield mock_build_url_for
