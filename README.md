# AgencyDesk

A multi-tenant client and project management app for agencies. One deployment serves many agencies. Each agency manages its own clients, projects, tasks, files and time entries, and invites clients into a portal where they see only their own client-visible work.

The focus is **data modelling and access-control correctness**. Tenant isolation and client visibility are enforced by PostgreSQL itself, through composite foreign keys and Row-Level Security, and proven by tests. See **[DESIGN.md](DESIGN.md)** for how it works.

**Stack:** PostgreSQL 16 · Python 3.12 + FastAPI + SQLAlchemy + Alembic · React + TypeScript + Vite

---

## Run it

**Requirements:** Docker, Python 3.12+, Node 22+, `make`.

```bash
git clone https://github.com/sp4chi/agencydesk.git
cd agencydesk

make install       # create .venv and install backend dependencies
make env           # create .env with a random SESSION_SECRET
make db-reset      # start Postgres in Docker (host port 5433), run migrations, load seed data
make web-install   # install frontend dependencies
```

Then, in two terminals:

```bash
make run           # API on http://localhost:8000  (interactive docs at /docs)
make web           # app on http://localhost:5173
```

Open **http://localhost:5173** for the staff app, or **http://localhost:5173/portal/login** for the client portal.

- **Ports:** Postgres runs on host port **5433**, so it doesn't clash with a local Postgres on 5432. The frontend forwards `/api/*` to the API, so there's no CORS to set up.
- **Refreshing logs you out.** Session tokens are kept in memory only, never in browser storage.
- **Resetting the demo data:** run `make db-reset` again.

From a fresh clone, setup plus `make check` took about 1.5 minutes on a machine that already had the Docker image and package caches; allow a few more minutes on a brand-new machine for the downloads.

## Demo accounts

Every account's password is `password`.

| Email                | Agency                              | Role                                | Logs in at     |
| -------------------- | ----------------------------------- | ----------------------------------- | -------------- |
| `alice@pixel.test`   | Pixel Studio                        | agency_admin                        | `/login`        |
| `mark@pixel.test`    | Pixel Studio                        | agency_member (Acme project)        | `/login`        |
| `nina@pixel.test`    | Pixel Studio                        | agency_member (Acme project)        | `/login`        |
| `bob@northwind.test` | Northwind Labs                      | agency_admin                        | `/login`        |
| `ravi@acme.test`     | Pixel Studio **and** Northwind Labs | client_user at both (Acme, Initech) | `/portal/login` |

Ravi is the "one person, two agencies" case: one account, one password, a separate membership in each agency. Pixel's seed data has both internal and client-visible tasks, comments and files, so you can compare what Alice sees with what Ravi sees.

## A five-minute tour

Use a normal window for staff and a private window for the client, so both stay signed in.

1. **Internal vs client view.** As Alice, open *Acme website redesign*: 3 tasks and 5 hours, including the internal "Fix our staging budget overrun". As Ravi (portal, pick Pixel Studio), the same project shows 2 tasks and 3 hours, and searching "budget" finds nothing.
2. **Comments and files.** As Alice, open *Homepage mockups*: an internal comment, an internal file, and badges saying what the client actually sees. Ravi sees only the client comment and `homepage-v2.fig`. Ravi clicks **Approve**, and Alice's drawer now shows "Approved by client".
3. **Hiding a task.** As Alice, set *Content migration* to Internal. It disappears from Ravi's portal, together with its comments and files.
4. **One person, two agencies.** Ravi signs in once and picks an agency. **Switch agency** moves him to Northwind, where he sees only Initech's project.
5. **Removing a member mid-task.** As Alice, open the **Team** tab and remove Nina. The app reports her 2 tasks were unassigned; their status and logged time are untouched.
6. **Invites.** As Alice, go to **Invites**, invite a new email as a client of Acme, and open the link in a private window to create the account. Opening the same link again is refused.

## Run the tests

```bash
make test        # backend: 157 tests against a real Postgres
make web-check   # frontend: typecheck, 40 unit/component tests, production build
make check       # both
```

The backend tests create and drop their own databases (`ad_test*`), so they never touch your dev data. Nothing in them mocks the database: access rules are Postgres's job, so the tests check Postgres.

| File                       | What it proves                                                                                                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/test_db_rules.py`   | Tenant isolation, client visibility and the edge cases, checked directly against Postgres as the same role the API uses. Also fails if any table with an `agency_id` is missing RLS.             |
| `tests/test_api.py`        | The same rules over HTTP for every endpoint: another tenant gets 404, clients never see internal content (including via search, filters, counts and downloads), and role rules hold.             |
| `tests/test_migrations.py` | Alembic migrations produce exactly `db/schema.sql`, and downgrade/upgrade round-trips.                                                                                                           |
| `frontend/src/**/*.test.*` | API client behaviour, the login/session state, UI defaults (new comments and files start internal), and guards: no tokens in browser storage, and portal code never uses staff code or staff API calls. |

API tests are named after the five edge cases (`test_cross_tenant_*`, `test_internal_content_leaking_to_clients_*`, `test_one_person_in_two_agencies_*`, `test_invite_races_*`, `test_removing_member_mid_task_*`); the DB rule tests are grouped under one heading per edge case.

## Try the API

```bash
# 1. Log in. Returns an identity token and the agencies you belong to.
curl -s localhost:8000/auth/portal/login -H 'content-type: application/json' \
  -d '{"email":"ravi@acme.test","password":"password"}'

# 2. Pick an agency. Returns a session token scoped to that one membership.
curl -s localhost:8000/auth/session -H "authorization: Bearer <identity_token>" \
  -H 'content-type: application/json' -d '{"agency_id":"aaaaaaaa-0000-0000-0000-000000000001"}'

# 3. Every other endpoint uses the session token.
curl -s localhost:8000/me -H "authorization: Bearer <session_token>"
```

Staff log in with `POST /auth/login`; clients use `POST /auth/portal/login`. The full list is at http://localhost:8000/docs.

## Project layout

```
db/schema.sql          Source of truth: tables, constraints, RLS policies, triggers, functions
db/seed.sql            Demo data (2 agencies, shared-email user, internal + client-visible content)
db/dev_roles.sql       Local-only passwords for the DB roles (never use in production)
backend/app/
  db.py                get_tenant_db: the one place each request's tenant context is set
  auth/                Passwords, tokens, login, agency selection, invite acceptance
  routers/             Thin HTTP layer
  services/            Business rules (and file storage)
  repositories/        SQL (no tenant filters needed; RLS applies them)
  schemas/             Pydantic request/response models (separate Staff* and Client* shapes)
backend/migrations/    Alembic (0001 = baseline schema, then one revision per change)
frontend/src/
  api/client.ts        The only module that calls the API
  auth/                In-memory session, route guard
  staff/               Staff app: projects, task board, task drawer, team, invites
  portal/              Client portal: projects, shared tasks, file approval, conversation
  shared/              Login, agency picker, invite acceptance
tests/                 DB-level, API-level and migration tests
scripts/               make env and seed-file helpers
DESIGN.md              How isolation, visibility and identity work
ROADMAP.md             Build order and status
AGENTS.md              Rules for AI coding assistants working in this repo
```

## Status

The required scope is complete. [ROADMAP.md](ROADMAP.md) has the step-by-step history, with commits and the bugs found along the way.

| Area | State |
| ---- | ----- |
| Database: schema, RLS policies, triggers, seed, migrations | Done |
| API: auth, invites, clients, projects, members, tasks, comments, files, time, dashboard | Done |
| Staff app: projects, task board, task drawer, team, invites | Done |
| Client portal: projects, shared tasks, file approval, conversation | Done |
| Tests | 157 backend (26 DB rules, 2 migrations, 129 API) + 40 frontend, all passing |
| Setup from a fresh clone | Verified: setup + `make check` in about 1.5 minutes (warm caches) |
| Walkthrough video | To do |
| Bonus: client intake forms, notifications | Not started |

## Known limits

- **Sessions don't survive a page refresh.** Tokens live in memory to keep them away from scripts. An httpOnly cookie would fix this, at the cost of CSRF protection.
- **No email sending.** Creating an invite shows the admin a one-time link to pass on.
- **Files live on local disk** behind a small storage interface; S3 or similar would slot in there.
- **No rate limiting** on login yet.
- **No delete endpoints for tasks, comments, files or time entries.** For time entries that's by design (they feed reporting). Comments also can't be edited after posting.

## How I used AI

I used an AI coding assistant for explanations, scaffolding and boilerplate. The schema, the isolation model and the edge-case decisions are mine. `AGENTS.md` sets the security rules the assistant had to follow, for example never disabling RLS and never taking `agency_id` from the request. Every one of those rules is enforced by the database and checked by the tests above.
