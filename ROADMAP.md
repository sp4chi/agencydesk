# AgencyDesk — Roadmap

Build order. Each step below is implemented and committed separately, in this order. Each step must be runnable and testable before moving to the next. Tick the box and fill in the commit hash when a step lands.

Rules for every step:
- One step = one commit, with a message in the form `Implement <thing>` / `Add <thing>` / `Fix <thing>`.
- `pytest -q` stays green after every commit. A step isn't done if it skips or deletes a test.
- Security rules come from `AGENTS.md`. When a step touches tenant isolation, its test lands in the same commit.

---

## Phase 1: Database

1. [x] **Schema, RLS policies, triggers and functions:** [db/schema.sql](db/schema.sql)
   Standalone; loads into any Postgres 15+ with `psql -f`.
2. [x] **Seed data:** [db/seed.sql](db/seed.sql)
   Includes 2 agencies, Ravi (same email at both), a mix of internal and client-visible tasks, comments, files and time.
3. [x] **DB rule tests:** [tests/test_db_rules.py](tests/test_db_rules.py)
   20 tests covering the five edge cases plus the "every tenant table has RLS" guard. They run as `agencydesk_api`, the role the API will use.
4. [x] **Docker Compose + Alembic baseline:** `docker-compose.yml`, `backend/migrations/`
   The first Alembic revision applies `db/schema.sql`. Add `make db-reset` (drop, migrate, seed).
   *Done when:* a fresh clone can run `docker compose up -d && make db-reset && pytest -q` with every test passing.

## Phase 2: Backend (FastAPI)

5. [x] **App skeleton + `get_tenant_db`:** `backend/app/main.py`, `backend/app/db.py`, `backend/app/config.py` (`a9fe9da`)
   This is the single place that sets `SET LOCAL ROLE` and the `app.*` context. Also add a `GET /health` endpoint.
   *Test:* after a request finishes, the next transaction on the same pooled connection sees an empty `app.agency_id`. This proves no context leaks between requests.
6. [x] **Auth: login, agency selection, `/me`:** `backend/app/auth/` (`aaa5cef..b347cd9`)
   bcrypt hashing, plus real hashes in the seed (replace the placeholder). Endpoints: `POST /auth/login`, `POST /auth/portal/login`, `POST /auth/session`, `GET /me`. Staff and portal logins each list only their kind of membership.
   *Tests:* Ravi logs in once and sees two memberships; the session token works only for the chosen agency; a removed membership gets 401 on the next request.
7. [x] **Invites:** `routers/invites.py`, `services/invites.py` (`91fa0cb..fc0f87e`)
   Create, resend (upsert), revoke, and accept (through `app.accept_invite` as `agencydesk_auth`). Accepting as an existing user requires being logged in as that email.
   *Tests:* resend makes no duplicate and the old link stops working; two simultaneous accepts over HTTP produce one account; a non-admin gets 403.
8. [x] **Clients, projects, project members:** `routers/projects.py` (`ca1ccf7..197ed79`)
   Admin writes; reads are scoped by RLS.
   *Tests:* another tenant gets 404 by ID; a member sees only assigned projects; `DELETE /projects/{id}/members/{uid}` unassigns that person's tasks and logs the event, checked over HTTP.
9. [x] **Tasks: list/filter/search, create, update:** `routers/tasks.py`, `schemas/tasks.py`
   Use separate `StaffTask` and `ClientTask` response models. Support `?status=&priority=&assignee=&q=`.
   *Tests:* a client using `?q=` or `?status=` never gets an internal task; a client's create or status change fails; assigning someone outside the project gets 422.
10. [ ] **Comments:** `routers/comments.py`
    A client's POST always gets `visibility=client`.
    *Tests:* a client never sees internal comments; flipping a task to internal hides its comments from the client.
11. [ ] **Files: upload, download, review:** `routers/files.py`, `services/storage.py`
    Local-disk storage behind an interface. Downloads check the file row under RLS first, then stream it. Clients use `POST /files/{id}/review {decision}`.
    *Tests:* a client can't download an internal file by ID (404); a client can review only client-visible files; a client can't rename a file.
12. [ ] **Time entries + hours summary:** `routers/time.py`
    Staff log their own time. Clients never receive raw entries.
    *Tests:* a client gets 404 on time entry endpoints; staff and client hour totals differ correctly.
13. [ ] **Project dashboard:** `GET /projects/{id}/dashboard`
    Task counts by status plus `app.project_hours()`.
    *Tests:* the same project returns different numbers for staff and client, and both match the seed.

## Phase 3: Frontend (React + TS + Vite)

14. [ ] **Scaffold + API client + auth flow:** `frontend/`
    Login → agency picker (for multi-agency users) → app. Separate route trees: `/` for staff and `/portal` for clients. The token is held in memory or an httpOnly cookie, not localStorage.
15. [ ] **Staff screens**
    Project list, task board grouped by status, task drawer (comments with the visibility toggle, files, time log), project members, invites.
16. [ ] **Portal screens**
    My projects, client-visible tasks, commenting, approve / request changes on files, dashboard.

## Phase 4: Ship

17. [ ] **README + DESIGN.md final pass**
    README.md is drafted (setup, demo accounts, tests, layout, status) and DESIGN.md is trimmed to half a page. Final pass: add frontend setup, re-check the 10-minute setup from a fresh clone, and update Status.
18. [ ] **Walkthrough video (3–5 min)**
    Covers the app, the schema and the isolation tests.

### Bonus (only after step 18 is done)

19. [ ] Client intake forms (`intake_forms`, `intake_submissions`, both tenant tables with RLS)
20. [ ] Notifications via an outbox table, with recipients filtered by the same visibility rules

---

## Bugs found during the build

Each real bug found while building: what happened, the root cause, the fix, and the commit.

| # | Step | Symptom | Root cause | Fix (commit) |
|---|---|---|---|---|
| 1 | 3 | `app.accept_invite` failed: "column reference agency_id is ambiguous" | The function's `RETURNS TABLE` output columns share names with table columns, and PL/pgSQL can't tell which one `ON CONFLICT (agency_id, user_id)` means | Renamed the outputs to `out_*` and used `ON CONFLICT ON CONSTRAINT agency_memberships_pkey` |
| 2 | 5 | `client_user` memberships not found by `get_tenant_db` (401 for every client) | `agency_memberships` read policy needs `app.client_id`, which is only known after the lookup; DB tests missed it because they look up as `postgres` | Own-row branch `OR user_id = app.user_id()` in the read policy, migration 0002 (`a9fe9da`) |
| 3 | 7 | Anyone holding an invite link could attach an existing account to the agency without that user logging in | `app.accept_invite` reused an existing user on `ON CONFLICT (email)` with no check on who was accepting | `p_acting_user` parameter; existing account requires the caller to be logged in as it, checked inside the locked step (migration 0003) |
| 4 | 7 | `alembic upgrade` failed: "value too long for type character varying(32)" | Revision ID `0003_accept_invite_requires_login` exceeds `alembic_version.version_num` length | Shortened the revision ID to `0003_accept_invite_login` |
| 5 | 8 | DB rule tests failed after the API tests ran (unexpected projects/tasks in seed data) | API tests commit through the real endpoints, and all test modules share one `ad_test` database | `test_api.py` rebuilds `ad_test` from schema + seed when the module finishes (`build_test_database`) |

## Status

- Phase 1 complete (steps 1–4).
- Phase 2: steps 5–9 complete. 110 tests passing (26 DB rules, 2 migrations, 82 API).
- Next: step 10 (comments).
