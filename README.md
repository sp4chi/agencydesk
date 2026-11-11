# AgencyDesk

A multi-tenant client and project management app for agencies. One deployment serves many agencies. Each agency manages its own clients, projects, tasks, files and time entries, and invites clients into a portal where they see only their own client-visible work.

The focus is **data modelling and access-control correctness**. Tenant isolation and client visibility are enforced by PostgreSQL itself, through composite foreign keys and Row-Level Security, and proven by tests. See **[DESIGN.md](DESIGN.md)** for how it works.

**Stack:** PostgreSQL 16 · Python 3.12 + FastAPI + SQLAlchemy + Alembic · React + TypeScript (frontend in progress)

---

## Run it

**Requirements:** Docker, Python 3.12+, `make`.

```bash
git clone https://github.com/sp4chi/agencydesk.git
cd agencydesk

make install    # create .venv and install backend dependencies
make env        # create .env with a random SESSION_SECRET
make db-reset   # start Postgres in Docker (host port 5433), run migrations, load seed data
make run        # API on http://localhost:8000  (interactive docs at /docs)
```

Postgres runs on host port **5433**, so it doesn't clash with a local Postgres on 5432.

## Run the tests

```bash
make test
```

The tests create and drop their own databases (`ad_test*`), so they never touch your dev data.

| File                       | What it proves                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/test_db_rules.py`   | Tenant isolation, client visibility and the edge cases, checked directly against Postgres as the same role the API uses. Also fails if any table with an `agency_id` is missing RLS. |
| `tests/test_api.py`        | The same rules over HTTP: tokens, agency selection, membership re-checks, and no request context leaking through the connection pool.                                                |
| `tests/test_migrations.py` | Alembic migrations produce exactly `db/schema.sql`, and downgrade/upgrade round-trips.                                                                                               |

## Demo accounts

Every account's password is `password`.

| Email                | Agency                              | Role                                | Logs in through |
| -------------------- | ----------------------------------- | ----------------------------------- | --------------- |
| `alice@pixel.test`   | Pixel Studio                        | agency_admin                        | staff app       |
| `mark@pixel.test`    | Pixel Studio                        | agency_member (Acme project)        | staff app       |
| `nina@pixel.test`    | Pixel Studio                        | agency_member (Acme project)        | staff app       |
| `bob@northwind.test` | Northwind Labs                      | agency_admin                        | staff app       |
| `ravi@acme.test`     | Pixel Studio **and** Northwind Labs | client_user at both (Acme, Initech) | client portal   |

Ravi is the "one person, two agencies" case: one account, one password, a separate membership in each agency. Pixel's seed data has both internal and client-visible tasks, comments and files, so you can compare what Alice sees with what Ravi sees.

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

Staff log in with `POST /auth/login`; clients use `POST /auth/portal/login`.

## Project layout

```
db/schema.sql          Source of truth: tables, constraints, RLS policies, triggers, functions
db/seed.sql            Demo data (2 agencies, shared-email user, internal + client-visible content)
db/dev_roles.sql       Local-only passwords for the DB roles (never use in production)
backend/app/
  db.py                get_tenant_db: the one place each request's tenant context is set
  auth/                Passwords, tokens, login, agency selection
  routers/             Thin HTTP layer
  services/            Business rules
  repositories/        SQL (no tenant filters needed; RLS applies them)
  schemas/             Pydantic request/response models
backend/migrations/    Alembic (0001 = baseline schema)
tests/                 DB-level, API-level and migration tests
DESIGN.md              How isolation, visibility and identity work
ROADMAP.md             Build order and current status
AGENTS.md              Rules for AI coding assistants working in this repo
```

## Status

Database, migrations, app skeleton and authentication are in place. Task, comment, file, time-tracking and dashboard endpoints and the React frontend are next. See [ROADMAP.md](ROADMAP.md) for the step-by-step status.

## How I used AI

I used an AI coding assistant for explanations, scaffolding and boilerplate. The schema, the isolation model and the edge-case decisions are mine. `AGENTS.md` sets the security rules the assistant had to follow, for example never disabling RLS and never taking `agency_id` from the request. Every one of those rules is enforced by the database and checked by the tests above.
