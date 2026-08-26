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

    # Printed on accreditation exports. There is no institution entity in
    # the schema — the legacy system_settings table was not migrated — so
    # this is configuration rather than data.
    institution_name: str = "Your Institution"

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

    # --- College sign-in (OpenID Connect) ---------------------------------
    #
    # Left unset, SSO is off and the sign-in page does not offer it. Configured
    # by discovery URL rather than by provider name: Google Workspace and
    # Microsoft 365 are both standard OIDC and differ only in these values, so
    # the choice of provider is deployment configuration and not code.
    #
    #   Google:    https://accounts.google.com/.well-known/openid-configuration
    #   Microsoft: https://login.microsoftonline.com/<tenant>/v2.0/
    #              .well-known/openid-configuration
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None

    # Addresses outside these domains are refused even when the provider
    # authenticated them successfully. Both Google and Microsoft will happily
    # sign in a personal account against a public client; the domain check is
    # what makes this "the college's directory" rather than "anyone".
    oidc_allowed_domains: list[str] = []

    # Shown on the button. Named by the college, not by the vendor: staff
    # recognise "ESEC staff account" faster than "Microsoft".
    oidc_button_label: str = "your college account"

    @property
    def sso_enabled(self) -> bool:
        return bool(
            self.oidc_discovery_url
            and self.oidc_client_id
            and self.oidc_client_secret
            and self.oidc_allowed_domains
        )

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
