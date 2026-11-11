"""
Shared test setup: builds the ad_test database once per run from
db/schema.sql + db/seed.sql, and gives the app's login roles their dev
passwords (db/dev_roles.sql) so the API can connect as agencydesk_api.

Connection strings default to docker-compose.yml; override with
DATABASE_URL / ADMIN_DATABASE_URL (libpq conninfo strings).
"""
import os
import pathlib

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PG = "host=localhost port=5433 user=postgres password=postgres"
ADMIN_DSN = os.environ.get("ADMIN_DATABASE_URL", f"{PG} dbname=postgres")
DSN = os.environ.get("DATABASE_URL", f"{PG} dbname=ad_test")

# The test-only session secret. Real ones come from .env (`make env`).
os.environ.setdefault("SESSION_SECRET", "test-secret-" + "x" * 40)


def api_database_url() -> str:
    """SQLAlchemy URL for the test DB, logged in as agencydesk_api."""
    parts = psycopg.conninfo.conninfo_to_dict(DSN)
    host, port = parts.get("host", "localhost"), parts.get("port", "5432")
    return f"postgresql+psycopg://agencydesk_api:dev-api-password@{host}:{port}/{parts['dbname']}"


@pytest.fixture(scope="session", autouse=True)
def database():
    dbname = psycopg.conninfo.conninfo_to_dict(DSN)["dbname"]
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{dbname}"')
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute((ROOT / "db/schema.sql").read_text())
        c.execute((ROOT / "db/dev_roles.sql").read_text())
        # seed.sql uses a psql variable; substitute it for the driver
        seed = (ROOT / "db/seed.sql").read_text()
        seed = "\n".join(l for l in seed.splitlines() if not l.startswith("\\set"))
        c.execute(seed.replace(":pw", "'x'"))
    yield
