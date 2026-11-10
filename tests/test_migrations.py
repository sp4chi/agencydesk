"""
Migrations and db/schema.sql must describe the same database.

AGENTS.md requires every schema change to edit db/schema.sql *and* add an
Alembic revision. This test builds one database each way and compares a
catalog fingerprint (columns, constraints, indexes, RLS, policies,
functions, triggers, grants). If someone edits only one side, it fails.
"""
import os
import pathlib

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

ROOT = pathlib.Path(__file__).resolve().parent.parent
PG = "host=localhost port=5433 user=postgres password=postgres"
ADMIN_DSN = os.environ.get("ADMIN_DATABASE_URL", f"{PG} dbname=postgres")
BASE = psycopg.conninfo.conninfo_to_dict(os.environ.get("DATABASE_URL", f"{PG} dbname=ad_test"))

FINGERPRINT_QUERIES = {
    "columns": """
        SELECT table_schema, table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns WHERE table_schema IN ('public', 'app')
          AND table_name <> 'alembic_version'""",
    "constraints": """
        SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
        FROM pg_constraint WHERE connamespace IN ('public'::regnamespace, 'app'::regnamespace)
          AND conrelid::regclass::text <> 'alembic_version'""",
    "indexes": """
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND tablename <> 'alembic_version'""",
    "rls": """
        SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
        WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
          AND relname <> 'alembic_version'""",
    "policies": """
        SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check
        FROM pg_policies WHERE schemaname = 'public'""",
    "functions": """
        SELECT p.proname, pg_get_functiondef(p.oid), p.prosecdef, p.proconfig::text
        FROM pg_proc p WHERE p.pronamespace = 'app'::regnamespace""",
    "triggers": "SELECT tgname, pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal",
    "table_grants": """
        SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
        WHERE grantee LIKE 'agencydesk_%'""",
    "column_grants": """
        SELECT grantee, table_name, column_name, privilege_type
        FROM information_schema.column_privileges WHERE grantee LIKE 'agencydesk_%'""",
    "routine_grants": """
        SELECT grantee, routine_name, privilege_type FROM information_schema.routine_privileges
        WHERE grantee LIKE 'agencydesk_%'""",
}


def dsn(dbname: str) -> str:
    return psycopg.conninfo.make_conninfo(**{**BASE, "dbname": dbname})


def fresh_db(dbname: str) -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{dbname}"')


def drop_db(dbname: str) -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')


def alembic(dbname: str, action: str, target: str) -> None:
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(dsn(dbname)))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        getattr(command, action)(cfg, target)
    engine.dispose()


def fingerprint(dbname: str) -> dict[str, set[tuple]]:
    with psycopg.connect(dsn(dbname)) as c:
        return {name: set(c.execute(sql).fetchall()) for name, sql in FINGERPRINT_QUERIES.items()}


@pytest.fixture(scope="module")
def db_names():
    from_schema, from_alembic = f"{BASE['dbname']}_schema", f"{BASE['dbname']}_alembic"
    fresh_db(from_schema)
    fresh_db(from_alembic)
    with psycopg.connect(dsn(from_schema), autocommit=True) as c:
        c.execute((ROOT / "db/schema.sql").read_text())
    yield from_schema, from_alembic
    drop_db(from_schema)
    drop_db(from_alembic)


def test_alembic_head_matches_schema_sql(db_names):
    from_schema, from_alembic = db_names
    alembic(from_alembic, "upgrade", "head")
    expected, actual = fingerprint(from_schema), fingerprint(from_alembic)
    for name in FINGERPRINT_QUERIES:
        assert actual[name] == expected[name], (
            f"{name} differs between `alembic upgrade head` and db/schema.sql.\n"
            f"only in schema.sql: {sorted(expected[name] - actual[name])[:5]}\n"
            f"only in migrations: {sorted(actual[name] - expected[name])[:5]}"
        )


def test_downgrade_to_base_then_upgrade_again(db_names):
    _, from_alembic = db_names
    alembic(from_alembic, "upgrade", "head")
    alembic(from_alembic, "downgrade", "base")
    with psycopg.connect(dsn(from_alembic)) as c:
        leftover = c.execute(
            """SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace
               AND relkind = 'r' AND relname <> 'alembic_version'"""
        ).fetchall()
        assert leftover == []
    alembic(from_alembic, "upgrade", "head")
