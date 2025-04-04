from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings which are loaded from environment variables"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    auth_api_token: str
    swagger_enabled: bool = True
    service_tokens: dict[str, str] = {}


settings = Settings()
