# AgencyDesk

A project management app for agencies and their clients. Many agencies share one app, but each agency only ever sees its own data. Agency staff manage clients, projects, tasks, files and time. Clients log in to a separate portal and see only the work shared with them.

The main goal is that these rules can't be broken. The database itself enforces them, and tests prove it. See **[DESIGN.md](DESIGN.md)** for how.

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

- **Ports:** Postgres uses port **5433**, so it won't clash with a Postgres you already run on 5432. The frontend passes `/api/*` calls to the API, so no CORS setup is needed.
- **Refreshing the page logs you out.** Login tokens are kept in memory only, never saved in the browser.
- **To reset the demo data,** run `make db-reset` again.

Setup takes about 2 minutes on a machine that has already downloaded Docker and package files, and a few more on a new machine.

## Demo accounts

Every account's password is `password`.

| Email                | Agency                              | Role                                | Logs in at      |
| -------------------- | ----------------------------------- | ----------------------------------- | --------------- |
| `alice@pixel.test`   | Pixel Studio                        | agency_admin                        | `/login`        |
| `mark@pixel.test`    | Pixel Studio                        | agency_member (Acme project)        | `/login`        |
| `nina@pixel.test`    | Pixel Studio                        | agency_member (Acme project)        | `/login`        |
| `bob@northwind.test` | Northwind Labs                      | agency_admin                        | `/login`        |
| `ravi@acme.test`     | Pixel Studio **and** Northwind Labs | client_user at both (Acme, Initech) | `/portal/login` |

Ravi is the "one person, two agencies" case: one account and one password, with separate access to each agency. Pixel's demo data mixes internal and client-visible tasks, comments and files, so you can compare what Alice sees with what Ravi sees.

## A five-minute tour

Use a normal browser window for staff and a private window for the client, so both can stay logged in.

1. **Internal vs client view.** As Alice, open _Acme website redesign_: 3 tasks and 5 hours, including the internal "Fix our staging budget overrun". As Ravi (portal, pick Pixel Studio), the same project shows 2 tasks and 3 hours, and searching "budget" finds nothing.
2. **Comments and files.** As Alice, open _Homepage mockups_: an internal comment, an internal file, and badges saying what the client actually sees. Ravi sees only the client comment and `homepage-v2.fig`. Ravi clicks **Approve**, and Alice's drawer now shows "Approved by client".
3. **Hiding a task.** As Alice, set _Content migration_ to Internal. It disappears from Ravi's portal, together with its comments and files.
4. **One person, two agencies.** Ravi signs in once and picks an agency. **Switch agency** moves him to Northwind, where he sees only Initech's project.
5. **Removing a member mid-task.** As Alice, open the **Team** tab and remove Nina. The app reports her 2 tasks were unassigned; their status and logged time are untouched.
6. **Invites.** As Alice, go to **Invites**, invite a new email as a client of Acme, and open the link in a private window to create the account. Opening the same link again is refused.

## Run the tests

```bash
make test        # backend: 157 tests against a real Postgres
make web-check   # frontend: typecheck, 40 unit/component tests, production build
make check       # both
```

The backend tests create and delete their own databases (`ad_test*`), so your demo data is never touched. They run against a real Postgres, not a fake one, because Postgres is what enforces the access rules.

| File                       | What it proves                                                                                                                                                                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_db_rules.py`   | Agencies can't see each other's data, clients can't see internal content, and the edge cases hold. Checked directly in Postgres, as the same database role the API uses. Also fails if a new agency table is added without its security rules. |
| `tests/test_api.py`        | The same rules through every API endpoint: another agency gets 404, clients never see internal content (including through search, filters, counts and downloads), and each role can only do what it should.                                    |
| `tests/test_migrations.py` | The database migrations build exactly the schema in `db/schema.sql`, and can be undone and redone cleanly.                                                                                                                                     |
| `frontend/src/**/*.test.*` | The API client, login state, and safe defaults (new comments and files start as internal). Also checks that tokens are never saved in the browser and that the client portal never uses staff code.                                            |

API tests are named after the five edge cases (`test_cross_tenant_*`, `test_internal_content_leaking_to_clients_*`, `test_one_person_in_two_agencies_*`, `test_invite_races_*`, `test_removing_member_mid_task_*`). The database tests are grouped the same way.

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
db/schema.sql          The full database design: tables, rules, security (RLS) policies, triggers
db/seed.sql            Demo data (2 agencies, shared-email user, internal + client-visible content)
db/dev_roles.sql       Local-only passwords for the DB roles (never use in production)
backend/app/
  db.py                get_tenant_db: the one place each request tells the database who is asking
  auth/                Passwords, tokens, login, agency selection, invite acceptance
  routers/             Thin HTTP layer
  services/            Business rules (and file storage)
  repositories/        Database queries (the database adds the agency filter itself)
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
DESIGN.md              How agencies are kept apart, what clients can see, and how logins work
ROADMAP.md             Build order
AGENTS.md              Rules for AI coding assistants working in this repo
```

## Status

Still to do (optional bonus items):

- Client intake forms
- Notifications

[ROADMAP.md](ROADMAP.md) has the full build history.

## Known limits

- **Refreshing the page logs you out.** Tokens are kept in memory so other scripts on the page can't read them. Storing them in a secure cookie would fix this, but would need extra protection against cross-site requests (CSRF).
- **No email sending.** Creating an invite shows the admin a one-time link to pass on.
- **Files are stored on the local disk.** The storage code is kept separate, so S3 or similar could replace it easily.
- **No rate limiting** on login yet.
- **Tasks, comments, files and time entries can't be deleted,** and comments can't be edited after posting. For time entries this is on purpose, since reports depend on them.
