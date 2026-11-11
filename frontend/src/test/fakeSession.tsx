// Test helper: render a component with a fake signed-in session and an api
// whose methods are vi.fn() mocks. Not used by the app itself.

import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import type { Api } from "../api/client";
import type { Role } from "../api/types";
import { SessionContext, type SessionContextValue } from "../auth/SessionProvider";

type DeepMock<T> = { [K in keyof T]: T[K] extends (...args: never[]) => unknown ? ReturnType<typeof vi.fn> : DeepMock<T[K]> };

export function fakeApi(overrides: Partial<Record<string, unknown>> = {}): DeepMock<Api> {
  const resolved = (value: unknown) => vi.fn().mockResolvedValue(value);
  const api = {
    me: resolved(null),
    team: { staff: resolved([]) },
    clients: { list: resolved([]), create: resolved(null) },
    projects: {
      list: resolved([]), get: resolved(null), create: resolved(null), dashboard: resolved(null),
      members: resolved([]), addMember: resolved([]), removeMember: resolved({ unassigned_task_count: 0 }),
    },
    tasks: { list: resolved([]), get: resolved(null), create: resolved(null), update: resolved(null) },
    comments: { list: resolved([]), create: resolved(null) },
    files: { list: resolved([]), upload: resolved(null), update: resolved(null), download: resolved(new Blob()) },
    time: { list: resolved([]), log: resolved(null) },
    invites: { list: resolved([]), create: resolved(null), resend: resolved(null), revoke: resolved(undefined) },
    portal: {
      projects: { list: resolved([]), get: resolved(null), dashboard: resolved(null) },
      tasks: { list: resolved([]), get: resolved(null) },
      comments: { list: resolved([]), create: resolved(null) },
      files: { list: resolved([]), download: resolved(new Blob()), review: resolved(null) },
    },
    ...overrides,
  };
  return api as unknown as DeepMock<Api>;
}

export function renderWithSession(ui: ReactElement, api: DeepMock<Api>, role: Role = "agency_member") {
  const value: SessionContextValue = {
    identity: { token: "id", kind: role === "client_user" ? "client" : "staff", memberships: [] },
    session: {
      token: "session",
      membership: { agency_id: "a", agency_name: "Pixel Studio", role, client_name: null },
      me: {
        user: { id: "me", email: "mark@pixel.test", name: "Mark" },
        agency: { id: "a", name: "Pixel Studio" },
        role,
        client: null,
      },
    },
    api: api as unknown as Api,
    login: vi.fn(),
    selectAgency: vi.fn(),
    switchAgency: vi.fn(),
    logout: vi.fn(),
  };
  return render(
    <SessionContext.Provider value={value}>
      <MemoryRouter>{ui}</MemoryRouter>
    </SessionContext.Provider>,
  );
}
