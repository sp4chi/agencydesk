"""
Database-level proof that tenant isolation and client visibility hold.

These tests talk to Postgres directly as the `agencydesk_api` role, the
same role the FastAPI app uses, with the same per-request context. If a
rule holds here, no API endpoint can break it by forgetting a WHERE.

Run:  make test   (defaults match docker-compose.yml; override with
      DATABASE_URL / ADMIN_DATABASE_URL as libpq conninfo strings)
"""
import os
import hashlib
import pathlib
import threading
import uuid

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PG = "host=localhost port=5433 user=postgres password=postgres"
ADMIN_DSN = os.environ.get("ADMIN_DATABASE_URL", f"{PG} dbname=postgres")
DSN = os.environ.get("DATABASE_URL", f"{PG} dbname=ad_test")

PIXEL = "aaaaaaaa-0000-0000-0000-000000000001"
NORTHWIND = "bbbbbbbb-0000-0000-0000-000000000001"
ACME = "aaaaaaaa-0000-0000-0001-000000000001"
ACME_PROJECT = "aaaaaaaa-0000-0000-0002-000000000001"
GLOBEX_PROJECT = "aaaaaaaa-0000-0000-0002-000000000002"
TASK_MOCKUPS = "aaaaaaaa-0000-0000-0003-000000000001"     # client-visible
TASK_BUDGET = "aaaaaaaa-0000-0000-0003-000000000002"      # internal
TASK_NW_SECRET = "bbbbbbbb-0000-0000-0003-000000000001"   # other tenant
FILE_CLIENT = "aaaaaaaa-0000-0000-0004-000000000001"
FILE_INTERNAL = "aaaaaaaa-0000-0000-0004-000000000002"
NINA = "00000000-0000-0000-0000-0000000000a3"


# ---------------------------------------------------------------- fixtures
# The ad_test database itself is built once per run in tests/conftest.py.


@pytest.fixture
def conn():
    """One transaction per test, always rolled back."""
    with psycopg.connect(DSN) as c:
        yield c
        c.rollback()


def act_as(conn, email, agency_id):
    """Mimic the API's per-request setup: load the membership as a trusted
    lookup, then drop to the RLS-enforced role and set the context."""
    conn.execute("RESET ROLE")
    row = conn.execute(
        """SELECT u.id, m.role, m.client_id FROM users u
           JOIN agency_memberships m ON m.user_id = u.id
           WHERE u.email = %s AND m.agency_id = %s AND m.removed_at IS NULL""",
        (email, agency_id),
    ).fetchone()
    assert row, f"{email} has no active membership in {agency_id}"
    user_id, role, client_id = row
    conn.execute("SET LOCAL ROLE agencydesk_api")
    for key, val in [("agency_id", agency_id), ("user_id", user_id),
                     ("role", role), ("client_id", client_id or "")]:
        conn.execute("SELECT set_config(%s, %s, true)", (f"app.{key}", str(val)))


def ids(conn, sql, *args):
    return {str(r[0]) for r in conn.execute(sql, args).fetchall()}


# ---------------------------------------------------- 1. cross-tenant access
def test_other_tenant_rows_are_invisible_even_by_id(conn):
    act_as(conn, "bob@northwind.test", NORTHWIND)
    assert ids(conn, "SELECT id FROM tasks") == {TASK_NW_SECRET}
    assert ids(conn, "SELECT id FROM tasks WHERE id = %s", TASK_MOCKUPS) == set()
    assert ids(conn, "SELECT id FROM projects WHERE id = %s", ACME_PROJECT) == set()
    assert ids(conn, "SELECT id FROM comments") == set()
    assert ids(conn, "SELECT id FROM files WHERE id = %s", FILE_CLIENT) == set()
    assert ids(conn, "SELECT user_id FROM agency_memberships WHERE agency_id = %s", PIXEL) == set()


def test_other_tenant_rows_cannot_be_written(conn):
    act_as(conn, "bob@northwind.test", NORTHWIND)
    cur = conn.execute("UPDATE tasks SET title = 'pwned' WHERE id = %s", (TASK_MOCKUPS,))
    assert cur.rowcount == 0
    cur = conn.execute("DELETE FROM comments WHERE task_id = %s", (TASK_MOCKUPS,))
    assert cur.rowcount == 0


def test_cannot_insert_into_other_tenant_by_claiming_its_agency_id(conn):
    act_as(conn, "bob@northwind.test", NORTHWIND)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):   # RLS WITH CHECK
        conn.execute("""INSERT INTO tasks (agency_id, project_id, title, created_by)
                        VALUES (%s, %s, 'x', '00000000-0000-0000-0000-0000000000b1')""",
                     (PIXEL, ACME_PROJECT))


def test_composite_fk_blocks_cross_tenant_reference_even_without_rls(conn):
    # As the table owner (RLS bypassed), the schema itself still refuses a
    # Northwind task that points at a Pixel project.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("""INSERT INTO tasks (agency_id, project_id, title, created_by)
                        VALUES (%s, %s, 'x', '00000000-0000-0000-0000-0000000000b1')""",
                     (NORTHWIND, ACME_PROJECT))


# ------------------------------------------- 2. internal content vs clients
def test_client_sees_only_own_client_visible_tasks(conn):
    act_as(conn, "ravi@acme.test", PIXEL)
    assert ids(conn, "SELECT id FROM tasks") == {
        TASK_MOCKUPS, "aaaaaaaa-0000-0000-0003-000000000003"}
    assert ids(conn, "SELECT id FROM projects") == {ACME_PROJECT}   # not Globex


def test_search_and_filters_do_not_leak_internal_tasks(conn):
    act_as(conn, "ravi@acme.test", PIXEL)
    assert ids(conn, "SELECT id FROM tasks WHERE title ILIKE %s", "%budget%") == set()
    assert ids(conn, "SELECT id FROM tasks WHERE status = 'in_progress'") == set()
    assert ids(conn, "SELECT id FROM tasks WHERE id = %s", TASK_BUDGET) == set()


def test_client_sees_only_client_visible_comments_and_files(conn):
    act_as(conn, "ravi@acme.test", PIXEL)
    bodies = {r[0] for r in conn.execute("SELECT body FROM comments").fetchall()}
    assert bodies == {"v2 uploaded, please review"}
    assert ids(conn, "SELECT id FROM files") == {FILE_CLIENT}
    assert ids(conn, "SELECT id FROM time_entries") == set()   # raw entries are staff-only


def test_flipping_task_to_internal_hides_its_comments_and_files(conn):
    act_as(conn, "alice@pixel.test", PIXEL)
    conn.execute("UPDATE tasks SET visibility = 'internal' WHERE id = %s", (TASK_MOCKUPS,))
    act_as(conn, "ravi@acme.test", PIXEL)
    assert conn.execute("SELECT count(*) FROM comments").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM files").fetchone()[0] == 0


def test_dashboard_is_scoped_to_viewer(conn):
    sql = "SELECT status, count(*) FROM tasks WHERE project_id = %s GROUP BY status"
    act_as(conn, "alice@pixel.test", PIXEL)
    staff = dict(conn.execute(sql, (ACME_PROJECT,)).fetchall())
    staff_hours = conn.execute("SELECT app.project_hours(%s)", (ACME_PROJECT,)).fetchone()[0]
    act_as(conn, "ravi@acme.test", PIXEL)
    client = dict(conn.execute(sql, (ACME_PROJECT,)).fetchall())
    client_hours = conn.execute("SELECT app.project_hours(%s)", (ACME_PROJECT,)).fetchone()[0]
    assert staff == {"in_review": 1, "in_progress": 1, "todo": 1}
    assert client == {"in_review": 1, "todo": 1}
    assert float(staff_hours) == 5.0 and float(client_hours) == 3.0
    assert conn.execute("SELECT app.project_hours(%s)", (GLOBEX_PROJECT,)).fetchone()[0] is None


def test_client_cannot_create_tasks_or_change_status(conn):
    act_as(conn, "ravi@acme.test", PIXEL)
    assert conn.execute("UPDATE tasks SET status = 'done' WHERE id = %s",
                        (TASK_MOCKUPS,)).rowcount == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("""INSERT INTO tasks (agency_id, project_id, title, visibility, created_by)
                        VALUES (%s, %s, 'x', 'client', '00000000-0000-0000-0000-0000000000c1')""",
                     (PIXEL, ACME_PROJECT))


def test_client_can_comment_only_publicly_on_visible_tasks(conn):
    act_as(conn, "ravi@acme.test", PIXEL)
    me = "00000000-0000-0000-0000-0000000000c1"
    conn.execute("""INSERT INTO comments (agency_id, task_id, author_user_id, body, visibility)
                    VALUES (%s, %s, %s, 'looks good', 'client')""", (PIXEL, TASK_MOCKUPS, me))
    conn.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("""INSERT INTO comments (agency_id, task_id, author_user_id, body, visibility)
                        VALUES (%s, %s, %s, 'hi', 'client')""", (PIXEL, TASK_BUDGET, me))
    conn.execute("ROLLBACK TO SAVEPOINT s")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("""INSERT INTO comments (agency_id, task_id, author_user_id, body, visibility)
                        VALUES (%s, %s, %s, 'hi', 'internal')""", (PIXEL, TASK_MOCKUPS, me))


def test_client_file_approval(conn):
    act_as(conn, "ravi@acme.test", PIXEL)
    me = "00000000-0000-0000-0000-0000000000c1"
    cur = conn.execute("""UPDATE files SET approval_status = 'approved', reviewed_by = %s
                          WHERE id = %s""", (me, FILE_CLIENT))
    assert cur.rowcount == 1
    # internal file: invisible, so nothing to update
    assert conn.execute("""UPDATE files SET approval_status = 'approved', reviewed_by = %s
                           WHERE id = %s""", (me, FILE_INTERNAL)).rowcount == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("UPDATE files SET filename = 'evil.exe' WHERE id = %s", (FILE_CLIENT,))


# ----------------------------------------------------------- roles scoping
def test_member_sees_only_assigned_projects(conn):
    act_as(conn, "mark@pixel.test", PIXEL)
    assert ids(conn, "SELECT id FROM projects") == {ACME_PROJECT}
    assert TASK_BUDGET in ids(conn, "SELECT id FROM tasks")      # staff see internal
    assert "aaaaaaaa-0000-0000-0003-000000000004" not in ids(conn, "SELECT id FROM tasks")
    act_as(conn, "alice@pixel.test", PIXEL)
    assert ids(conn, "SELECT id FROM projects") == {ACME_PROJECT, GLOBEX_PROJECT}


# --------------------------------------------- 3. one person, two agencies
def test_same_person_two_agencies_is_one_user_with_two_scoped_roles(conn):
    assert conn.execute("SELECT count(*) FROM users WHERE email = 'ravi@acme.test'").fetchone()[0] == 1
    act_as(conn, "ravi@acme.test", PIXEL)
    pixel_view = ids(conn, "SELECT id FROM tasks")
    act_as(conn, "ravi@acme.test", NORTHWIND)
    nw_view = ids(conn, "SELECT id FROM tasks")
    assert pixel_view and not (pixel_view & nw_view)
    assert TASK_NW_SECRET not in nw_view           # internal there too


# -------------------------------------------------------- 4. invite races
def _invite(conn, email, token):
    return conn.execute(
        """INSERT INTO invites (agency_id, email, role, client_id, token_hash, invited_by, expires_at)
           VALUES (%s, %s, 'client_user', %s, %s, '00000000-0000-0000-0000-0000000000a1',
                   now() + interval '7 days')
           ON CONFLICT (agency_id, email) WHERE status = 'pending'
           DO UPDATE SET token_hash = EXCLUDED.token_hash,
                         expires_at = EXCLUDED.expires_at,
                         send_count = invites.send_count + 1
           RETURNING id, send_count""",
        (PIXEL, email, ACME, hashlib.sha256(token.encode()).hexdigest())).fetchone()


def test_resending_invite_reuses_the_row_and_kills_old_token(conn):
    act_as(conn, "alice@pixel.test", PIXEL)
    first = _invite(conn, "new@acme.test", "tok-1")
    second = _invite(conn, "new@acme.test", "tok-2")
    assert first[0] == second[0] and second[1] == 2
    assert conn.execute("SELECT count(*) FROM invites WHERE email = 'new@acme.test'").fetchone()[0] == 1
    old = hashlib.sha256(b"tok-1").hexdigest()
    assert conn.execute("SELECT count(*) FROM invites WHERE token_hash = %s", (old,)).fetchone()[0] == 0


def test_concurrent_double_accept_creates_exactly_one_account():
    email, token = f"race-{uuid.uuid4().hex[:6]}@acme.test", uuid.uuid4().hex
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("BEGIN")
        act_as(c, "alice@pixel.test", PIXEL)
        _invite(c, email, token)
        c.execute("COMMIT")

    results, barrier = [], threading.Barrier(2)

    def accept():
        with psycopg.connect(DSN) as c:
            c.execute("SET ROLE agencydesk_auth")
            barrier.wait()
            try:
                c.execute("SELECT * FROM app.accept_invite(%s, 'Racer', 'x')",
                          (hashlib.sha256(token.encode()).hexdigest(),))
                c.commit()
                results.append("ok")
            except psycopg.errors.NoDataFound:
                c.rollback()
                results.append("rejected")

    threads = [threading.Thread(target=accept) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "rejected"]
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM users WHERE email = %s", (email,)).fetchone()[0] == 1


def test_accepting_invite_as_existing_user_adds_membership_not_account(conn):
    # Mark (Pixel staff) gets invited as a client contact at Northwind.
    conn.execute("""INSERT INTO invites (agency_id, email, role, client_id, token_hash, invited_by, expires_at)
                    VALUES (%s, 'mark@pixel.test', 'client_user', 'bbbbbbbb-0000-0000-0001-000000000001',
                            'h-mark', '00000000-0000-0000-0000-0000000000b1', now() + interval '1 day')""",
                 (NORTHWIND,))
    conn.execute("SET LOCAL ROLE agencydesk_auth")
    conn.execute("SELECT * FROM app.accept_invite('h-mark', 'ignored', 'ignored')")
    conn.execute("RESET ROLE")
    assert conn.execute("SELECT count(*) FROM users WHERE email = 'mark@pixel.test'").fetchone()[0] == 1
    roles = dict(conn.execute("""SELECT agency_id::text, role FROM agency_memberships
                                 WHERE user_id = '00000000-0000-0000-0000-0000000000a2'""").fetchall())
    assert roles == {PIXEL: "agency_member", NORTHWIND: "client_user"}


# ------------------------------------- 5. removing a member mid-task
def test_removing_member_unassigns_tasks_logs_it_and_keeps_time(conn):
    act_as(conn, "alice@pixel.test", PIXEL)
    conn.execute("DELETE FROM project_members WHERE project_id = %s AND user_id = %s",
                 (ACME_PROJECT, NINA))
    assert conn.execute("SELECT count(*) FROM tasks WHERE assignee_user_id = %s",
                        (NINA,)).fetchone()[0] == 0
    # task status untouched, event recorded with the admin as actor
    assert conn.execute("SELECT status FROM tasks WHERE id = %s", (TASK_BUDGET,)).fetchone()[0] == "in_progress"
    kinds = {r[0] for r in conn.execute(
        "SELECT kind FROM task_events WHERE payload->>'from' = %s", (NINA,)).fetchall()}
    assert kinds == {"auto_unassigned_member_removed"}
    assert conn.execute("SELECT count(*) FROM time_entries WHERE user_id = %s",
                        (NINA,)).fetchone()[0] == 1


def test_cannot_assign_task_to_someone_not_on_the_project(conn):
    act_as(conn, "alice@pixel.test", PIXEL)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("UPDATE tasks SET assignee_user_id = '00000000-0000-0000-0000-0000000000a1' WHERE id = %s",
                     (TASK_MOCKUPS,))   # Alice is admin but not a member of this project


# --------------------------------------------- guard against future tables
def test_every_table_with_agency_id_has_rls_and_a_tenant_policy(conn):
    missing = conn.execute("""
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'agency_id'
        WHERE c.relkind = 'r'
          AND (NOT c.relrowsecurity OR NOT EXISTS (
                SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid
                  AND p.polname = 'tenant' AND NOT p.polpermissive))""").fetchall()
    assert missing == [], f"tables without tenant RLS: {missing}"
