"""Let a user read their own membership row.

Revision ID: 0002_membership_read_own_row
Revises: 0001_baseline
Create Date: 2026-11-11

get_tenant_db loads the caller's membership under RLS after setting only
app.agency_id and app.user_id from the verified token. Without this branch
a client_user's own row is hidden at that point (their client_id isn't
known yet), so they could never authenticate. Mirrors db/schema.sql.
"""
from alembic import op

revision = "0002_membership_read_own_row"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY read ON agency_memberships")
    op.execute(
        """CREATE POLICY read ON agency_memberships FOR SELECT USING (
             app.is_staff() OR is_staff OR client_id = app.client_id() OR user_id = app.user_id())"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY read ON agency_memberships")
    op.execute(
        """CREATE POLICY read ON agency_memberships FOR SELECT USING (
             app.is_staff() OR is_staff OR client_id = app.client_id())"""
    )
