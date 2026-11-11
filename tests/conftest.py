"""
Shared test setup: builds the ad_test database once per run from
db/schema.sql + db/seed.sql, and gives the app's login roles their dev
passwords (db/dev_roles.sql) so the API can connect as agencydesk_api.

Connection strings default to docker-compose.yml; override with
DATABASE_URL / ADMIN_DATABASE_URL (libpq conninfo strings).
"""
import os
import pathlib
import re

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PG = "host=localhost port=5433 user=postgres password=postgres"
ADMIN_DSN = os.environ.get("ADMIN_DATABASE_URL", f"{PG} dbname=postgres")
DSN = os.environ.get("DATABASE_URL", f"{PG} dbname=ad_test")

# The test-only session secret. Real ones come from .env (`make env`).
os.environ.setdefault("SESSION_SECRET", "test-secret-" + "x" * 40)


def _test_db_url(role: str, password: str) -> str:
    parts = psycopg.conninfo.conninfo_to_dict(DSN)
    host, port = parts.get("host", "localhost"), parts.get("port", "5432")
    return f"postgresql+psycopg://{role}:{password}@{host}:{port}/{parts['dbname']}"


def api_database_url() -> str:
    """SQLAlchemy URL for the test DB, logged in as agencydesk_api (RLS applies)."""
    return _test_db_url("agencydesk_api", "dev-api-password")


def auth_database_url() -> str:
    """SQLAlchemy URL for the test DB, logged in as agencydesk_auth (login only)."""
    return _test_db_url("agencydesk_auth", "dev-auth-password")


@pytest.fixture(scope="session", autouse=True)
def database():
    dbname = psycopg.conninfo.conninfo_to_dict(DSN)["dbname"]
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{dbname}"')
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute((ROOT / "db/schema.sql").read_text())
        c.execute((ROOT / "db/dev_roles.sql").read_text())
        c.execute(seed_sql_for_driver())
    yield


def seed_sql_for_driver() -> str:
    """seed.sql uses a psql variable (`\\set pw '''<hash>'''` ... `:pw`).
    psycopg doesn't understand psql meta-commands, so substitute it here,
    keeping the real bcrypt hash so seeded users can log in."""
    seed = (ROOT / "db/seed.sql").read_text()
    match = re.search(r"^\\set pw '''(.+)'''$", seed, flags=re.MULTILINE)
    assert match, "db/seed.sql must define the password hash with \\set pw"
    seed = seed.replace(match.group(0), "")
    return seed.replace(":pw", f"'{match.group(1)}'")
