// React wrapper around sessionState: login, agency selection, switching,
// logout, and an `api` bound to the current session token.

import { createContext, useCallback, useContext, useMemo, useReducer, type ReactNode } from "react";

import { authApi, createApi, type Api } from "../api/client";
import type { LoginKind } from "../api/types";
import {
  initialSessionState,
  sessionReducer,
  type ActiveSession,
  type Identity,
} from "./sessionState";

export interface SessionContextValue {
  identity: Identity | null;
  session: ActiveSession | null;
  api: Api | null;
  /** Returns true if a session was started straight away (only one agency). */
  login: (kind: LoginKind, email: string, password: string) => Promise<boolean>;
  selectAgency: (agencyId: string) => Promise<void>;
  switchAgency: () => void;
  logout: () => void;
}

// Exported so component tests can provide a fake session and api.
export const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(sessionReducer, initialSessionState);

  const logout = useCallback(() => dispatch({ type: "loggedOut" }), []);

  const startSession = useCallback(async (identity: Identity, agencyId: string) => {
    const started = await authApi.startSession(identity.token, agencyId);
    const me = await createApi(started.session_token, logout).me();
    dispatch({
      type: "sessionStarted",
      session: { token: started.session_token, membership: started.membership, me },
    });
  }, [logout]);

  const login = useCallback(async (kind: LoginKind, email: string, password: string) => {
    const result = await authApi.login(kind, email, password);
    const identity: Identity = { token: result.identity_token, kind, memberships: result.memberships };
    dispatch({ type: "loggedIn", identity });
    const only = result.memberships.length === 1 ? result.memberships[0] : undefined;
    if (only) {
      await startSession(identity, only.agency_id);
      return true;
    }
    return false;
  }, [startSession]);

  const selectAgency = useCallback(async (agencyId: string) => {
    if (!state.identity) throw new Error("Log in first");
    await startSession(state.identity, agencyId);
  }, [state.identity, startSession]);

  const switchAgency = useCallback(() => dispatch({ type: "sessionEnded" }), []);

  const api = useMemo(
    () => (state.session ? createApi(state.session.token, logout) : null),
    [state.session, logout],
  );

  const value = useMemo<SessionContextValue>(
    () => ({ ...state, api, login, selectAgency, switchAgency, logout }),
    [state, api, login, selectAgency, switchAgency, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}

/** For pages behind RequireSession: the session and api are always set there. */
export function useActiveSession(): { session: ActiveSession; api: Api } {
  const { session, api } = useSession();
  if (!session || !api) throw new Error("useActiveSession needs an active session");
  return { session, api };
}
