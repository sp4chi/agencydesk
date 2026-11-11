import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import type { LoginKind } from "../api/types";
import { useSession } from "../auth/SessionProvider";
import { ROUTES } from "../auth/sessionState";

const TITLES: Record<LoginKind, { title: string; other: string; otherPath: string }> = {
  staff: { title: "AgencyDesk", other: "Client? Go to the client portal", otherPath: ROUTES.client.login },
  client: { title: "AgencyDesk client portal", other: "Agency staff? Go to the staff app", otherPath: ROUTES.staff.login },
};

export function LoginPage({ kind }: { kind: LoginKind }) {
  const { login } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const text = TITLES[kind];

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const started = await login(kind, email, password);
      navigate(started ? ROUTES[kind].home : ROUTES[kind].selectAgency, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={onSubmit} aria-labelledby="login-title">
        <h1 id="login-title">{text.title}</h1>
        <label>
          Email
          <input type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="muted"><Link to={text.otherPath}>{text.other}</Link></p>
      </form>
    </main>
  );
}
