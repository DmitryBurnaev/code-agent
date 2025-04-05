from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    auth_api_token: str
    swagger_enabled: bool = True
    service_tokens: dict[str, str] = {}
    app_host: str = "0.0.0.0"
    app_port: int = 8003

settings = Settings()
