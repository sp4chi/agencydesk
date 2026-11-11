"""
API-level tests against a real Postgres (no mocks), through FastAPI's TestClient.

Step 5 covers get_tenant_db: token checks, membership re-load, the RLS
context it sets, and the guarantee that a pooled connection never carries
one request's identity into the next.

Step 6 covers login (staff and portal), agency selection and GET /me.

Step 7 covers invites: create, resend, revoke, accept.
"""
import pathlib
import threading
import uuid

import psycopg
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth.tokens import issue_session_token
from app.config import Settings
from app.db import TenantDb, get_tenant_db
from app.main import create_app
from conftest import DSN, api_database_url, auth_database_url, build_test_database

PIXEL = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
NORTHWIND = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
ALICE = uuid.UUID("00000000-0000-0000-0000-0000000000a1")   # Pixel admin
BOB = uuid.UUID("00000000-0000-0000-0000-0000000000b1")     # Northwind admin
RAVI = uuid.UUID("00000000-0000-0000-0000-0000000000c1")    # client_user at both
ACME = "aaaaaaaa-0000-0000-0001-000000000001"
INITECH = "bbbbbbbb-0000-0000-0001-000000000001"
TASK_NW_SECRET = "bbbbbbbb-0000-0000-0003-000000000001"

SECRET = "api-test-secret-" + "y" * 40


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module", autouse=True)
def restore_seed_afterwards():
    # These tests go through the real API, so their writes are committed.
    # Rebuild the database afterwards so other test modules see the plain seed.
    yield
    build_test_database()


@pytest.fixture(scope="module")
def app() -> FastAPI:
    settings = Settings(
        api_database_url=api_database_url(),
        auth_database_url=auth_database_url(),
        session_secret=SECRET,
    )
    app = create_app(settings)
    # One pooled connection, so consecutive requests provably reuse it.
    app.state.api_engine.dispose()
    app.state.api_engine = create_engine(settings.api_database_url, pool_size=1, max_overflow=0)

    # Test-only routes that expose what get_tenant_db set up.
    @app.get("/_test/context")
    def context(db: TenantDb = Depends(get_tenant_db)) -> dict:
        row = db.conn.execute(text(
            """SELECT current_user,
                      current_setting('app.agency_id', true) AS agency_id,
                      current_setting('app.user_id', true)   AS user_id,
                      current_setting('app.role', true)      AS role,
                      current_setting('app.client_id', true) AS client_id"""
        )).one()
        return {**row._asdict(), "dep_role": db.role, "dep_client_id": str(db.client_id or "")}

    @app.get("/_test/tasks")
    def tasks(db: TenantDb = Depends(get_tenant_db)) -> list[str]:
        # Deliberately no WHERE agency_id: RLS alone must scope this.
        return [str(r[0]) for r in db.conn.execute(text("SELECT id FROM tasks"))]

    @app.get("/_test/boom")
    def boom(db: TenantDb = Depends(get_tenant_db)) -> None:
        raise RuntimeError("route failed mid-transaction")

    @app.post("/_test/write-invite-skipping-service")
    def write_invite(db: TenantDb = Depends(get_tenant_db)) -> None:
        # Simulates a service that forgot its role check: RLS must refuse.
        db.conn.execute(text(
            """INSERT INTO invites (agency_id, email, role, token_hash, invited_by, expires_at)
               VALUES (:agency, 'sneaky@acme.test', 'agency_admin', :hash, :user, now())"""
        ), {"agency": db.agency_id, "hash": uuid.uuid4().hex, "user": db.user_id})

    return app


@pytest.fixture(scope="module")
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def token(user_id: uuid.UUID, agency_id: uuid.UUID, secret: str = SECRET, ttl: int = 600) -> dict:
    return {"Authorization": f"Bearer {issue_session_token(user_id, agency_id, secret, ttl)}"}


def assert_pooled_connection_is_clean(app: FastAPI) -> None:
    """Check out the (only) pooled connection and confirm no context survived."""
    with app.state.api_engine.connect() as conn:
        row = conn.execute(text(
            """SELECT current_user,
                      coalesce(current_setting('app.agency_id', true), ''),
                      coalesce(current_setting('app.user_id', true), ''),
                      coalesce(current_setting('app.role', true), ''),
                      coalesce(current_setting('app.client_id', true), '')"""
        )).one()
        assert tuple(row) == ("agencydesk_api", "", "", "", "")
        # And with no context, RLS shows nothing.
        assert conn.execute(text("SELECT count(*) FROM tasks")).scalar() == 0


# ------------------------------------------------------------------ health
def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


# ------------------------------------------------------ token verification
@pytest.mark.parametrize("headers", [
    {},                                                  # no header
    {"Authorization": "Bearer not-a-token"},             # garbage
    {"Authorization": "Basic YWxpY2U6cGFzc3dvcmQ="},     # wrong scheme
])
def test_missing_or_malformed_token_is_401(client: TestClient, headers: dict) -> None:
    assert client.get("/_test/context", headers=headers).status_code == 401


def test_token_signed_with_another_secret_is_401(client: TestClient) -> None:
    forged = token(ALICE, PIXEL, secret="attacker-secret-" + "z" * 40)
    assert client.get("/_test/context", headers=forged).status_code == 401


def test_tampered_token_is_401(client: TestClient) -> None:
    good = issue_session_token(ALICE, PIXEL, SECRET, 600)
    payload, sig = good.split(".")
    # Re-use Alice's signature on a payload claiming Northwind.
    other_payload = issue_session_token(ALICE, NORTHWIND, SECRET, 600).split(".")[0]
    resp = client.get("/_test/context", headers={"Authorization": f"Bearer {other_payload}.{sig}"})
    assert resp.status_code == 401


def test_expired_token_is_401(client: TestClient) -> None:
    assert client.get("/_test/context", headers=token(ALICE, PIXEL, ttl=-1)).status_code == 401


# ---------------------------------------------------------- context setup
def test_context_comes_from_membership_row(client: TestClient) -> None:
    body = client.get("/_test/context", headers=token(ALICE, PIXEL)).json()
    assert body == {
        "current_user": "agencydesk_api",
        "agency_id": str(PIXEL), "user_id": str(ALICE),
        "role": "agency_admin", "client_id": "",
        "dep_role": "agency_admin", "dep_client_id": "",
    }


def test_api_pool_role_is_not_superuser_and_cannot_bypass_rls(app: FastAPI) -> None:
    with app.state.api_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = session_user"
        )).one()
        assert tuple(row) == ("agencydesk_api", False, False)


# ------------------------------------------------- edge: cross-tenant access
def test_cross_tenant_token_for_agency_you_are_not_in_is_401(client: TestClient) -> None:
    # Bob is a real user with a validly signed token, but has no Pixel membership.
    assert client.get("/_test/context", headers=token(BOB, PIXEL)).status_code == 401


def test_cross_tenant_rls_scopes_queries_without_where_clause(client: TestClient) -> None:
    assert client.get("/_test/tasks", headers=token(BOB, NORTHWIND)).json() == [TASK_NW_SECRET]
    assert TASK_NW_SECRET not in client.get("/_test/tasks", headers=token(ALICE, PIXEL)).json()


# ---------------------------------------- edge: one person in two agencies
def test_one_person_in_two_agencies_each_token_gets_that_agencys_membership(
    client: TestClient,
) -> None:
    # Ravi is a client_user at both agencies, for a different client in each.
    # This also proves the "read your own membership row" policy: without it,
    # a client_user's row is invisible during the lookup and this would be 401.
    at_pixel = client.get("/_test/context", headers=token(RAVI, PIXEL)).json()
    at_northwind = client.get("/_test/context", headers=token(RAVI, NORTHWIND)).json()
    assert (at_pixel["agency_id"], at_pixel["role"], at_pixel["client_id"]) == (
        str(PIXEL), "client_user", ACME)
    assert (at_northwind["agency_id"], at_northwind["role"], at_northwind["client_id"]) == (
        str(NORTHWIND), "client_user", INITECH)


# -------------------------------------------- removed membership takes effect
def test_removed_membership_gets_401_on_next_request(client: TestClient) -> None:
    headers = token(RAVI, PIXEL)
    assert client.get("/_test/context", headers=headers).status_code == 200
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(
            "UPDATE agency_memberships SET removed_at = now() WHERE agency_id = %s AND user_id = %s",
            (PIXEL, RAVI))
        try:
            # Same, still-unexpired token: rejected because the row is re-read.
            assert client.get("/_test/context", headers=headers).status_code == 401
            # His other agency is unaffected.
            assert client.get("/_test/context", headers=token(RAVI, NORTHWIND)).status_code == 200
        finally:
            admin.execute(
                "UPDATE agency_memberships SET removed_at = NULL WHERE agency_id = %s AND user_id = %s",
                (PIXEL, RAVI))


# ------------------------------------------------ no context leaks via pool
def test_context_does_not_leak_to_next_use_of_pooled_connection(
    app: FastAPI, client: TestClient,
) -> None:
    assert client.get("/_test/context", headers=token(ALICE, PIXEL)).status_code == 200
    assert_pooled_connection_is_clean(app)


def test_context_does_not_leak_after_a_failed_request(app: FastAPI, client: TestClient) -> None:
    assert client.get("/_test/boom", headers=token(ALICE, PIXEL)).status_code == 500
    assert_pooled_connection_is_clean(app)


def test_context_does_not_leak_after_a_rejected_membership(
    app: FastAPI, client: TestClient,
) -> None:
    # get_tenant_db had already set agency_id/user_id before finding no membership.
    assert client.get("/_test/context", headers=token(BOB, PIXEL)).status_code == 401
    assert_pooled_connection_is_clean(app)


def test_back_to_back_requests_for_different_tenants_on_one_connection(
    client: TestClient,
) -> None:
    for _ in range(3):
        assert client.get("/_test/context", headers=token(ALICE, PIXEL)).json()["agency_id"] == str(PIXEL)
        assert client.get("/_test/context", headers=token(BOB, NORTHWIND)).json()["agency_id"] == str(NORTHWIND)


# ------------------------------------------- rule 4: one place sets context
def test_request_context_is_set_only_in_get_tenant_db() -> None:
    backend = pathlib.Path(__file__).resolve().parent.parent / "backend" / "app"
    offenders = [
        str(path.relative_to(backend))
        for path in backend.rglob("*.py")
        if path.name != "db.py"
        and ("set_config" in path.read_text() or "SET LOCAL" in path.read_text().upper()
             or "SET ROLE" in path.read_text().upper())
    ]
    assert offenders == []


# =========================================================== step 6: login
def login(client: TestClient, email: str, password: str = "password", portal: bool = False):
    path = "/auth/portal/login" if portal else "/auth/login"
    return client.post(path, json={"email": email, "password": password})


def select_agency(client: TestClient, identity_token: str, agency_id: uuid.UUID):
    return client.post(
        "/auth/session",
        json={"agency_id": str(agency_id)},
        headers={"Authorization": f"Bearer {identity_token}"},
    )


def session_headers(client: TestClient, email: str, agency_id: uuid.UUID, portal: bool = False) -> dict:
    identity = login(client, email, portal=portal).json()["identity_token"]
    resp = select_agency(client, identity, agency_id)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['session_token']}"}


def test_staff_login_lists_staff_memberships(client: TestClient) -> None:
    resp = login(client, "alice@pixel.test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["identity_token"]
    assert body["memberships"] == [{
        "agency_id": str(PIXEL), "agency_name": "Pixel Studio",
        "role": "agency_admin", "client_name": None,
    }]


def test_login_email_is_case_and_space_insensitive(client: TestClient) -> None:
    assert login(client, "  Alice@PIXEL.test ").status_code == 200


def test_wrong_password_and_unknown_email_get_identical_401(client: TestClient) -> None:
    wrong_password = login(client, "alice@pixel.test", password="nope")
    unknown_email = login(client, "nobody@pixel.test")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid email or password"}


def test_over_long_password_is_401_not_500(client: TestClient) -> None:
    assert login(client, "alice@pixel.test", password="p" * 150).status_code == 401


def test_staff_and_portal_logins_list_only_their_kind(client: TestClient) -> None:
    # Ravi only has client memberships; Alice only has a staff one.
    assert login(client, "ravi@acme.test").status_code == 403
    assert login(client, "alice@pixel.test", portal=True).status_code == 403


def test_one_person_in_two_agencies_logs_in_once_and_sees_both(client: TestClient) -> None:
    resp = login(client, "ravi@acme.test", portal=True)
    assert resp.status_code == 200
    options = {(m["agency_id"], m["role"]) for m in resp.json()["memberships"]}
    assert options == {(str(PIXEL), "client_user"), (str(NORTHWIND), "client_user")}


def test_one_person_in_two_agencies_session_token_works_only_for_chosen_agency(
    client: TestClient,
) -> None:
    at_pixel = session_headers(client, "ravi@acme.test", PIXEL, portal=True)
    at_northwind = session_headers(client, "ravi@acme.test", NORTHWIND, portal=True)

    me_pixel = client.get("/me", headers=at_pixel).json()
    me_northwind = client.get("/me", headers=at_northwind).json()
    assert (me_pixel["agency"]["id"], me_pixel["client"]["id"]) == (str(PIXEL), ACME)
    assert (me_northwind["agency"]["id"], me_northwind["client"]["id"]) == (str(NORTHWIND), INITECH)
    # Same person, but the Pixel token never reaches Northwind data.
    assert TASK_NW_SECRET not in client.get("/_test/tasks", headers=at_pixel).json()


def test_cross_tenant_select_agency_you_are_not_in_is_404(client: TestClient) -> None:
    identity = login(client, "alice@pixel.test").json()["identity_token"]
    assert select_agency(client, identity, NORTHWIND).status_code == 404
    assert select_agency(client, identity, uuid.uuid4()).status_code == 404


def test_staff_login_cannot_open_a_client_membership(client: TestClient) -> None:
    # Give Bob (Northwind admin) a client membership at Pixel for this test.
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(
            """INSERT INTO agency_memberships (agency_id, user_id, role, client_id)
               VALUES (%s, %s, 'client_user', %s)""", (PIXEL, BOB, ACME))
        try:
            staff = login(client, "bob@northwind.test").json()
            assert [m["agency_id"] for m in staff["memberships"]] == [str(NORTHWIND)]
            assert select_agency(client, staff["identity_token"], PIXEL).status_code == 404

            portal = login(client, "bob@northwind.test", portal=True).json()
            assert [m["agency_id"] for m in portal["memberships"]] == [str(PIXEL)]
            assert select_agency(client, portal["identity_token"], NORTHWIND).status_code == 404
        finally:
            admin.execute("DELETE FROM agency_memberships WHERE agency_id = %s AND user_id = %s",
                          (PIXEL, BOB))


def test_identity_token_cannot_be_used_as_session_token(client: TestClient) -> None:
    identity = login(client, "alice@pixel.test").json()["identity_token"]
    assert client.get("/me", headers={"Authorization": f"Bearer {identity}"}).status_code == 401


def test_session_token_cannot_be_used_to_select_agency(client: TestClient) -> None:
    session = issue_session_token(ALICE, PIXEL, SECRET, 600)
    assert select_agency(client, session, PIXEL).status_code == 401


def test_select_agency_without_identity_token_is_401(client: TestClient) -> None:
    assert client.post("/auth/session", json={"agency_id": str(PIXEL)}).status_code == 401


def test_removed_membership_disappears_from_login_and_blocks_tokens(client: TestClient) -> None:
    identity = login(client, "ravi@acme.test", portal=True).json()["identity_token"]
    pixel_session = session_headers(client, "ravi@acme.test", PIXEL, portal=True)
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(
            "UPDATE agency_memberships SET removed_at = now() WHERE agency_id = %s AND user_id = %s",
            (PIXEL, RAVI))
        try:
            listed = login(client, "ravi@acme.test", portal=True).json()["memberships"]
            assert [m["agency_id"] for m in listed] == [str(NORTHWIND)]
            # Identity token issued before the removal can't open Pixel any more...
            assert select_agency(client, identity, PIXEL).status_code == 404
            # ...and the existing Pixel session stops working on the next request.
            assert client.get("/me", headers=pixel_session).status_code == 401
        finally:
            admin.execute(
                "UPDATE agency_memberships SET removed_at = NULL WHERE agency_id = %s AND user_id = %s",
                (PIXEL, RAVI))


def test_me_for_staff(client: TestClient) -> None:
    resp = client.get("/me", headers=session_headers(client, "alice@pixel.test", PIXEL))
    assert resp.status_code == 200
    assert resp.json() == {
        "user": {"id": str(ALICE), "email": "alice@pixel.test", "name": "Alice (Pixel admin)"},
        "agency": {"id": str(PIXEL), "name": "Pixel Studio"},
        "role": "agency_admin",
        "client": None,
    }
    assert "password" not in resp.text


def test_login_pool_is_read_only_auth_role(app: FastAPI) -> None:
    from app.auth.db import get_auth_db

    @app.get("/_test/auth-db")
    def auth_db(conn=Depends(get_auth_db)) -> list[str]:
        row = conn.execute(text("SELECT current_user, current_setting('transaction_read_only')")).one()
        return list(row)

    assert TestClient(app).get("/_test/auth-db").json() == ["agencydesk_auth", "on"]


def test_auth_pool_is_only_used_by_auth_code() -> None:
    # AGENTS.md rule 10: agencydesk_auth (BYPASSRLS) is for login, agency
    # selection and accept_invite only.
    backend = pathlib.Path(__file__).resolve().parent.parent / "backend" / "app"
    allowed = {"auth/db.py", "routers/auth.py", "main.py", "config.py"}
    markers = ("auth_engine", "get_auth_db", "agencydesk_auth", "auth_database_url")
    offenders = [
        str(path.relative_to(backend))
        for path in backend.rglob("*.py")
        if str(path.relative_to(backend)) not in allowed
        and any(marker in path.read_text() for marker in markers)
    ]
    assert offenders == []


# ========================================================= step 7: invites
MARK = uuid.UUID("00000000-0000-0000-0000-0000000000a2")    # Pixel member


def new_email() -> str:
    return f"invitee-{uuid.uuid4().hex[:8]}@acme.test"


def create_invite(client: TestClient, admin: dict, email: str, role: str = "client_user",
                  client_id: str | None = ACME):
    return client.post("/invites", headers=admin,
                       json={"email": email, "role": role, "client_id": client_id})


def token_from(resp) -> str:
    return resp.json()["invite_url"].split("#token=")[1]


def accept(client: TestClient, token: str, name: str | None = "New Person",
           password: str | None = "a-good-password", identity: str | None = None):
    headers = {"Authorization": f"Bearer {identity}"} if identity else {}
    return client.post("/invites/accept", headers=headers,
                       json={"token": token, "name": name, "password": password})


@pytest.fixture
def alice(client: TestClient) -> dict:
    return session_headers(client, "alice@pixel.test", PIXEL)


def test_admin_creates_invite_and_gets_link_without_token_hash(client: TestClient, alice: dict) -> None:
    email = new_email()
    resp = create_invite(client, alice, email)
    assert resp.status_code == 201
    body = resp.json()
    assert body["invite"]["email"] == email and body["invite"]["status"] == "pending"
    assert body["invite_url"].startswith("http://localhost:5173/invite#token=")
    assert "token_hash" not in resp.text
    listed = client.get("/invites", headers=alice).json()
    assert body["invite"]["id"] in [i["id"] for i in listed]
    assert "token" not in client.get("/invites", headers=alice).text


def test_invite_races_resend_reuses_row_and_old_link_stops_working(
    client: TestClient, alice: dict,
) -> None:
    email = new_email()
    first = create_invite(client, alice, email)
    invite_id = first.json()["invite"]["id"]
    resent = client.post(f"/invites/{invite_id}/resend", headers=alice)
    again = create_invite(client, alice, email)          # "invite" twice = resend too
    assert resent.status_code == 200 and again.status_code == 201
    assert resent.json()["invite"]["id"] == again.json()["invite"]["id"] == invite_id
    assert again.json()["invite"]["send_count"] == 3
    assert [i["id"] for i in client.get("/invites", headers=alice).json()
            if i["email"] == email] == [invite_id]

    assert accept(client, token_from(first)).status_code == 404     # old links are dead
    assert accept(client, token_from(resent)).status_code == 404
    assert accept(client, token_from(again)).status_code == 200      # latest one works
    assert login(client, email, password="a-good-password", portal=True).status_code == 200


def test_invite_races_two_simultaneous_accepts_create_one_account(
    app: FastAPI, client: TestClient, alice: dict,
) -> None:
    email = new_email()
    token = token_from(create_invite(client, alice, email))
    results: list[int] = []
    barrier = threading.Barrier(2)

    def accept_in_thread() -> None:
        own_client = TestClient(app, raise_server_exceptions=False)
        barrier.wait()
        results.append(accept(own_client, token).status_code)

    threads = [threading.Thread(target=accept_in_thread) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 404]
    with psycopg.connect(DSN) as admin:
        assert admin.execute("SELECT count(*) FROM users WHERE email = %s", (email,)).fetchone()[0] == 1


def test_invite_races_existing_account_must_be_logged_in_as_it(
    client: TestClient,
) -> None:
    # Bob (Northwind admin) invites Mark (a Pixel member) as a Northwind client contact.
    bob = session_headers(client, "bob@northwind.test", NORTHWIND)
    token = token_from(create_invite(client, bob, "mark@pixel.test", client_id=INITECH))
    alice_identity = login(client, "alice@pixel.test").json()["identity_token"]
    mark_identity = login(client, "mark@pixel.test").json()["identity_token"]
    try:
        # Logged out, trying to set a new password on Mark's account: refused.
        assert accept(client, token, password="attacker-password").status_code == 401
        # Logged in as someone else: refused.
        assert accept(client, token, identity=alice_identity).status_code == 403
        # Logged in as Mark: accepted.
        resp = accept(client, token, identity=mark_identity)
        assert resp.status_code == 200
        assert resp.json() == {"agency_id": str(NORTHWIND), "role": "client_user", "login": "portal"}
        # One person in two agencies now; his password is unchanged.
        assert login(client, "mark@pixel.test", password="attacker-password").status_code == 401
        portal = login(client, "mark@pixel.test", portal=True).json()["memberships"]
        assert [m["agency_id"] for m in portal] == [str(NORTHWIND)]
    finally:
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute("DELETE FROM agency_memberships WHERE agency_id = %s AND user_id = %s",
                          (NORTHWIND, MARK))


def test_logged_in_user_cannot_accept_invite_for_a_new_email(client: TestClient, alice: dict) -> None:
    token = token_from(create_invite(client, alice, new_email()))
    alice_identity = login(client, "alice@pixel.test").json()["identity_token"]
    assert accept(client, token, identity=alice_identity).status_code == 403
    assert accept(client, token).status_code == 200      # still usable by the real invitee


def test_accept_with_bad_identity_token_is_401_not_logged_out(client: TestClient, alice: dict) -> None:
    token = token_from(create_invite(client, alice, new_email()))
    assert accept(client, token, identity="garbage.token").status_code == 401


@pytest.mark.parametrize("name, password", [(None, "a-good-password"), ("  ", "a-good-password"),
                                            ("New", None), ("New", "short")])
def test_new_account_needs_name_and_valid_password(
    client: TestClient, alice: dict, name: str | None, password: str | None,
) -> None:
    token = token_from(create_invite(client, alice, new_email()))
    assert accept(client, token, name=name, password=password).status_code == 422
    assert accept(client, token).status_code == 200      # a failed attempt doesn't burn the invite


def test_unknown_or_garbage_invite_token_is_404(client: TestClient) -> None:
    assert accept(client, "x" * 43).status_code == 404


def test_revoked_invite_cannot_be_accepted(client: TestClient, alice: dict) -> None:
    created = create_invite(client, alice, new_email())
    invite_id = created.json()["invite"]["id"]
    assert client.delete(f"/invites/{invite_id}", headers=alice).status_code == 204
    assert accept(client, token_from(created)).status_code == 404
    assert client.delete(f"/invites/{invite_id}", headers=alice).status_code == 409
    assert client.post(f"/invites/{invite_id}/resend", headers=alice).status_code == 409


def test_inviting_an_active_member_is_409(client: TestClient, alice: dict) -> None:
    assert create_invite(client, alice, "MARK@pixel.test", role="agency_member",
                         client_id=None).status_code == 409


@pytest.mark.parametrize("role, client_id", [("client_user", None), ("agency_member", ACME)])
def test_client_id_required_exactly_for_client_users(
    client: TestClient, alice: dict, role: str, client_id: str | None,
) -> None:
    assert create_invite(client, alice, new_email(), role=role, client_id=client_id).status_code == 422


def test_cross_tenant_invite_for_another_agencys_client_is_422(client: TestClient, alice: dict) -> None:
    resp = create_invite(client, alice, new_email(), client_id=INITECH)
    assert resp.status_code == 422 and "Initech" not in resp.text


def test_cross_tenant_invite_ids_are_404(client: TestClient, alice: dict) -> None:
    invite_id = create_invite(client, alice, new_email()).json()["invite"]["id"]
    bob = session_headers(client, "bob@northwind.test", NORTHWIND)
    assert client.post(f"/invites/{invite_id}/resend", headers=bob).status_code == 404
    assert client.delete(f"/invites/{invite_id}", headers=bob).status_code == 404
    assert invite_id not in [i["id"] for i in client.get("/invites", headers=bob).json()]
    # And it's untouched for Alice.
    assert client.post(f"/invites/{invite_id}/resend", headers=alice).status_code == 200


@pytest.mark.parametrize("who, agency, portal", [
    ("mark@pixel.test", PIXEL, False),    # agency_member
    ("ravi@acme.test", PIXEL, True),      # client_user
])
def test_non_admin_cannot_manage_invites(
    client: TestClient, alice: dict, who: str, agency: uuid.UUID, portal: bool,
) -> None:
    invite_id = create_invite(client, alice, new_email()).json()["invite"]["id"]
    headers = session_headers(client, who, agency, portal=portal)
    assert client.get("/invites", headers=headers).status_code == 403
    assert create_invite(client, headers, new_email()).status_code == 403
    assert client.post(f"/invites/{invite_id}/resend", headers=headers).status_code == 403
    assert client.delete(f"/invites/{invite_id}", headers=headers).status_code == 403


def test_rls_refusing_a_write_is_403_without_database_details(client: TestClient) -> None:
    # A member writing an invite with no service check in the way: RLS says no.
    resp = client.post("/_test/write-invite-skipping-service",
                       headers=session_headers(client, "mark@pixel.test", PIXEL))
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Not allowed"}


# ============================================ step 8: clients and projects
NINA = uuid.UUID("00000000-0000-0000-0000-0000000000a3")    # Pixel member, on Acme only
ACME_PROJECT = "aaaaaaaa-0000-0000-0002-000000000001"
GLOBEX_PROJECT = "aaaaaaaa-0000-0000-0002-000000000002"
NW_PROJECT = "bbbbbbbb-0000-0000-0002-000000000001"


def project_ids(client: TestClient, headers: dict) -> set[str]:
    resp = client.get("/projects", headers=headers)
    assert resp.status_code == 200
    return {p["id"] for p in resp.json()}


def new_project(client: TestClient, alice: dict, name: str = "Temp project") -> str:
    resp = client.post("/projects", headers=alice, json={"client_id": ACME, "name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_admin_sees_all_projects_member_sees_only_assigned(client: TestClient, alice: dict) -> None:
    assert {ACME_PROJECT, GLOBEX_PROJECT} <= project_ids(client, alice)
    assert NW_PROJECT not in project_ids(client, alice)
    nina = session_headers(client, "nina@pixel.test", PIXEL)
    assert project_ids(client, nina) == {ACME_PROJECT}
    assert client.get(f"/projects/{GLOBEX_PROJECT}", headers=nina).status_code == 404
    assert client.get(f"/projects/{GLOBEX_PROJECT}/members", headers=nina).status_code == 404


def test_client_sees_own_clients_projects_without_internal_fields(client: TestClient) -> None:
    ravi = session_headers(client, "ravi@acme.test", PIXEL, portal=True)
    projects = client.get("/projects", headers=ravi).json()
    assert [p["id"] for p in projects] == [ACME_PROJECT]
    assert set(projects[0]) == {"id", "name", "created_at"}
    assert set(client.get(f"/projects/{ACME_PROJECT}", headers=ravi).json()) == {"id", "name", "created_at"}
    assert client.get(f"/projects/{GLOBEX_PROJECT}", headers=ravi).status_code == 404


def test_staff_project_has_client_fields(client: TestClient, alice: dict) -> None:
    body = client.get(f"/projects/{ACME_PROJECT}", headers=alice).json()
    assert body["client_id"] == ACME and body["client_name"] == "Acme Corp"


def test_cross_tenant_project_and_client_ids_are_404(client: TestClient, alice: dict) -> None:
    bob = session_headers(client, "bob@northwind.test", NORTHWIND)
    assert client.get(f"/projects/{ACME_PROJECT}", headers=bob).status_code == 404
    assert client.get(f"/projects/{ACME_PROJECT}/members", headers=bob).status_code == 404
    assert client.post(f"/projects/{ACME_PROJECT}/members", headers=bob,
                       json={"user_id": str(BOB)}).status_code == 404
    assert client.delete(f"/projects/{ACME_PROJECT}/members/{MARK}", headers=bob).status_code == 404
    assert client.get(f"/clients/{ACME}", headers=bob).status_code == 404
    assert client.get(f"/projects/{NW_PROJECT}", headers=alice).status_code == 404
    assert client.get(f"/clients/{INITECH}", headers=alice).status_code == 404
    # Nothing changed for Pixel.
    members = {m["user_id"] for m in client.get(f"/projects/{ACME_PROJECT}/members", headers=alice).json()}
    assert {str(MARK), str(NINA)} <= members


def test_cross_tenant_project_for_another_agencys_client_is_422(client: TestClient, alice: dict) -> None:
    resp = client.post("/projects", headers=alice, json={"client_id": INITECH, "name": "Sneaky"})
    assert resp.status_code == 422 and "Initech" not in resp.text


def test_admin_creates_client_and_project(client: TestClient, alice: dict) -> None:
    created = client.post("/clients", headers=alice, json={"name": "  Hooli  "})
    assert created.status_code == 201 and created.json()["name"] == "Hooli"
    client_id = created.json()["id"]
    assert client_id in {c["id"] for c in client.get("/clients", headers=alice).json()}

    project = client.post("/projects", headers=alice, json={"client_id": client_id, "name": "Hooli app"})
    assert project.status_code == 201
    assert project.json()["client_name"] == "Hooli"
    nina = session_headers(client, "nina@pixel.test", PIXEL)
    assert project.json()["id"] not in project_ids(client, nina)   # not on it


@pytest.mark.parametrize("who, portal", [("mark@pixel.test", False), ("ravi@acme.test", True)])
def test_non_admin_cannot_write_clients_projects_or_members(
    client: TestClient, who: str, portal: bool,
) -> None:
    headers = session_headers(client, who, PIXEL, portal=portal)
    assert client.post("/clients", headers=headers, json={"name": "X"}).status_code == 403
    assert client.post("/projects", headers=headers,
                       json={"client_id": ACME, "name": "X"}).status_code == 403
    assert client.post(f"/projects/{ACME_PROJECT}/members", headers=headers,
                       json={"user_id": str(MARK)}).status_code == 403
    assert client.delete(f"/projects/{ACME_PROJECT}/members/{NINA}", headers=headers).status_code == 403


def test_client_cannot_see_clients_or_project_team(client: TestClient) -> None:
    ravi = session_headers(client, "ravi@acme.test", PIXEL, portal=True)
    assert client.get("/clients", headers=ravi).status_code == 403
    assert client.get(f"/clients/{ACME}", headers=ravi).status_code == 403
    assert client.get(f"/projects/{ACME_PROJECT}/members", headers=ravi).status_code == 403


def test_member_can_see_team_of_their_project(client: TestClient) -> None:
    nina = session_headers(client, "nina@pixel.test", PIXEL)
    members = client.get(f"/projects/{ACME_PROJECT}/members", headers=nina).json()
    assert {m["user_id"] for m in members} >= {str(MARK), str(NINA)}


def test_add_member_only_accepts_active_staff_of_this_agency(client: TestClient, alice: dict) -> None:
    project_id = new_project(client, alice)
    added = client.post(f"/projects/{project_id}/members", headers=alice, json={"user_id": str(MARK)})
    assert added.status_code == 201 and [m["user_id"] for m in added.json()] == [str(MARK)]
    assert client.post(f"/projects/{project_id}/members", headers=alice,
                       json={"user_id": str(MARK)}).status_code == 409
    for not_allowed in (RAVI, BOB, uuid.uuid4()):     # client user, other agency, nobody
        resp = client.post(f"/projects/{project_id}/members", headers=alice,
                           json={"user_id": str(not_allowed)})
        assert resp.status_code == 422
        assert resp.json() == {"detail": "Only active staff members of this agency can be added to a project"}

    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute("UPDATE agency_memberships SET removed_at = now() WHERE agency_id = %s AND user_id = %s",
                      (PIXEL, NINA))
        try:
            assert client.post(f"/projects/{project_id}/members", headers=alice,
                               json={"user_id": str(NINA)}).status_code == 422
        finally:
            admin.execute("UPDATE agency_memberships SET removed_at = NULL WHERE agency_id = %s AND user_id = %s",
                          (PIXEL, NINA))


def test_removing_member_mid_task_unassigns_only_their_tasks_and_logs_it(
    client: TestClient, alice: dict,
) -> None:
    project_id = new_project(client, alice, "Mid-task removal")
    for user in (MARK, NINA):
        assert client.post(f"/projects/{project_id}/members", headers=alice,
                           json={"user_id": str(user)}).status_code == 201
    mark_task, nina_task = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(DSN, autocommit=True) as admin:
        for task_id, assignee in ((mark_task, MARK), (nina_task, NINA)):
            admin.execute(
                """INSERT INTO tasks (id, agency_id, project_id, title, status, priority, visibility,
                                      assignee_user_id, created_by)
                   VALUES (%s, %s, %s, 'Half done', 'in_progress', 'high', 'internal', %s, %s)""",
                (task_id, PIXEL, project_id, assignee, ALICE))
        admin.execute("""INSERT INTO time_entries (agency_id, task_id, user_id, minutes, entry_date, note)
                         VALUES (%s, %s, %s, 90, '2026-11-10', 'work so far')""", (PIXEL, mark_task, MARK))

    mark = session_headers(client, "mark@pixel.test", PIXEL)
    assert project_id in project_ids(client, mark)

    resp = client.delete(f"/projects/{project_id}/members/{MARK}", headers=alice)
    assert resp.status_code == 200 and resp.json() == {"unassigned_task_count": 1}

    with psycopg.connect(DSN) as admin:
        tasks = dict(admin.execute(
            "SELECT id, (assignee_user_id, status) FROM tasks WHERE project_id = %s", (project_id,)).fetchall())
        assert tasks[mark_task] == (None, "in_progress")          # unassigned, status kept
        assert tasks[nina_task] == (str(NINA), "in_progress")     # other people untouched
        events = admin.execute(
            "SELECT kind, actor_id, payload->>'from' FROM task_events WHERE task_id = %s", (mark_task,)).fetchall()
        assert events == [("auto_unassigned_member_removed", ALICE, str(MARK))]
        assert admin.execute("SELECT count(*) FROM time_entries WHERE task_id = %s",
                             (mark_task,)).fetchone()[0] == 1      # history kept

    assert project_id not in project_ids(client, mark)             # access gone immediately
    assert client.get(f"/projects/{project_id}", headers=mark).status_code == 404
    assert client.delete(f"/projects/{project_id}/members/{MARK}", headers=alice).status_code == 404
    # Take Nina off too, so later tests still see her on the Acme project only.
    assert client.delete(f"/projects/{project_id}/members/{NINA}", headers=alice).status_code == 200


# ===================================================== step 9: tasks
TASK_MOCKUPS = "aaaaaaaa-0000-0000-0003-000000000001"   # Acme, client-visible, in_review, high, Mark
TASK_BUDGET = "aaaaaaaa-0000-0000-0003-000000000002"    # Acme, INTERNAL, in_progress, urgent, Nina
TASK_CONTENT = "aaaaaaaa-0000-0000-0003-000000000003"   # Acme, client-visible, todo, medium, Nina
TASK_GLOBEX = "aaaaaaaa-0000-0000-0003-000000000004"    # Globex, client-visible, unassigned
CLIENT_TASK_FIELDS = {"id", "project_id", "title", "description", "status", "priority",
                      "due_date", "created_at", "updated_at"}


def task_ids(client: TestClient, headers: dict, project: str = ACME_PROJECT, **params) -> set[str]:
    resp = client.get(f"/projects/{project}/tasks", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return {t["id"] for t in resp.json()}


@pytest.fixture
def ravi(client: TestClient) -> dict:
    return session_headers(client, "ravi@acme.test", PIXEL, portal=True)


@pytest.fixture
def mark(client: TestClient) -> dict:
    return session_headers(client, "mark@pixel.test", PIXEL)


def test_internal_content_leaking_to_clients_via_task_list_search_and_filters(
    client: TestClient, ravi: dict,
) -> None:
    assert task_ids(client, ravi) == {TASK_MOCKUPS, TASK_CONTENT}
    for task in client.get(f"/projects/{ACME_PROJECT}/tasks", headers=ravi).json():
        assert set(task) == CLIENT_TASK_FIELDS                       # no visibility/assignee/creator
    # The internal task matches each of these, but the client must get nothing.
    for params in ({"q": "budget"}, {"q": "STAGING"}, {"q": "overrun"},
                   {"status": "in_progress"}, {"priority": "urgent"},
                   {"q": "budget", "status": "in_progress", "priority": "urgent"}):
        assert task_ids(client, ravi, **params) == set(), params
    assert TASK_BUDGET not in task_ids(client, ravi, q="o")             # broad search
    assert client.get(f"/tasks/{TASK_BUDGET}", headers=ravi).status_code == 404
    assert "budget" not in client.get(f"/tasks/{TASK_BUDGET}", headers=ravi).text.lower()


@pytest.mark.parametrize("assignee", ["me", "unassigned", str(NINA)])
def test_client_cannot_filter_by_assignee(client: TestClient, ravi: dict, assignee: str) -> None:
    resp = client.get(f"/projects/{ACME_PROJECT}/tasks", headers=ravi, params={"assignee": assignee})
    assert resp.status_code == 403


def test_client_cannot_create_or_change_tasks(client: TestClient, ravi: dict) -> None:
    assert client.post(f"/projects/{ACME_PROJECT}/tasks", headers=ravi,
                       json={"title": "Please add a blog"}).status_code == 403
    for change in ({"status": "done"}, {"priority": "low"}, {"title": "Renamed"}):
        assert client.patch(f"/tasks/{TASK_MOCKUPS}", headers=ravi, json=change).status_code == 403
    with psycopg.connect(DSN) as admin:
        assert admin.execute("SELECT status, priority, title FROM tasks WHERE id = %s",
                             (TASK_MOCKUPS,)).fetchone() == ("in_review", "high", "Homepage mockups")


def test_staff_filters_and_search(client: TestClient, alice: dict, mark: dict) -> None:
    assert task_ids(client, alice) >= {TASK_MOCKUPS, TASK_BUDGET, TASK_CONTENT}
    assert task_ids(client, alice, status="in_progress") == {TASK_BUDGET}
    assert task_ids(client, alice, priority="urgent") == {TASK_BUDGET}
    assert task_ids(client, alice, q="BUDGET") == {TASK_BUDGET}               # case-insensitive
    assert task_ids(client, alice, assignee=str(NINA)) == {TASK_BUDGET, TASK_CONTENT}
    assert task_ids(client, mark, assignee="me") == {TASK_MOCKUPS}
    assert task_ids(client, alice, project=GLOBEX_PROJECT, assignee="unassigned") == {TASK_GLOBEX}
    # LIKE wildcards are matched literally, not as "anything".
    assert task_ids(client, alice, q="%") == set()
    assert task_ids(client, alice, q="_") == set()
    staff_task = client.get(f"/tasks/{TASK_BUDGET}", headers=alice).json()
    assert staff_task["visibility"] == "internal" and staff_task["assignee_name"] == "Nina (Pixel member)"


@pytest.mark.parametrize("params", [{"assignee": "someone"}, {"status": "bogus"}, {"priority": "meh"}])
def test_bad_filter_values_are_422(client: TestClient, alice: dict, params: dict) -> None:
    assert client.get(f"/projects/{ACME_PROJECT}/tasks", headers=alice, params=params).status_code == 422


def test_member_creates_task_internal_by_default_hidden_from_client(
    client: TestClient, mark: dict, ravi: dict,
) -> None:
    resp = client.post(f"/projects/{ACME_PROJECT}/tasks", headers=mark,
                       json={"title": "  Draft internal estimate  ", "assignee_user_id": str(MARK)})
    assert resp.status_code == 201
    task = resp.json()
    assert (task["title"], task["visibility"], task["status"], task["created_by"]) == (
        "Draft internal estimate", "internal", "todo", str(MARK))
    assert task["id"] not in task_ids(client, ravi)
    assert task_ids(client, ravi, q="estimate") == set()
    assert client.get(f"/tasks/{task['id']}", headers=ravi).status_code == 404


def test_assigning_someone_outside_the_project_is_422(client: TestClient, alice: dict, mark: dict) -> None:
    for outsider in (ALICE, BOB, RAVI, uuid.uuid4()):   # admin not on project, other agency, client, nobody
        created = client.post(f"/projects/{ACME_PROJECT}/tasks", headers=mark,
                              json={"title": "X", "assignee_user_id": str(outsider)})
        assert created.status_code == 422
        assert created.json() == {"detail": "The assignee must be a member of this project"}
        patched = client.patch(f"/tasks/{TASK_MOCKUPS}", headers=mark,
                               json={"assignee_user_id": str(outsider)})
        assert patched.status_code == 422

    # Someone who *is* on the project: fine, and the change is logged.
    assert client.patch(f"/tasks/{TASK_MOCKUPS}", headers=mark,
                        json={"assignee_user_id": str(NINA)}).json()["assignee_user_id"] == str(NINA)
    assert client.patch(f"/tasks/{TASK_MOCKUPS}", headers=mark,
                        json={"assignee_user_id": str(MARK)}).status_code == 200
    with psycopg.connect(DSN) as admin:
        events = admin.execute(
            """SELECT kind, actor_id, payload->>'to' FROM task_events
               WHERE task_id = %s ORDER BY id DESC LIMIT 2""", (TASK_MOCKUPS,)).fetchall()
    assert events == [("assignee_changed", MARK, str(MARK)), ("assignee_changed", MARK, str(NINA))]


def test_member_cannot_touch_tasks_on_projects_they_are_not_on(client: TestClient, mark: dict) -> None:
    assert client.get(f"/projects/{GLOBEX_PROJECT}/tasks", headers=mark).status_code == 404
    assert client.post(f"/projects/{GLOBEX_PROJECT}/tasks", headers=mark,
                       json={"title": "X"}).status_code == 404
    assert client.get(f"/tasks/{TASK_GLOBEX}", headers=mark).status_code == 404
    assert client.patch(f"/tasks/{TASK_GLOBEX}", headers=mark, json={"status": "done"}).status_code == 404


def test_cross_tenant_task_ids_are_404(client: TestClient, alice: dict) -> None:
    bob = session_headers(client, "bob@northwind.test", NORTHWIND)
    assert client.get(f"/tasks/{TASK_MOCKUPS}", headers=bob).status_code == 404
    assert client.patch(f"/tasks/{TASK_MOCKUPS}", headers=bob, json={"status": "done"}).status_code == 404
    assert client.get(f"/projects/{ACME_PROJECT}/tasks", headers=bob).status_code == 404
    assert client.post(f"/projects/{ACME_PROJECT}/tasks", headers=bob, json={"title": "X"}).status_code == 404
    assert client.get(f"/tasks/{TASK_NW_SECRET}", headers=alice).status_code == 404
    assert client.patch(f"/tasks/{TASK_NW_SECRET}", headers=alice, json={"status": "done"}).status_code == 404


def test_flipping_task_to_internal_hides_it_from_client(client: TestClient, alice: dict, ravi: dict) -> None:
    assert client.patch(f"/tasks/{TASK_CONTENT}", headers=alice,
                        json={"visibility": "internal"}).status_code == 200
    try:
        assert TASK_CONTENT not in task_ids(client, ravi)
        assert task_ids(client, ravi, q="migration") == set()
        assert client.get(f"/tasks/{TASK_CONTENT}", headers=ravi).status_code == 404
    finally:
        client.patch(f"/tasks/{TASK_CONTENT}", headers=alice, json={"visibility": "client"})
    assert TASK_CONTENT in task_ids(client, ravi)


def test_patch_changes_only_sent_fields_and_null_unassigns(client: TestClient, mark: dict) -> None:
    task = client.post(f"/projects/{ACME_PROJECT}/tasks", headers=mark, json={
        "title": "Patch me", "priority": "high", "assignee_user_id": str(MARK), "due_date": "2026-12-01",
    }).json()
    done = client.patch(f"/tasks/{task['id']}", headers=mark, json={"status": "done"}).json()
    assert (done["status"], done["priority"], done["assignee_user_id"], done["due_date"]) == (
        "done", "high", str(MARK), "2026-12-01")
    cleared = client.patch(f"/tasks/{task['id']}", headers=mark,
                           json={"assignee_user_id": None, "due_date": None}).json()
    assert (cleared["assignee_user_id"], cleared["due_date"], cleared["status"]) == (None, None, "done")
    for bad in ({"status": None}, {"title": "   "}, {"visibility": None}):
        assert client.patch(f"/tasks/{task['id']}", headers=mark, json=bad).status_code == 422


def test_task_inputs_reject_agency_and_project_fields(client: TestClient, mark: dict) -> None:
    assert client.post(f"/projects/{ACME_PROJECT}/tasks", headers=mark,
                       json={"title": "X", "agency_id": str(NORTHWIND)}).status_code == 422
    assert client.patch(f"/tasks/{TASK_MOCKUPS}", headers=mark,
                        json={"project_id": GLOBEX_PROJECT}).status_code == 422
