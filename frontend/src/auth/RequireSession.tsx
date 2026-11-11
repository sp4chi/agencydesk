// Route guard: sends people without a matching session to the right login.
// This is UX only. The backend checks every request; a staff page reached by
// a client user would still get 403/404 from the API.

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import type { LoginKind } from "../api/types";
import { useSession } from "./SessionProvider";
import { kindForRole, ROUTES } from "./sessionState";

export function RequireSession({ kind, children }: { kind: LoginKind; children: ReactNode }) {
  const { identity, session } = useSession();
  const location = useLocation();

  if (session && kindForRole(session.membership.role) === kind) return <>{children}</>;
  if (identity && identity.kind === kind) {
    return <Navigate to={ROUTES[kind].selectAgency} replace />;
  }
  return <Navigate to={ROUTES[kind].login} replace state={{ from: location.pathname }} />;
}
