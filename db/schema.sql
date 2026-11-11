-- =====================================================================
-- AgencyDesk schema (PostgreSQL 15+; uses ON DELETE SET NULL (col) syntax)
--
-- Three layers of protection, outermost first:
--   1. Composite foreign keys: every child row carries agency_id and
--      references its parent by (agency_id, id). A row physically cannot
--      point at a parent in another agency.
--   2. Row-Level Security (RLS): the API connects as `agencydesk_api`.
--      Every query is filtered by the agency / role / client stored in
--      per-transaction settings (app.agency_id, app.role, ...).
--   3. Service layer checks in Python (nice error messages, business rules).
-- Layers 1-2 hold even if layer 3 forgets a WHERE clause.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS app;

-- ---------------------------------------------------------------------
-- Roles
--   agencydesk_owner : owns tables, runs migrations (bypasses RLS as owner)
--   agencydesk_api   : used by every normal API request; RLS applies
--   agencydesk_auth  : used only by login + invite acceptance, which run
--                      before a tenant is known; small grant set
-- ---------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agencydesk_api')  THEN CREATE ROLE agencydesk_api  LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agencydesk_auth') THEN CREATE ROLE agencydesk_auth LOGIN BYPASSRLS; END IF;
END $$;

-- ---------------------------------------------------------------------
-- Request context. The API sets these with SET LOCAL at the start of
-- every transaction, using values it loaded from agency_memberships
-- (never from anything the browser sent directly).
-- ---------------------------------------------------------------------
CREATE FUNCTION app.agency_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.agency_id', true), '')::uuid $$;
CREATE FUNCTION app.user_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;
CREATE FUNCTION app.role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.role', true), '') $$;
CREATE FUNCTION app.client_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.client_id', true), '')::uuid $$;
CREATE FUNCTION app.is_staff() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(app.role() IN ('agency_admin', 'agency_member'), false) $$;

-- =====================================================================
-- Global tables (not tenant-owned)
-- =====================================================================

CREATE TABLE agencies (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]+$'),
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- One row per human, regardless of how many agencies they belong to.
CREATE TABLE users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text NOT NULL UNIQUE CHECK (email = lower(email)),
  name           text NOT NULL,
  password_hash  text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- Tenant tables. Every one has agency_id and UNIQUE (agency_id, id) so
-- children can reference (agency_id, id) instead of id alone.
-- =====================================================================

CREATE TABLE clients (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id   uuid NOT NULL REFERENCES agencies(id),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id)
);

-- A person's role inside one agency. Same user can have rows in many
-- agencies with different roles (edge case: one person, two agencies).
CREATE TABLE agency_memberships (
  agency_id   uuid NOT NULL REFERENCES agencies(id),
  user_id     uuid NOT NULL REFERENCES users(id),
  role        text NOT NULL CHECK (role IN ('agency_admin', 'agency_member', 'client_user')),
  client_id   uuid,                         -- set iff role = client_user
  is_staff    boolean GENERATED ALWAYS AS (role <> 'client_user') STORED,
  removed_at  timestamptz,                  -- soft removal keeps history (time entries, comments)
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (agency_id, user_id),
  UNIQUE (agency_id, user_id, is_staff),    -- target for "must be staff" FKs
  FOREIGN KEY (agency_id, client_id) REFERENCES clients(agency_id, id),
  CHECK ((role = 'client_user') = (client_id IS NOT NULL))
);

CREATE TABLE projects (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id   uuid NOT NULL,
  client_id   uuid NOT NULL,
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, client_id) REFERENCES clients(agency_id, id)
);
CREATE INDEX ON projects (agency_id, client_id);

-- Which staff members work on which project. Only staff can be added:
-- is_staff is pinned to true and must match the membership row.
CREATE TABLE project_members (
  agency_id   uuid NOT NULL,
  project_id  uuid NOT NULL,
  user_id     uuid NOT NULL,
  is_staff    boolean NOT NULL DEFAULT true CHECK (is_staff),
  added_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (agency_id, project_id, user_id),
  FOREIGN KEY (agency_id, project_id) REFERENCES projects(agency_id, id) ON DELETE CASCADE,
  FOREIGN KEY (agency_id, user_id, is_staff)
    REFERENCES agency_memberships(agency_id, user_id, is_staff) ON DELETE CASCADE
);
CREATE INDEX ON project_members (agency_id, user_id);

CREATE TABLE tasks (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id         uuid NOT NULL,
  project_id        uuid NOT NULL,
  title             text NOT NULL,
  description       text NOT NULL DEFAULT '',
  status            text NOT NULL DEFAULT 'todo'
                      CHECK (status IN ('todo', 'in_progress', 'in_review', 'done')),
  priority          text NOT NULL DEFAULT 'medium'
                      CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
  visibility        text NOT NULL DEFAULT 'internal'      -- safe default: hidden from clients
                      CHECK (visibility IN ('internal', 'client')),
  assignee_user_id  uuid,
  due_date          date,
  created_by        uuid NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, project_id) REFERENCES projects(agency_id, id) ON DELETE CASCADE,
  -- The assignee must be a current member of THIS project. When they are
  -- removed from the project, only assignee_user_id is cleared (edge case 5).
  FOREIGN KEY (agency_id, project_id, assignee_user_id)
    REFERENCES project_members(agency_id, project_id, user_id)
    ON DELETE SET NULL (assignee_user_id),
  FOREIGN KEY (agency_id, created_by) REFERENCES agency_memberships(agency_id, user_id)
);
CREATE INDEX ON tasks (agency_id, project_id, status);
CREATE INDEX ON tasks (agency_id, assignee_user_id);

CREATE TABLE comments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id       uuid NOT NULL,
  task_id         uuid NOT NULL,
  author_user_id  uuid NOT NULL,
  body            text NOT NULL CHECK (length(body) > 0),
  -- Effective visibility = task.visibility AND comment.visibility.
  -- A 'client' comment on an internal task stays hidden from clients.
  visibility      text NOT NULL DEFAULT 'internal' CHECK (visibility IN ('internal', 'client')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id) ON DELETE CASCADE,
  FOREIGN KEY (agency_id, author_user_id) REFERENCES agency_memberships(agency_id, user_id)
);
CREATE INDEX ON comments (agency_id, task_id, created_at);

CREATE TABLE files (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id       uuid NOT NULL,
  task_id         uuid NOT NULL,
  uploaded_by     uuid NOT NULL,
  storage_key     text NOT NULL UNIQUE,     -- path in object storage; never guessable from id alone
  filename        text NOT NULL,
  content_type    text NOT NULL,
  size_bytes      bigint NOT NULL CHECK (size_bytes > 0),
  visibility      text NOT NULL DEFAULT 'internal' CHECK (visibility IN ('internal', 'client')),
  approval_status text NOT NULL DEFAULT 'pending'
                    CHECK (approval_status IN ('pending', 'approved', 'changes_requested')),
  reviewed_by     uuid,
  reviewed_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id) ON DELETE CASCADE,
  FOREIGN KEY (agency_id, uploaded_by) REFERENCES agency_memberships(agency_id, user_id),
  FOREIGN KEY (agency_id, reviewed_by) REFERENCES agency_memberships(agency_id, user_id),
  -- Only client-visible files can carry a client decision.
  CHECK (approval_status = 'pending' OR visibility = 'client'),
  CHECK ((approval_status = 'pending') = (reviewed_by IS NULL))
);
CREATE INDEX ON files (agency_id, task_id);

CREATE TABLE time_entries (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id   uuid NOT NULL,
  task_id     uuid NOT NULL,
  user_id     uuid NOT NULL,
  is_staff    boolean NOT NULL DEFAULT true CHECK (is_staff),   -- clients can't log time
  minutes     integer NOT NULL CHECK (minutes > 0 AND minutes <= 1440),
  entry_date  date NOT NULL,
  note        text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id) ON DELETE CASCADE,
  FOREIGN KEY (agency_id, user_id, is_staff)
    REFERENCES agency_memberships(agency_id, user_id, is_staff)
);
CREATE INDEX ON time_entries (agency_id, task_id);

-- Append-only activity log (assignment changes, approvals, ...). Staff only.
CREATE TABLE task_events (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  agency_id   uuid NOT NULL,
  task_id     uuid NOT NULL,
  actor_id    uuid,                      -- null = system (e.g. automatic unassignment)
  kind        text NOT NULL,
  payload     jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id) ON DELETE CASCADE
);
CREATE INDEX ON task_events (agency_id, task_id, created_at);

CREATE TABLE invites (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id         uuid NOT NULL REFERENCES agencies(id),
  email             text NOT NULL CHECK (email = lower(email)),
  role              text NOT NULL CHECK (role IN ('agency_admin', 'agency_member', 'client_user')),
  client_id         uuid,
  token_hash        text NOT NULL UNIQUE,   -- sha256 of the emailed token; raw token never stored
  status            text NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'accepted', 'revoked')),
  invited_by        uuid NOT NULL,
  send_count        integer NOT NULL DEFAULT 1,
  expires_at        timestamptz NOT NULL,
  accepted_user_id  uuid REFERENCES users(id),
  accepted_at       timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (agency_id, client_id) REFERENCES clients(agency_id, id),
  FOREIGN KEY (agency_id, invited_by) REFERENCES agency_memberships(agency_id, user_id),
  CHECK ((role = 'client_user') = (client_id IS NOT NULL)),
  CHECK ((status = 'accepted') = (accepted_user_id IS NOT NULL))
);
-- At most one live invite per (agency, email): a resend updates it in place.
CREATE UNIQUE INDEX invites_one_pending ON invites (agency_id, email) WHERE status = 'pending';

-- =====================================================================
-- Visibility helpers. SECURITY DEFINER = runs as the table owner, so it
-- can look up projects/tasks without re-triggering RLS (which would
-- recurse). Each helper still filters by app.agency_id() itself.
-- =====================================================================

CREATE FUNCTION app.can_access_project(p_project uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM projects p
    WHERE p.id = p_project
      AND p.agency_id = app.agency_id()
      AND (
           app.role() = 'agency_admin'
        OR (app.role() = 'agency_member' AND EXISTS (
              SELECT 1 FROM project_members pm
              WHERE pm.agency_id = p.agency_id AND pm.project_id = p.id
                AND pm.user_id = app.user_id()))
        OR (app.role() = 'client_user' AND p.client_id = app.client_id())
      )
  )
$$;

CREATE FUNCTION app.can_see_task(p_task uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM tasks t
    WHERE t.id = p_task
      AND t.agency_id = app.agency_id()
      AND app.can_access_project(t.project_id)
      AND (app.role() <> 'client_user' OR t.visibility = 'client')
  )
$$;

CREATE FUNCTION app.can_see_client(p_client uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT CASE app.role()
    WHEN 'agency_admin'  THEN true
    WHEN 'client_user'   THEN p_client = app.client_id()
    WHEN 'agency_member' THEN EXISTS (
      SELECT 1 FROM projects p
      WHERE p.agency_id = app.agency_id() AND p.client_id = p_client
        AND app.can_access_project(p.id))
    ELSE false END
$$;

CREATE FUNCTION app.shares_agency(p_user uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT p_user = app.user_id() OR EXISTS (
    SELECT 1 FROM agency_memberships m
    WHERE m.agency_id = app.agency_id() AND m.user_id = p_user)
$$;

-- =====================================================================
-- Row-Level Security policies
-- Pattern per table:
--   tenant  : RESTRICTIVE, ALL commands -> agency_id must match context.
--             Restrictive = ANDed with everything else; can't be bypassed
--             by adding another permissive policy later.
--   read / insert / update / delete : PERMISSIVE, role rules.
-- A command with no permissive policy for the caller is denied.
-- =====================================================================

ALTER TABLE agencies ENABLE ROW LEVEL SECURITY;
CREATE POLICY read ON agencies FOR SELECT USING (id = app.agency_id());

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY read ON users FOR SELECT USING (app.shares_agency(id));
CREATE POLICY update_self ON users FOR UPDATE USING (id = app.user_id()) WITH CHECK (id = app.user_id());

-- Tenant policy on every tenant table
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['clients','agency_memberships','projects','project_members','tasks',
                           'comments','files','time_entries','task_events','invites'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant ON %I AS RESTRICTIVE FOR ALL
                      USING (agency_id = app.agency_id())
                      WITH CHECK (agency_id = app.agency_id())', t);
  END LOOP;
END $$;

-- clients
CREATE POLICY read  ON clients FOR SELECT USING (app.can_see_client(id));
CREATE POLICY write ON clients FOR ALL USING (app.role() = 'agency_admin') WITH CHECK (app.role() = 'agency_admin');

-- memberships: staff see the whole team; a client sees staff + contacts of their own client.
-- Everyone can also see their own row: get_tenant_db reads it (under RLS) after setting only
-- app.agency_id + app.user_id from the verified token, to learn the role and client_id.
-- Once the context is fully set, this exposes nothing the other branches don't already show.
CREATE POLICY read ON agency_memberships FOR SELECT USING (
  app.is_staff() OR is_staff OR client_id = app.client_id() OR user_id = app.user_id());
CREATE POLICY write ON agency_memberships FOR ALL
  USING (app.role() = 'agency_admin') WITH CHECK (app.role() = 'agency_admin');

-- projects
CREATE POLICY read  ON projects FOR SELECT USING (app.can_access_project(id));
CREATE POLICY write ON projects FOR ALL USING (app.role() = 'agency_admin') WITH CHECK (app.role() = 'agency_admin');

-- project_members (staff only)
CREATE POLICY read  ON project_members FOR SELECT USING (app.is_staff() AND app.can_access_project(project_id));
CREATE POLICY write ON project_members FOR ALL USING (app.role() = 'agency_admin') WITH CHECK (app.role() = 'agency_admin');

-- tasks: clients read client-visible tasks of their projects; only staff write
CREATE POLICY read ON tasks FOR SELECT USING (
  app.can_access_project(project_id) AND (app.is_staff() OR visibility = 'client'));
CREATE POLICY write ON tasks FOR ALL
  USING (app.is_staff() AND app.can_access_project(project_id))
  WITH CHECK (app.is_staff() AND app.can_access_project(project_id));

-- comments: visible iff task visible AND (staff OR comment is client-visible)
CREATE POLICY read ON comments FOR SELECT USING (
  app.can_see_task(task_id) AND (app.is_staff() OR visibility = 'client'));
CREATE POLICY insert ON comments FOR INSERT WITH CHECK (
  author_user_id = app.user_id() AND app.can_see_task(task_id)
  AND (app.is_staff() OR visibility = 'client'));
CREATE POLICY update ON comments FOR UPDATE
  USING (author_user_id = app.user_id())
  WITH CHECK (author_user_id = app.user_id() AND (app.is_staff() OR visibility = 'client'));
CREATE POLICY delete ON comments FOR DELETE USING (
  author_user_id = app.user_id() OR app.role() = 'agency_admin');

-- files: staff upload/delete; client may update (approval only, see trigger)
CREATE POLICY read ON files FOR SELECT USING (
  app.can_see_task(task_id) AND (app.is_staff() OR visibility = 'client'));
CREATE POLICY insert ON files FOR INSERT WITH CHECK (
  app.is_staff() AND uploaded_by = app.user_id() AND app.can_see_task(task_id));
CREATE POLICY update ON files FOR UPDATE
  USING (app.can_see_task(task_id) AND (app.is_staff() OR visibility = 'client'))
  WITH CHECK (app.can_see_task(task_id) AND (app.is_staff() OR visibility = 'client'));
CREATE POLICY delete ON files FOR DELETE USING (app.is_staff() AND app.can_see_task(task_id));

-- time entries: staff only; you log your own time
CREATE POLICY read ON time_entries FOR SELECT USING (app.is_staff() AND app.can_see_task(task_id));
CREATE POLICY insert ON time_entries FOR INSERT WITH CHECK (
  app.is_staff() AND user_id = app.user_id() AND app.can_see_task(task_id));
CREATE POLICY modify ON time_entries FOR UPDATE
  USING (user_id = app.user_id() OR app.role() = 'agency_admin')
  WITH CHECK (app.is_staff() AND app.can_see_task(task_id));
CREATE POLICY delete ON time_entries FOR DELETE
  USING (user_id = app.user_id() OR app.role() = 'agency_admin');

-- task events: staff read; inserted by triggers / service layer
CREATE POLICY read   ON task_events FOR SELECT USING (app.is_staff() AND app.can_see_task(task_id));
CREATE POLICY insert ON task_events FOR INSERT WITH CHECK (app.is_staff() AND app.can_see_task(task_id));

-- invites: admins manage; acceptance happens through app.accept_invite
CREATE POLICY admin ON invites FOR ALL
  USING (app.role() = 'agency_admin') WITH CHECK (app.role() = 'agency_admin');

-- =====================================================================
-- Triggers
-- =====================================================================

-- Clients may change ONLY the approval fields of a file, and reviewed_by
-- must be themselves.
CREATE FUNCTION app.files_client_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF app.role() = 'client_user' THEN
    IF (NEW.agency_id, NEW.task_id, NEW.uploaded_by, NEW.storage_key, NEW.filename,
        NEW.content_type, NEW.size_bytes, NEW.visibility)
       IS DISTINCT FROM
       (OLD.agency_id, OLD.task_id, OLD.uploaded_by, OLD.storage_key, OLD.filename,
        OLD.content_type, OLD.size_bytes, OLD.visibility) THEN
      RAISE EXCEPTION 'clients may only change approval_status' USING ERRCODE = '42501';
    END IF;
    IF NEW.approval_status = 'pending' OR NEW.reviewed_by IS DISTINCT FROM app.user_id() THEN
      RAISE EXCEPTION 'invalid approval decision' USING ERRCODE = '42501';
    END IF;
    NEW.reviewed_at := now();
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER files_client_guard BEFORE UPDATE ON files
  FOR EACH ROW EXECUTE FUNCTION app.files_client_guard();

-- Log every assignee change, including the automatic one done by the
-- ON DELETE SET NULL foreign key when someone leaves a project.
CREATE FUNCTION app.log_assignee_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF NEW.assignee_user_id IS DISTINCT FROM OLD.assignee_user_id THEN
    INSERT INTO task_events (agency_id, task_id, actor_id, kind, payload)
    VALUES (NEW.agency_id, NEW.id, app.user_id(),
            -- If the old assignee is no longer on the project, this update
            -- came from the ON DELETE SET NULL foreign key.
            CASE WHEN NEW.assignee_user_id IS NULL AND NOT EXISTS (
                   SELECT 1 FROM project_members pm
                   WHERE pm.agency_id = NEW.agency_id AND pm.project_id = NEW.project_id
                     AND pm.user_id = OLD.assignee_user_id)
                 THEN 'auto_unassigned_member_removed' ELSE 'assignee_changed' END,
            jsonb_build_object('from', OLD.assignee_user_id, 'to', NEW.assignee_user_id));
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER tasks_assignee_log BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION app.log_assignee_change();

-- =====================================================================
-- Functions called by the API
-- =====================================================================

-- Accept an invite exactly once. The UPDATE ... WHERE status='pending'
-- takes a row lock: if two requests race, the second waits, then sees
-- status='accepted' and matches 0 rows. users.email UNIQUE + ON CONFLICT
-- means an existing person is reused, never duplicated.
CREATE FUNCTION app.accept_invite(p_token_hash text, p_name text, p_password_hash text)
RETURNS TABLE (out_user_id uuid, out_agency_id uuid, out_role text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE inv invites; uid uuid;
BEGIN
  -- FOR UPDATE locks the row. A concurrent second call blocks here; when
  -- the first commits, Postgres re-checks the WHERE, sees status is no
  -- longer 'pending', and returns no row.
  SELECT * INTO inv FROM invites i
   WHERE i.token_hash = p_token_hash AND i.status = 'pending' AND i.expires_at > now()
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invite is invalid, expired or already used' USING ERRCODE = 'P0002';
  END IF;

  INSERT INTO users (email, name, password_hash)
  VALUES (inv.email, p_name, p_password_hash)
  ON CONFLICT (email) DO NOTHING;
  SELECT u.id INTO uid FROM users u WHERE u.email = inv.email;

  INSERT INTO agency_memberships (agency_id, user_id, role, client_id)
  VALUES (inv.agency_id, uid, inv.role, inv.client_id)
  ON CONFLICT ON CONSTRAINT agency_memberships_pkey DO UPDATE
    SET role = EXCLUDED.role, client_id = EXCLUDED.client_id, removed_at = NULL;

  UPDATE invites SET status = 'accepted', accepted_at = now(), accepted_user_id = uid
   WHERE id = inv.id;
  RETURN QUERY SELECT uid, inv.agency_id, inv.role;
END $$;

-- Hours per project for the dashboard. Clients can't read raw time
-- entries (notes are internal), so this returns only the total over
-- tasks the caller is allowed to see.
CREATE FUNCTION app.project_hours(p_project uuid) RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT CASE WHEN app.can_access_project(p_project) THEN
    coalesce(round(sum(te.minutes) / 60.0, 2), 0) END
  FROM time_entries te
  JOIN tasks t ON t.agency_id = te.agency_id AND t.id = te.task_id
  WHERE t.project_id = p_project
    AND t.agency_id = app.agency_id()
    AND (app.is_staff() OR t.visibility = 'client')
$$;

-- =====================================================================
-- Grants
-- =====================================================================
GRANT USAGE ON SCHEMA app TO agencydesk_api, agencydesk_auth;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO agencydesk_api;
REVOKE EXECUTE ON FUNCTION app.accept_invite(text, text, text) FROM PUBLIC, agencydesk_api;
GRANT EXECUTE ON FUNCTION app.accept_invite(text, text, text) TO agencydesk_auth;

GRANT SELECT, INSERT, UPDATE, DELETE ON
  clients, agency_memberships, projects, project_members, tasks,
  comments, files, time_entries, invites TO agencydesk_api;
GRANT SELECT, INSERT ON task_events TO agencydesk_api;   -- append-only
GRANT SELECT ON agencies TO agencydesk_api;
GRANT SELECT, UPDATE (name, password_hash) ON users TO agencydesk_api;

-- auth role: login lookup only
GRANT SELECT ON users, agency_memberships, agencies, clients TO agencydesk_auth;
