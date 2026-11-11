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
from conftest import DSN, api_database_url, auth_database_url

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
