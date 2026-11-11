// Public page the invite link opens: /invite#token=...
//
// The token is in the URL fragment, which browsers never send to servers,
// so it doesn't land in access logs. Two paths, matching app.accept_invite:
//   * new person: choose a name and password -> account created
//   * existing account: must be logged in as it -> membership added
// After accepting, the in-memory login is cleared, so the next login lists
// the new agency.

import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError, authApi } from "../api/client";
import { useSession } from "../auth/SessionProvider";
import { ROUTES } from "../auth/sessionState";
import { errorText } from "./useLoad";

export function inviteTokenFromHash(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return token && token.length >= 10 ? token : null;
}

export function AcceptInvitePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { identity, logout } = useSession();
  const token = inviteTokenFromHash(location.hash);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [busy, setBusy] = useState(false);
  const returnTo = `/invite${location.hash}`;

  if (!token) {
    return (
      <main className="auth-page">
        <section className="card auth-card">
          <h1>Invite link not valid</h1>
          <p className="muted">Ask the person who invited you to send the link again.</p>
        </section>
      </main>
    );
  }

  async function accept(account: Parameters<typeof authApi.acceptInvite>[1]) {
    if (!token) return;
    setError(null);
    setBusy(true);
    try {
      const accepted = await authApi.acceptInvite(token, account);
      logout(); // the old identity doesn't know about the new membership
      const kind = accepted.login === "portal" ? "client" : "staff";
      navigate(ROUTES[kind].login, { replace: true, state: { notice: "Invite accepted. Sign in to continue." } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setNeedsLogin(true);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function createAccount(event: FormEvent) {
    event.preventDefault();
    void accept({ name, password });
  }

  return (
    <main className="auth-page">
      <section className="card auth-card" aria-labelledby="invite-title">
        <h1 id="invite-title">Join on AgencyDesk</h1>
        {identity ? (
          <>
            <p>You're signed in. Accept this invite with your current account?</p>
            <button type="button" disabled={busy} onClick={() => void accept({ identityToken: identity.token })}>
              Accept invite
            </button>
            <p className="muted small">Not the invited email? <button type="button" className="link-button" onClick={logout}>Sign out</button> first.</p>
          </>
        ) : (
          <form onSubmit={createAccount} className="auth-card">
            <p className="muted">New to AgencyDesk? Choose your name and a password.</p>
            <label>
              Your name
              <input required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              Password (at least 8 characters)
              <input type="password" required minLength={8} autoComplete="new-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button type="submit" disabled={busy}>Create account and join</button>
          </form>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        {!identity && (
          <p className={needsLogin ? "notice" : "muted small"}>
            Already have an account?{" "}
            <Link to={ROUTES.staff.login} state={{ returnTo }}>Sign in (staff)</Link> or{" "}
            <Link to={ROUTES.client.login} state={{ returnTo }}>sign in (client portal)</Link>, then you'll come back here.
          </p>
        )}
      </section>
    </main>
  );
}
