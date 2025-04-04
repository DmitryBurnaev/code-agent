from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='my_prefix_')
    enable_swagger: bool = Field(True)
    auth_key: str = 'xxx'  # will be read from `my_prefix_auth_key`


print(Settings().model_dump())
"""
{
    'auth_key': 'xxx',
    'api_key': 'xxx',
    'redis_dsn': RedisDsn('redis://user:pass@localhost:6379/1'),
    'pg_dsn': PostgresDsn('postgres://user:pass@localhost:5432/foobar'),
    'amqp_dsn': AmqpDsn('amqp://user:pass@localhost:5672/'),
    'special_function': math.cos,
    'domains': set(),
    'more_settings': {'foo': 'bar', 'apple': 1},
}
"""

settings = Settings()
