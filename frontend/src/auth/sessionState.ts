// Pure session state, kept separate from React so it can be unit tested.
//
// Two levels, mirroring the backend's two tokens:
//   identity: who you are (after login). Can only be exchanged for a session.
//   session:  you, acting in one agency. This is what API calls use.
// Both live in memory only: a page refresh means logging in again. That is
// the price of never putting a token where other scripts could read it.

import type { LoginKind, Me, MembershipOption, Role } from "../api/types";

export interface Identity {
  token: string;
  kind: LoginKind;
  memberships: MembershipOption[];
}

export interface ActiveSession {
  token: string;
  membership: MembershipOption;
  me: Me;
}

export interface SessionState {
  identity: Identity | null;
  session: ActiveSession | null;
}

export type SessionAction =
  | { type: "loggedIn"; identity: Identity }
  | { type: "sessionStarted"; session: ActiveSession }
  | { type: "sessionEnded" } // switch agency: keep identity, drop the agency session
  | { type: "loggedOut" };

export const initialSessionState: SessionState = { identity: null, session: null };

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "loggedIn":
      return { identity: action.identity, session: null };
    case "sessionStarted":
      if (!state.identity) return state; // can't have a session without an identity
      return { ...state, session: action.session };
    case "sessionEnded":
      return { ...state, session: null };
    case "loggedOut":
      return initialSessionState;
  }
}

export function kindForRole(role: Role): LoginKind {
  return role === "client_user" ? "client" : "staff";
}

// Where each kind of user lives. Staff app at /, client portal at /portal.
export const ROUTES: Record<LoginKind, { login: string; selectAgency: string; home: string }> = {
  staff: { login: "/login", selectAgency: "/select-agency", home: "/" },
  client: { login: "/portal/login", selectAgency: "/portal/select-agency", home: "/portal" },
};
