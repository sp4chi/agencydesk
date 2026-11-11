"""Settings, read from environment variables (see .env.example).

The app refuses to start with a missing or placeholder session secret,
so a forgotten config can never ship with a guessable signing key.
"""
import os
from dataclasses import dataclass

PLACEHOLDER_SECRETS = {"", "change-me"}
MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class Settings:
    # Pool for normal requests. Must log in as agencydesk_api (RLS applies).
    api_database_url: str
    # HMAC key for session tokens.
    session_secret: str
    session_ttl_seconds: int = 12 * 60 * 60

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("SESSION_SECRET", "")
        if secret in PLACEHOLDER_SECRETS or len(secret) < MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"SESSION_SECRET must be set to a random value of at least {MIN_SECRET_LENGTH} "
                "characters (run `make env` to generate one)."
            )
        return cls(
            api_database_url=os.environ.get(
                "API_DATABASE_URL",
                "postgresql+psycopg://agencydesk_api:dev-api-password@localhost:5433/agencydesk",
            ),
            session_secret=secret,
            session_ttl_seconds=int(os.environ.get("SESSION_TTL_SECONDS", 12 * 60 * 60)),
        )
