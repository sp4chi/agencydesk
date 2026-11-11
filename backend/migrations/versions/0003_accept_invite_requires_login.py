"""accept_invite: an existing account can only be attached by its owner.

Revision ID: 0003_accept_invite_login
Revises: 0002_membership_read_own_row
Create Date: 2026-11-11

Adds p_acting_user to app.accept_invite. If the invited email already has
an account, the caller must be logged in as it; otherwise a name and
password are required to create one. Mirrors db/schema.sql.

The function bodies live in frozen .up.sql / .down.sql files next to this
one (copied from db/schema.sql and 0001_baseline.sql), because the drift
test compares function source byte for byte.
"""
import pathlib

from alembic import op

revision = "0003_accept_invite_login"
down_revision = "0002_membership_read_own_row"
branch_labels = None
depends_on = None

HERE = pathlib.Path(__file__).parent
NEW_SIG = "app.accept_invite(text, uuid, text, text)"
OLD_SIG = "app.accept_invite(text, text, text)"


def _run_sql_file(name: str) -> None:
    # Raw cursor, no parameters: the file is sent as-is ($$ bodies, ':' etc.).
    op.get_bind().connection.cursor().execute((HERE / name).read_text())


def upgrade() -> None:
    op.execute(f"DROP FUNCTION {OLD_SIG}")
    _run_sql_file("0003_accept_invite_requires_login.up.sql")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {NEW_SIG} FROM PUBLIC, agencydesk_api")
    op.execute(f"GRANT EXECUTE ON FUNCTION {NEW_SIG} TO agencydesk_auth")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {NEW_SIG}")
    _run_sql_file("0003_accept_invite_requires_login.down.sql")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {OLD_SIG} FROM PUBLIC, agencydesk_api")
    op.execute(f"GRANT EXECUTE ON FUNCTION {OLD_SIG} TO agencydesk_auth")
