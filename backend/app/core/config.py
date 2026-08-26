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

    # Where the app is served from. Used to build the links in emails, so it
    # must be the address a recipient can actually open — not the API's.
    app_base_url: str = "http://localhost:5173"

    # "console" prints to the log and sends nothing, which is the right default:
    # a misconfigured deployment should fail to deliver visibly rather than mail
    # real students by accident. "memory" is for tests. "smtp" actually sends.
    email_backend: Literal["console", "memory", "smtp"] = "console"
    email_from: str = "Faculty Evaluation <no-reply@example.edu>"
    email_reply_to: str | None = None

    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_timeout: int = 15

    # How long a link stays good. A reset is short because it is a live
    # credential; an invitation is long because it is sent in bulk and people
    # open it when they get round to it.
    password_reset_ttl_minutes: int = 60
    invitation_ttl_hours: int = 24 * 7

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
