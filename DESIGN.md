# AgencyDesk — Design

**Tenant isolation.** Every tenant table carries `agency_id` and `UNIQUE (agency_id, id)`. Children reference parents by the pair (`tasks (agency_id, project_id) → projects (agency_id, id)`), so a row cannot point across agencies even if application code is wrong. Postgres Row-Level Security adds a `RESTRICTIVE` policy, `agency_id = app.agency_id()`, on every tenant table. The API runs as a non-owner role. In one place (`get_tenant_db`), it `SET LOCAL`s the agency, user, role and client loaded from the caller's membership. A query that forgets a filter, or guesses another tenant's UUID, gets zero rows, and the API answers 404.

**Blocking clients from internal content.** Tasks, comments and files carry `visibility ∈ {internal, client}`, defaulting to `internal`. A child is client-visible only if both it and its task are `client`. The rule lives in RLS read policies, so list, search, filters, comments and dashboard counts all inherit it. Clients have no write policy on tasks. They may only add `client` comments, and a trigger limits their file updates to approval fields. Raw time entries are staff-only; clients get totals through `app.project_hours()`. Responses use separate `Staff*` and `Client*` models, so internal fields can't leak either.

**One person, two agencies.** `users` has one row per email. `agency_memberships (agency_id, user_id, role, client_id)` holds the role in each agency. After login the user picks a membership, and the session is scoped to it. Every request re-reads the membership, so removal takes effect immediately.

**Invite races.** A partial unique index allows one pending invite per (agency, email), so a resend replaces the token hash on the same row and the old link dies. `app.accept_invite` locks the invite row, so two simultaneous accepts produce exactly one account. If the email already has an account, the caller must be logged in as it, checked inside the same locked step.

**Edge case: removing a member mid-task.** `tasks (agency_id, project_id, assignee_user_id)` references `project_members` with `ON DELETE SET NULL (assignee_user_id)`. The assignee is therefore always a current project member. Removing someone unassigns only their tasks, keeps status and time entries, and a trigger logs the change.

All rules are proven against the real API role: in Postgres (`tests/test_db_rules.py`) and over HTTP (`tests/test_api.py`).
