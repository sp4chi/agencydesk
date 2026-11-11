import { useNavigate } from "react-router-dom";

import { useActiveSession, useSession } from "../auth/SessionProvider";
import { kindForRole, ROUTES } from "../auth/sessionState";

export function AppHeader() {
  const { session } = useActiveSession();
  const { identity, switchAgency, logout } = useSession();
  const navigate = useNavigate();
  const kind = kindForRole(session.me.role);
  const canSwitch = (identity?.memberships.length ?? 0) > 1;

  return (
    <header className="app-header">
      <div>
        <strong>{session.me.agency.name}</strong>
        {session.me.client && <span className="muted"> · {session.me.client.name}</span>}
      </div>
      <nav className="header-actions" aria-label="Account">
        <span className="muted">{session.me.user.name}</span>
        {canSwitch && (
          <button type="button" className="link-button" onClick={() => {
            switchAgency();
            navigate(ROUTES[kind].selectAgency);
          }}>
            Switch agency
          </button>
        )}
        <button type="button" className="link-button" onClick={logout}>Sign out</button>
      </nav>
    </header>
  );
}
