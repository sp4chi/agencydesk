import { describe, expect, it } from "vitest";

import type { MembershipOption } from "../api/types";
import {
  initialSessionState,
  kindForRole,
  sessionReducer,
  type ActiveSession,
  type Identity,
} from "./sessionState";

const pixel: MembershipOption = {
  agency_id: "pixel", agency_name: "Pixel Studio", role: "client_user", client_name: "Acme Corp",
};
const northwind: MembershipOption = {
  agency_id: "northwind", agency_name: "Northwind Labs", role: "client_user", client_name: "Initech",
};
const identity: Identity = { token: "id-tok", kind: "client", memberships: [pixel, northwind] };
const session: ActiveSession = {
  token: "session-tok",
  membership: pixel,
  me: {
    user: { id: "u", email: "ravi@acme.test", name: "Ravi" },
    agency: { id: "pixel", name: "Pixel Studio" },
    role: "client_user",
    client: { id: "acme", name: "Acme Corp" },
  },
};

describe("sessionReducer", () => {
  it("one person, two agencies: login keeps both memberships and no session yet", () => {
    const state = sessionReducer(initialSessionState, { type: "loggedIn", identity });
    expect(state.identity?.memberships).toHaveLength(2);
    expect(state.session).toBeNull();
  });

  it("switching agency drops the session but keeps the identity", () => {
    let state = sessionReducer(initialSessionState, { type: "loggedIn", identity });
    state = sessionReducer(state, { type: "sessionStarted", session });
    state = sessionReducer(state, { type: "sessionEnded" });
    expect(state).toEqual({ identity, session: null });
  });

  it("a new login replaces any previous session", () => {
    let state = sessionReducer(initialSessionState, { type: "loggedIn", identity });
    state = sessionReducer(state, { type: "sessionStarted", session });
    state = sessionReducer(state, { type: "loggedIn", identity: { ...identity, token: "new" } });
    expect(state.session).toBeNull();
  });

  it("ignores a session without an identity", () => {
    expect(sessionReducer(initialSessionState, { type: "sessionStarted", session })).toBe(initialSessionState);
  });

  it("logout clears everything", () => {
    let state = sessionReducer(initialSessionState, { type: "loggedIn", identity });
    state = sessionReducer(state, { type: "sessionStarted", session });
    expect(sessionReducer(state, { type: "loggedOut" })).toEqual(initialSessionState);
  });
});

describe("kindForRole", () => {
  it("maps client users to the portal and everyone else to the staff app", () => {
    expect(kindForRole("client_user")).toBe("client");
    expect(kindForRole("agency_admin")).toBe("staff");
    expect(kindForRole("agency_member")).toBe("staff");
  });
});
