# AgencyDesk — Design

## 1. How the schema keeps agencies apart

Every table holding agency data has an `agency_id`. A row points to its parent by agency *and* id, e.g. `tasks (agency_id, project_id) → projects (agency_id, id)`, so the database refuses to store a Northwind task under a Pixel project, even if the code has a bug.

Postgres Row-Level Security (RLS) then filters every query by agency. The API connects as a database role that cannot skip RLS. At the start of each request, one function (`get_tenant_db`) tells the database who is asking (agency, user, role, client), reading this from the user's membership, never from the request. `SET LOCAL` clears it when the request ends. Guessing another agency's ID gets a 404.

## 2. How a client is blocked from internal content

Tasks, comments and files have a `visibility`: `internal` (default) or `client`. A client sees a comment or file only if both it and its task are `client`, so hiding a task hides everything on it. The rule lives in RLS read policies, not in each endpoint, so lists, search, filters, downloads and dashboard counts all follow it. Clients cannot create tasks or change status; they can only post `client` comments and approve client-visible files. Time-entry notes stay internal; clients see only hour totals.

## 3. One person in two agencies

A person has one `users` row: one email, one password. Their access lives in `agency_memberships`, one row per agency, with their role there (and their client, for client users). Ravi, for example, is a client at both Pixel and Northwind. He logs in once, picks an agency, and gets a session valid only for that agency; switching gives a new session. Every request re-checks the membership, so removed access stops at once.

## 4. Edge case I'm proud of: removing a member mid-task

A task can only be assigned to a current member of its project: a foreign key from the task to `project_members` enforces it. Removing someone from a project therefore unassigns their tasks automatically (`ON DELETE SET NULL`), keeps status and logged time, and a trigger records why. No code path can leave a task assigned to someone who lost access.

Invite races are handled too: a resend updates the same invite row, and accepting locks it, so two clicks create one account. Everything above is proven by tests against the real database (`tests/test_db_rules.py`, `tests/test_api.py`).
