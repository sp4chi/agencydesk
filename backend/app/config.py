"""Settings, read from environment variables (see .env.example).

The app refuses to start with a missing or placeholder session secret,
so a forgotten config can never ship with a guessable signing key.
"""
import os
import pathlib
from dataclasses import dataclass

PLACEHOLDER_SECRETS = {"", "change-me"}
MIN_SECRET_LENGTH = 32
# <repo>/uploads (gitignored). Never served directly; see app/services/storage.py.
DEFAULT_UPLOAD_DIR = pathlib.Path(__file__).resolve().parents[2] / "uploads"


@dataclass(frozen=True)
class Settings:
    # Pool for normal requests. Must log in as agencydesk_api (RLS applies).
    api_database_url: str
    # Pool for login / agency selection / invite acceptance only (agencydesk_auth).
    auth_database_url: str
    # HMAC key for identity and session tokens.
    session_secret: str
    session_ttl_seconds: int = 12 * 60 * 60
    invite_ttl_days: int = 7
    # Frontend origin, used to build invite links handed to the admin.
    app_base_url: str = "http://localhost:5173"
    upload_dir: pathlib.Path = DEFAULT_UPLOAD_DIR
    max_upload_bytes: int = 25 * 1024 * 1024

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
            auth_database_url=os.environ.get(
                "AUTH_DATABASE_URL",
                "postgresql+psycopg://agencydesk_auth:dev-auth-password@localhost:5433/agencydesk",
            ),
            session_secret=secret,
            session_ttl_seconds=int(os.environ.get("SESSION_TTL_SECONDS", 12 * 60 * 60)),
            invite_ttl_days=int(os.environ.get("INVITE_TTL_DAYS", 7)),
            app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/"),
            upload_dir=pathlib.Path(os.environ.get("UPLOAD_DIR", DEFAULT_UPLOAD_DIR)),
            max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", 25 * 1024 * 1024)),
        )
