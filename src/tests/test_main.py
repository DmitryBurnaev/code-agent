from unittest.mock import patch, MagicMock

import pytest
from pydantic import SecretStr

from src.main import make_app, CodeAgentAPI, run_app
from src.settings import AppSettings


@pytest.fixture
def mock_settings() -> AppSettings:
    return AppSettings(
        auth_api_token=SecretStr("auth_test_token"),
        app_host="test_host",
        app_port=1234,
        docs_enabled=True,
    )


def test_make_app__custom_settings(mock_settings: AppSettings) -> None:
    app = make_app(settings=mock_settings)

    assert isinstance(app, CodeAgentAPI)
    assert app.settings == mock_settings


def test_make_app__default_settings(
    mock_settings: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_API_TOKEN", "test_token")
    app = make_app()

    assert isinstance(app, CodeAgentAPI)
    assert isinstance(app.settings, AppSettings)
    assert app.settings.auth_api_token == SecretStr("test_token")


@patch("uvicorn.run")
@patch("src.main.make_app")
def test_main_run_app(
    mock_make_app: MagicMock,
    mock_run: MagicMock,
    mock_settings: AppSettings,
) -> None:
    app = make_app(settings=mock_settings)
    mock_make_app.return_value = app

    run_app()

    mock_run.assert_called_once_with(
        app,
        host="test_host",
        port=1234,
        log_config=mock_settings.log_config,
    )
