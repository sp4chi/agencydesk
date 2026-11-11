# AGENTS.md — AgencyDesk

Instructions for coding agents working in this repo. Read this file fully before changing anything. `DESIGN.md` explains the reasoning behind the isolation rules. `README.md` is the public setup guide for people running the project.

## What this project is

AgencyDesk is a multi-tenant client and project management app. One deployment serves many agencies. Each agency manages its own clients, projects, tasks, files and time entries, and invites clients into a portal.

The priority is **tenant isolation, access control correctness and schema design**, not how many screens exist. Correctness beats features. When unsure, choose the more restrictive behaviour.

## How to work through the build

Follow `ROADMAP.md` in order:
- Do **one step per task and one commit per step**, with a message like `Implement <thing>`.
- Don't start a step until the previous one is runnable and its tests pass.
- When a step lands, tick its box, add the commit hash, and update the Status section.
- In the same commit, update `README.md` if the step changed setup, `make` commands, environment variables, endpoints, demo accounts, the project layout or the Status section.
- If you hit a real bug, add a row to "Bugs found during the build".
- Don't jump ahead to later steps or bonus items unless asked.

## Stack

- **Database:** PostgreSQL 15+ (needed for `ON DELETE SET NULL (column)`)
- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.0 (Core-style queries), psycopg 3, Alembic, Pydantic v2, pytest
- **Frontend:** React + TypeScript + Vite, with two route trees: staff app (`/`) and client portal (`/portal`)

## Layout

```
db/schema.sql            # source of truth for the schema, RLS policies, triggers, functions
db/seed.sql              # 2 agencies, shared-email user, internal + client-visible content
tests/test_db_rules.py   # DB-level proof of isolation & visibility (must always pass)
backend/app/
  main.py
  db.py                  # engine + get_tenant_db dependency (ONLY place request context is set)
  auth/                  # password hashing, tokens, login, select-agency, invites
  routers/               # thin HTTP layer
  services/              # business rules, validation
  repositories/          # SQL only
  schemas/               # Pydantic models; separate Staff* and Client* response models
backend/migrations/      # Alembic; the first revision applies db/schema.sql
frontend/
README.md                # setup, demo accounts, tests, layout, status (keep current)
DESIGN.md                # required design write-up (keep to about half a page)
ROADMAP.md               # build order + status
```

Some of `backend/` and `frontend/` may not exist yet. Create them following this layout.

## Commands

```bash
make install     # create .venv and install backend deps (Python 3.12+)
make env         # create .env from .env.example with a random SESSION_SECRET
make db-reset    # start Postgres in Docker (host port 5433), drop + recreate `agencydesk`,
                 # alembic upgrade head, load db/seed.sql + db/dev_roles.sql
make migrate     # alembic upgrade head only
make run         # API on http://localhost:8000 (uvicorn app.main:create_app --factory)
make test        # pytest -q; tests create/drop their own databases (ad_test*)
```

Defaults match `docker-compose.yml`; override with the variables in `.env.example`
(`MIGRATION_DATABASE_URL` / `API_DATABASE_URL` are SQLAlchemy URLs; `DATABASE_URL` / `ADMIN_DATABASE_URL` are libpq conninfo strings for the tests).
The app refuses to start without a real `SESSION_SECRET`. `db/dev_roles.sql` sets dev-only passwords for `agencydesk_api` / `agencydesk_auth`; never run it in production.

Migrations: `backend/migrations/versions/`. Revision `0001_baseline` runs a frozen copy of `db/schema.sql`.
New schema changes go in `db/schema.sql` **and** a new revision; `tests/test_migrations.py` fails if they drift.

Add the frontend commands here once they exist.

---

## Non-negotiable security invariants

Breaking any of these is a failed task, even if the feature works.

1. **Every tenant table has `agency_id NOT NULL` and `UNIQUE (agency_id, id)`.** Children reference parents with composite foreign keys `(agency_id, parent_id) → parent(agency_id, id)`. Never add a single-column FK from one tenant table to another.
2. **Every tenant table has RLS enabled and a `RESTRICTIVE` policy named `tenant`.** The test `test_every_table_with_agency_id_has_rls_and_a_tenant_policy` enforces this. Don't weaken or skip it.
3. **The API connects as `agencydesk_api`**, a non-owner role, so RLS applies. Never run request queries as the table owner or a superuser. Never grant `BYPASSRLS` to the API role.
4. **Request context is set in exactly one place:** `get_tenant_db` in `backend/app/db.py`. It does the following:
   - verifies the session token
   - re-loads the membership from `agency_memberships` (`removed_at IS NULL`) and returns 401 if it's gone
   - opens a transaction
   - runs `SET LOCAL ROLE agencydesk_api`
   - calls `set_config('app.agency_id' | 'app.user_id' | 'app.role' | 'app.client_id', value, true)`

   Use `SET LOCAL` / `is_local = true` only, never plain `SET`, because pooled connections are reused across requests. Never call `set_config('app.*')` anywhere else.
5. **The agency, user, role and client come from the server-side membership lookup, never from the URL, query string, body or headers.** Routes must not accept `agency_id` as input.
6. **Repositories must not rely on their own `WHERE agency_id = …` for security.** Adding one for index use is fine; RLS is the guarantee. Never "fix" a missing-row bug by switching to the owner connection.
7. **Visibility defaults to `internal`.** A comment or file is client-visible only if *both* it and its task are `client`. Never add a client-facing query path that bypasses RLS. That includes raw SQL through `agencydesk_auth`, the owner, or a `SECURITY DEFINER` function that doesn't re-check `app.can_see_task` / `app.can_access_project`.
8. **Clients never receive internal data in any form.** That covers rows, counts, hours, time entry notes, `task_events`, file URLs, error messages and autocomplete results. Use `Client*` Pydantic response models that omit staff-only fields.
9. **Return 404 (not 403) for rows the caller can't see**, so the response doesn't reveal that the row exists.
10. **`agencydesk_auth` (which has BYPASSRLS) is used only by login, agency selection and `app.accept_invite`.** No other code path may use it.
11. **Secrets:** store invite tokens and session secrets hashed (SHA-256 for invite tokens, bcrypt or argon2 for passwords). Never log tokens, password hashes or full emails with their tokens.

## Domain rules (already enforced in the DB; keep the API consistent)

| Role | Can see | Can write |
|---|---|---|
| `agency_admin` | everything in their agency | everything in their agency, including invites and project membership |
| `agency_member` | projects they're in (`project_members`), including internal content | tasks, comments, files and their own time entries on those projects |
| `client_user` | their own client's projects, and only client-visible tasks, comments and files | comments (always `visibility='client'`) and file approval decisions; **no** task creation or status changes |

- **One person in several agencies:** there is one `users` row per email and one `agency_memberships` row per agency. After login, the user picks a membership and the session token is scoped to it. Switching agencies means issuing a new token.
- **Invites:** create and resend with `INSERT … ON CONFLICT (agency_id, email) WHERE status='pending' DO UPDATE` (this replaces the token hash). Accept only through `app.accept_invite`. If the email already has an account, require the user to be logged in as that email before attaching the membership.
- **Removing a member from a project:** delete the `project_members` row. The FK clears their task assignments and a trigger logs `auto_unassigned_member_removed`. Don't reimplement this in Python. Removing someone from the agency means setting `removed_at` and deleting their `project_members` rows; never hard-delete memberships.
- **Time:** stored as integer minutes (1–1440 per entry). Clients get totals only, through `app.project_hours()`.
- **Files:** approval is allowed only on client-visible files. Clients may change only `approval_status` and `reviewed_by` (the trigger enforces this). Downloads go through an endpoint that first reads the file row under RLS, then streams or returns a short-lived signed URL. Storage must never be public.

## Changing the schema

Every schema change must do all of the following:
1. Edit `db/schema.sql` **and** add an Alembic migration that matches it.
2. For a new tenant table, add:
   - `agency_id NOT NULL`
   - `UNIQUE (agency_id, id)`
   - composite FKs
   - an index whose first column is `agency_id`
   - `ENABLE ROW LEVEL SECURITY`
   - the restrictive `tenant` policy (add the table to the `DO $$ … FOREACH` list)
   - per-command permissive policies
   - grants to `agencydesk_api`
3. For a new child of `tasks`: give it a `visibility` column if clients could ever see it, and a read policy using `app.can_see_task(task_id) AND (app.is_staff() OR visibility = 'client')`.
4. Prefer `CHECK` constraints over Postgres enums for status-like columns.
5. `SECURITY DEFINER` functions must have `SET search_path = public, pg_temp` and filter by `app.agency_id()` themselves.
6. Update `db/seed.sql` and the tests in the same change.

## Tests (definition of done)

A change is done only when:
- `pytest -q tests/` passes, with no skipped or deleted assertions.
- Any new endpoint has an API-level test (`tests/test_api.py`, using FastAPI's `TestClient` against a real Postgres, not mocks) proving:
  - another tenant gets **404** for it, by ID
  - a `client_user` can't see or change internal content through it, including via `?q=` search and filter params
  - the role rules in the table above hold
- New behaviour on the five key edge cases has a test named after the edge case:
  - cross-tenant access
  - internal content leaking to clients
  - one person in two agencies
  - invite races
  - removing a member mid-task
- Never mock the database to test access rules. Their whole point is that Postgres enforces them.

## README rules

- Setup must stay under 10 minutes from a fresh clone. If a step adds a dependency or setup command (e.g. the frontend), add it to "Run it" and check that it still works from a clean checkout.
- The demo accounts table must match `db/seed.sql`.
- The "Status" section describes only what actually works. Don't list unbuilt features as done.
- Don't edit the "How I used AI" section; the author maintains it.
- Keep `DESIGN.md` to about half a page. Put setup details in the README, not in DESIGN.md.

## Code style

- **Python:** type hints everywhere. Routers stay thin: parse the request, call a service, return a schema. Services hold the rules. Repositories hold the SQL. No business logic in routers, no HTTP concepts in services.
- Use explicit SQL or SQLAlchemy Core, not lazy-loaded ORM relationships, which hide queries.
- Pydantic: separate input models (`TaskCreate`, `TaskUpdate`) and output models (`StaffTask`, `ClientTask`). Never return ORM rows or dicts directly.
- **Errors:** map RLS denial (`InsufficientPrivilege`) to 403 on writes. Map not-found-under-RLS to 404. Map unique/FK violations to 409/422 with a safe message that never echoes another tenant's data.
- **Frontend:** TypeScript strict mode. Put the API client in one module, and keep staff and portal pages separate. The UI hiding something is never the security boundary; the backend must enforce every rule.
- Keep the code readable over clever.

## Don't

- Don't disable RLS, add `FORCE`/`NO FORCE` tweaks, or switch roles to make a test pass.
- Don't add `agency_id` to request bodies or URLs.
- Don't add catch-all permissive policies (`USING (true)`).
- Don't hard-delete users, memberships or time entries.
- Don't introduce a second way to set request context, a global DB session, or a module-level connection.
- Don't add features outside scope (CRM, invoicing, Gantt build) unless asked. Bonus items (intake forms, notifications) come only after the required scope and tests are done.
- Don't commit `.env`, real secrets or uploaded files.
- Don't add `Co-Authored-By` trailers or tool attribution lines to commit messages.

## When in doubt

Stop and ask rather than guess if a change would:
- touch RLS policies, roles or grants
- touch `get_tenant_db`
- touch `app.accept_invite`
- change a rule in the role table

Explain the trade-off and propose the most restrictive option.
