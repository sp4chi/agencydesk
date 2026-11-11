// Mirrors the backend's Pydantic response models (backend/app/schemas/).
// Staff and client shapes are separate types, like on the server.

export type Role = "agency_admin" | "agency_member" | "client_user";
export type LoginKind = "staff" | "client";

export interface MembershipOption {
  agency_id: string;
  agency_name: string;
  role: Role;
  client_name: string | null;
}

export interface LoginResponse {
  identity_token: string;
  memberships: MembershipOption[];
}

export interface SessionResponse {
  session_token: string;
  expires_in: number;
  membership: MembershipOption;
}

export interface Me {
  user: { id: string; email: string; name: string };
  agency: { id: string; name: string };
  role: Role;
  client: { id: string; name: string } | null;
}

// ---------------------------------------------------------- staff app
export type TaskStatus = "todo" | "in_progress" | "in_review" | "done";
export type TaskPriority = "low" | "medium" | "high" | "urgent";
export type Visibility = "internal" | "client";
export type ApprovalStatus = "pending" | "approved" | "changes_requested";

export interface StaffClient {
  id: string;
  name: string;
  created_at: string;
}

export interface StaffProject {
  id: string;
  name: string;
  client_id: string;
  client_name: string;
  created_at: string;
}

export interface ProjectMember {
  user_id: string;
  name: string;
  email: string;
  role: Role;
  added_at: string;
}

export interface TeamMember {
  user_id: string;
  name: string;
  email: string;
  role: Role;
}

export interface StaffTask {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  visibility: Visibility;
  assignee_user_id: string | null;
  assignee_name: string | null;
  due_date: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  visibility?: Visibility;
  assignee_user_id?: string | null;
  due_date?: string | null;
}

export type TaskUpdate = Partial<TaskCreate>;

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  assignee?: string; // user id, "me" or "unassigned"
  q?: string;
}

export interface StaffComment {
  id: string;
  task_id: string;
  body: string;
  visibility: Visibility;
  visible_to_client: boolean;
  author_user_id: string;
  author_name: string;
  created_at: string;
}

export interface StaffFile {
  id: string;
  task_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  visibility: Visibility;
  visible_to_client: boolean;
  approval_status: ApprovalStatus;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  uploaded_by: string;
  uploaded_by_name: string;
  created_at: string;
}

export interface StaffTimeEntry {
  id: string;
  task_id: string;
  user_id: string;
  user_name: string;
  minutes: number;
  entry_date: string;
  note: string;
  created_at: string;
}

export interface ProjectDashboard {
  project_id: string;
  project_name: string;
  task_counts: Record<TaskStatus, number>;
  total_tasks: number;
  total_hours: number;
}

export interface StaffInvite {
  id: string;
  email: string;
  role: Role;
  client_id: string | null;
  status: "pending" | "accepted" | "revoked";
  send_count: number;
  expires_at: string;
  created_at: string;
}

export interface IssuedInvite {
  invite: StaffInvite;
  invite_url: string;
}

export interface InviteAccepted {
  agency_id: string;
  role: Role;
  /** Which app to log in to next. */
  login: "staff" | "portal";
}

// -------------------------------------------------------- client portal
// What a client_user gets back from the same endpoints: the backend's
// Client* models, without internal fields (visibility, assignee, notes...).

export interface ClientProject {
  id: string;
  name: string;
  created_at: string;
}

export interface ClientTask {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientComment {
  id: string;
  body: string;
  author_name: string;
  created_at: string;
}

export interface ClientFile {
  id: string;
  task_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  approval_status: ApprovalStatus;
  reviewed_at: string | null;
  created_at: string;
}

export type ReviewDecision = "approved" | "changes_requested";
