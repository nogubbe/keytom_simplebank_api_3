"""Application configuration, sourced from the environment via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    secret_key: str
    debug: bool = False
    allowed_hosts: Annotated[list[str], NoDecode] = []
    database_url: PostgresDsn
    secure_ssl_redirect: bool = True
    secure_hsts_seconds: int = 60 * 60 * 24 * 30

    @field_validator('allowed_hosts', mode='before')
    @classmethod
    def split_allowed_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [host.strip() for host in value.split(',') if host.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
