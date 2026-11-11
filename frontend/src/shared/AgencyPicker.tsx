// Shown after login when the person has more than one agency (e.g. Ravi),
// and when they choose "Switch agency". Picking one starts a new session
// scoped to that agency only.

import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import type { LoginKind } from "../api/types";
import { useSession } from "../auth/SessionProvider";
import { ROUTES } from "../auth/sessionState";
import { ROLE_LABELS } from "./labels";

export function AgencyPicker({ kind }: { kind: LoginKind }) {
  const { identity, selectAgency, logout } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  if (!identity || identity.kind !== kind) return <Navigate to={ROUTES[kind].login} replace />;

  async function choose(agencyId: string) {
    setError(null);
    setBusyId(agencyId);
    try {
      await selectAgency(agencyId);
      navigate(ROUTES[kind].home, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="auth-page">
      <section className="card auth-card" aria-labelledby="picker-title">
        <h1 id="picker-title">Choose an agency</h1>
        <ul className="choice-list">
          {identity.memberships.map((m) => (
            <li key={m.agency_id}>
              <button type="button" className="choice" disabled={busyId !== null}
                      onClick={() => choose(m.agency_id)}>
                <strong>{m.agency_name}</strong>
                <span className="muted">
                  {ROLE_LABELS[m.role]}{m.client_name ? ` · ${m.client_name}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="button" className="link-button" onClick={logout}>Sign out</button>
      </section>
    </main>
  );
}
