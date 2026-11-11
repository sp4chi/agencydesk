// The one module that talks to the backend. Pages never call fetch directly.
//
// Tokens are passed in by the caller (the session context keeps them in
// memory). Nothing here reads or writes localStorage, sessionStorage or
// cookies: a token there could be stolen by any script that runs on the page.
//
// The UI hiding a button is never the security boundary: every rule is
// enforced by the backend (and by Postgres RLS behind it).

import type {
  InviteAccepted,
  IssuedInvite,
  LoginKind,
  LoginResponse,
  Me,
  ProjectDashboard,
  ProjectMember,
  Role,
  SessionResponse,
  StaffClient,
  StaffComment,
  StaffFile,
  StaffInvite,
  StaffProject,
  StaffTask,
  StaffTimeEntry,
  TaskCreate,
  TaskFilters,
  TaskUpdate,
  TeamMember,
  Visibility,
} from "./types";

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  /** JSON-encoded, unless it's FormData (file uploads), which is sent as-is. */
  body?: unknown;
  token?: string | null;
  /** "blob" for file downloads. */
  responseType?: "json" | "blob";
}

function errorMessage(status: number, payload: unknown): string {
  // FastAPI errors: {"detail": "text"} or {"detail": [{msg: ...}, ...]} for 422.
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first.msg === "string") return first.msg;
    }
  }
  return status >= 500 ? "Something went wrong. Please try again." : `Request failed (${status})`;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const isForm = options.body instanceof FormData;
  // For FormData the browser sets Content-Type itself (with the multipart boundary).
  if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body:
      options.body === undefined ? undefined
      : isForm ? (options.body as FormData)
      : JSON.stringify(options.body),
    credentials: "omit", // auth is the bearer token only; never send cookies
  });

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // non-JSON error body; fall back to a generic message
    }
    throw new ApiError(response.status, errorMessage(response.status, payload));
  }
  if (response.status === 204) return undefined as T;
  if (options.responseType === "blob") return (await response.blob()) as T;
  return (await response.json()) as T;
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

// ---------------------------------------------------------------- auth
// Login and agency selection: no session yet.
export const authApi = {
  login(kind: LoginKind, email: string, password: string): Promise<LoginResponse> {
    const path = kind === "staff" ? "/auth/login" : "/auth/portal/login";
    return request<LoginResponse>(path, { method: "POST", body: { email, password } });
  },

  startSession(identityToken: string, agencyId: string): Promise<SessionResponse> {
    return request<SessionResponse>("/auth/session", {
      method: "POST",
      body: { agency_id: agencyId },
      token: identityToken,
    });
  },

  /** New account: name + password, no identity. Existing account: identity token, no password. */
  acceptInvite(
    inviteToken: string,
    account: { name: string; password: string } | { identityToken: string },
  ): Promise<InviteAccepted> {
    const loggedIn = "identityToken" in account;
    return request<InviteAccepted>("/invites/accept", {
      method: "POST",
      body: loggedIn ? { token: inviteToken } : { token: inviteToken, ...account },
      token: loggedIn ? account.identityToken : null,
    });
  },
};

// ------------------------------------------------------- authenticated
// Everything after agency selection. `onUnauthorized` runs on any 401
// (expired token, membership removed): the session is cleared and the
// user goes back to the login page.
export function createApi(sessionToken: string, onUnauthorized: () => void) {
  async function call<T>(path: string, options: Omit<RequestOptions, "token"> = {}): Promise<T> {
    try {
      return await request<T>(path, { ...options, token: sessionToken });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      throw error;
    }
  }

  const post = <T>(path: string, body?: unknown) => call<T>(path, { method: "POST", body });
  const patch = <T>(path: string, body: unknown) => call<T>(path, { method: "PATCH", body });

  return {
    me: () => call<Me>("/me"),

    team: {
      staff: () => call<TeamMember[]>("/team/staff"),
    },

    clients: {
      list: () => call<StaffClient[]>("/clients"),
      create: (name: string) => post<StaffClient>("/clients", { name }),
    },

    projects: {
      list: () => call<StaffProject[]>("/projects"),
      get: (id: string) => call<StaffProject>(`/projects/${id}`),
      create: (clientId: string, name: string) =>
        post<StaffProject>("/projects", { client_id: clientId, name }),
      dashboard: (id: string) => call<ProjectDashboard>(`/projects/${id}/dashboard`),
      members: (id: string) => call<ProjectMember[]>(`/projects/${id}/members`),
      addMember: (id: string, userId: string) =>
        post<ProjectMember[]>(`/projects/${id}/members`, { user_id: userId }),
      removeMember: (id: string, userId: string) =>
        call<{ unassigned_task_count: number }>(`/projects/${id}/members/${userId}`, { method: "DELETE" }),
    },

    tasks: {
      list: (projectId: string, filters: TaskFilters = {}) =>
        call<StaffTask[]>(`/projects/${projectId}/tasks${query(filters)}`),
      get: (id: string) => call<StaffTask>(`/tasks/${id}`),
      create: (projectId: string, task: TaskCreate) => post<StaffTask>(`/projects/${projectId}/tasks`, task),
      update: (id: string, changes: TaskUpdate) => patch<StaffTask>(`/tasks/${id}`, changes),
    },

    comments: {
      list: (taskId: string) => call<StaffComment[]>(`/tasks/${taskId}/comments`),
      create: (taskId: string, body: string, visibility: Visibility) =>
        post<StaffComment>(`/tasks/${taskId}/comments`, { body, visibility }),
    },

    files: {
      list: (taskId: string) => call<StaffFile[]>(`/tasks/${taskId}/files`),
      upload: (taskId: string, file: File, visibility: Visibility) => {
        const form = new FormData();
        form.append("file", file);
        form.append("visibility", visibility);
        return post<StaffFile>(`/tasks/${taskId}/files`, form);
      },
      update: (id: string, changes: { filename?: string; visibility?: Visibility }) =>
        patch<StaffFile>(`/files/${id}`, changes),
      // Downloads need the bearer token, so they can't be a plain link:
      // fetch the bytes, then hand them to the browser (see saveBlob).
      download: (id: string) => call<Blob>(`/files/${id}/download`, { responseType: "blob" }),
    },

    time: {
      list: (taskId: string) => call<StaffTimeEntry[]>(`/tasks/${taskId}/time-entries`),
      log: (taskId: string, entry: { minutes: number; entry_date?: string; note?: string }) =>
        post<StaffTimeEntry>(`/tasks/${taskId}/time-entries`, entry),
    },

    invites: {
      list: () => call<StaffInvite[]>("/invites"),
      create: (email: string, role: Role, clientId: string | null) =>
        post<IssuedInvite>("/invites", { email, role, client_id: clientId }),
      resend: (id: string) => post<IssuedInvite>(`/invites/${id}/resend`),
      revoke: (id: string) => call<void>(`/invites/${id}`, { method: "DELETE" }),
    },
  };
}

/** Save a downloaded file using the browser's normal "save as". */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export type Api = ReturnType<typeof createApi>;
