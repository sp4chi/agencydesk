"""Alembic environment.

Migrations run as the table owner (never as agencydesk_api), using
MIGRATION_DATABASE_URL. Tests can instead hand in an open connection via
`config.attributes["connection"]`.

There is no ORM metadata: the schema is hand-written SQL, so autogenerate
is intentionally not supported.
"""
import os

from alembic import context
from sqlalchemy import Connection, create_engine

DEFAULT_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/agencydesk"


def run_with(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    passed_in: Connection | None = context.config.attributes.get("connection")
    if passed_in is not None:
        run_with(passed_in)
        return
    engine = create_engine(os.environ.get("MIGRATION_DATABASE_URL", DEFAULT_URL))
    with engine.connect() as connection:
        run_with(connection)
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) mode is not supported; run against a database.")
run_migrations_online()
