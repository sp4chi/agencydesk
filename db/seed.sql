-- Seed data: 2 agencies, one person (ravi) in both with different roles,
-- a mix of internal and client-visible tasks, comments, files, time.
-- Fixed UUIDs make the tests readable. Password for everyone: "password"
-- (bcrypt hash below is a placeholder; the real seed script hashes it).

\set pw '''$2b$12$placeholderplaceholderplaceholderplaceholderplace'''

INSERT INTO agencies (id, name, slug) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', 'Pixel Studio',   'pixel'),
  ('bbbbbbbb-0000-0000-0000-000000000001', 'Northwind Labs', 'northwind');

INSERT INTO users (id, email, name, password_hash) VALUES
  ('00000000-0000-0000-0000-0000000000a1', 'alice@pixel.test',  'Alice (Pixel admin)',  :pw),
  ('00000000-0000-0000-0000-0000000000a2', 'mark@pixel.test',   'Mark (Pixel member)',  :pw),
  ('00000000-0000-0000-0000-0000000000a3', 'nina@pixel.test',   'Nina (Pixel member)',  :pw),
  ('00000000-0000-0000-0000-0000000000b1', 'bob@northwind.test','Bob (Northwind admin)',:pw),
  ('00000000-0000-0000-0000-0000000000c1', 'ravi@acme.test',    'Ravi (in both)',       :pw);

INSERT INTO clients (id, agency_id, name) VALUES
  ('aaaaaaaa-0000-0000-0001-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'Acme Corp'),
  ('aaaaaaaa-0000-0000-0001-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'Globex'),
  ('bbbbbbbb-0000-0000-0001-000000000001', 'bbbbbbbb-0000-0000-0000-000000000001', 'Initech');

INSERT INTO agency_memberships (agency_id, user_id, role, client_id) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000a1', 'agency_admin',  NULL),
  ('aaaaaaaa-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000a2', 'agency_member', NULL),
  ('aaaaaaaa-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000a3', 'agency_member', NULL),
  -- Ravi: client contact for Acme at Pixel ...
  ('aaaaaaaa-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000c1', 'client_user', 'aaaaaaaa-0000-0000-0001-000000000001'),
  ('bbbbbbbb-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000b1', 'agency_admin',  NULL),
  -- ... and a contact for Initech at Northwind (same email, separate role row)
  ('bbbbbbbb-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000c1', 'client_user', 'bbbbbbbb-0000-0000-0001-000000000001');

INSERT INTO projects (id, agency_id, client_id, name) VALUES
  ('aaaaaaaa-0000-0000-0002-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0001-000000000001', 'Acme website redesign'),
  ('aaaaaaaa-0000-0000-0002-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0001-000000000002', 'Globex brand refresh'),
  ('bbbbbbbb-0000-0000-0002-000000000001', 'bbbbbbbb-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0001-000000000001', 'Initech TPS portal');

-- Mark and Nina are on the Acme project; nobody but the admin is on Globex.
INSERT INTO project_members (agency_id, project_id, user_id) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0002-000000000001', '00000000-0000-0000-0000-0000000000a2'),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0002-000000000001', '00000000-0000-0000-0000-0000000000a3'),
  ('bbbbbbbb-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0002-000000000001', '00000000-0000-0000-0000-0000000000b1');

INSERT INTO tasks (id, agency_id, project_id, title, status, priority, visibility, assignee_user_id, created_by) VALUES
  ('aaaaaaaa-0000-0000-0003-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0002-000000000001',
   'Homepage mockups',              'in_review',   'high',   'client',   '00000000-0000-0000-0000-0000000000a2', '00000000-0000-0000-0000-0000000000a1'),
  ('aaaaaaaa-0000-0000-0003-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0002-000000000001',
   'Fix our staging budget overrun', 'in_progress', 'urgent', 'internal', '00000000-0000-0000-0000-0000000000a3', '00000000-0000-0000-0000-0000000000a1'),
  ('aaaaaaaa-0000-0000-0003-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0002-000000000001',
   'Content migration',             'todo',        'medium', 'client',   '00000000-0000-0000-0000-0000000000a3', '00000000-0000-0000-0000-0000000000a1'),
  ('aaaaaaaa-0000-0000-0003-000000000004', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0002-000000000002',
   'Globex logo options',           'todo',        'medium', 'client',   NULL,                                   '00000000-0000-0000-0000-0000000000a1'),
  ('bbbbbbbb-0000-0000-0003-000000000001', 'bbbbbbbb-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0002-000000000001',
   'Northwind secret task',         'todo',        'low',    'internal', '00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000b1');

INSERT INTO comments (agency_id, task_id, author_user_id, body, visibility) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0003-000000000001', '00000000-0000-0000-0000-0000000000a2', 'v2 uploaded, please review', 'client'),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0003-000000000001', '00000000-0000-0000-0000-0000000000a1', 'INTERNAL: client keeps changing scope', 'internal');

INSERT INTO files (id, agency_id, task_id, uploaded_by, storage_key, filename, content_type, size_bytes, visibility) VALUES
  ('aaaaaaaa-0000-0000-0004-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0003-000000000001',
   '00000000-0000-0000-0000-0000000000a2', 'pixel/f1-homepage-v2.fig', 'homepage-v2.fig', 'application/octet-stream', 1024, 'client'),
  ('aaaaaaaa-0000-0000-0004-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0003-000000000001',
   '00000000-0000-0000-0000-0000000000a2', 'pixel/f2-internal-notes.pdf', 'internal-notes.pdf', 'application/pdf', 2048, 'internal');

INSERT INTO time_entries (agency_id, task_id, user_id, minutes, entry_date, note) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0003-000000000001', '00000000-0000-0000-0000-0000000000a2', 180, '2026-11-03', 'mockup v2'),
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0003-000000000002', '00000000-0000-0000-0000-0000000000a3', 120, '2026-11-04', 'internal firefighting');
