from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration is environment-only.

    The app this replaces kept database credentials in a committed file. There
    is deliberately no default for `database_url` — the app refuses to start
    rather than falling back to something that happens to work locally.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    database_url: str

    # Signing key for session tokens. Must be overridden outside local use;
    # startup validation in main.py enforces that.
    secret_key: str = "insecure-local-only-key"
    access_token_ttl_minutes: int = 60 * 8

    # Origins allowed to call the API with credentials. The React dev server
    # by default; the real origin is set per environment.
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
