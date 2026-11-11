// The one module that talks to the backend. Pages never call fetch directly.
//
// Tokens are passed in by the caller (the session context keeps them in
// memory). Nothing here reads or writes localStorage, sessionStorage or
// cookies: a token there could be stolen by any script that runs on the page.
//
// The UI hiding a button is never the security boundary: every rule is
// enforced by the backend (and by Postgres RLS behind it).

import type { LoginKind, LoginResponse, Me, SessionResponse } from "./types";

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
  body?: unknown;
  token?: string | null;
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
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
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
  return (await response.json()) as T;
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

  return {
    me: () => call<Me>("/me"),
  };
}

export type Api = ReturnType<typeof createApi>;
