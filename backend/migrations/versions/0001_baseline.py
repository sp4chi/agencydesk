"""Baseline: tables, RLS policies, triggers and functions.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-11

Applies 0001_baseline.sql, a frozen copy of db/schema.sql taken when this
revision was written. It is a copy (not a read of db/schema.sql) so that
later schema edits can't silently change what revision 1 does; those
edits go in new revisions instead.
"""
import pathlib

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = pathlib.Path(__file__).with_suffix(".sql")

TABLES = [
    "invites", "task_events", "time_entries", "files", "comments", "tasks",
    "project_members", "projects", "agency_memberships", "clients", "users", "agencies",
]


def upgrade() -> None:
    # Run through the raw psycopg cursor with no parameters, so the file is
    # sent as-is: no bind-parameter parsing of ':' or '%', and multiple
    # statements (DO blocks, functions) are allowed in one call.
    cursor = op.get_bind().connection.cursor()
    cursor.execute(SQL_FILE.read_text())


def downgrade() -> None:
    # Roles (agencydesk_api, agencydesk_auth) are cluster-wide and may be
    # shared with other databases, so they are left in place.
    for table in TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
