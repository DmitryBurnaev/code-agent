from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    API_TOKEN: str
    SERVICE_TOKENS: dict[str, str]
    ENABLE_SWAGGER: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
