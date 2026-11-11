// Invites (admins only; the API returns 403 for anyone else). The invite
// link is shown once after create/resend, to pass on to the person; only a
// hash of its token is stored, so it can't be shown again later.

import { useState, type FormEvent } from "react";

import type { Role } from "../api/types";
import { useActiveSession } from "../auth/SessionProvider";
import { formatDate } from "../shared/format";
import { ROLE_LABELS } from "../shared/labels";
import { errorText, useLoad } from "../shared/useLoad";

export function InvitesPage() {
  const { api } = useActiveSession();
  const invites = useLoad(() => api.invites.list(), [api]);
  const clients = useLoad(() => api.clients.list(), [api]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agency_member");
  const [clientId, setClientId] = useState("");
  const [link, setLink] = useState<{ email: string; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<{ invite: { email: string }; invite_url: string } | void>) {
    setError(null);
    try {
      const result = await action();
      if (result) setLink({ email: result.invite.email, url: result.invite_url });
      invites.reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  function create(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await api.invites.create(email, role, role === "client_user" ? clientId : null);
      setEmail("");
      return result;
    });
  }

  const clientName = (id: string | null) => clients.data?.find((c) => c.id === id)?.name;

  return (
    <section aria-labelledby="invites-title">
      <h1 id="invites-title">Invites</h1>

      <form className="card inline-form" onSubmit={create}>
        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {(Object.keys(ROLE_LABELS) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </label>
        {role === "client_user" && (
          <label>
            Client
            <select required value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">Choose a client…</option>
              {clients.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        )}
        <button type="submit">Send invite</button>
      </form>

      {link && (
        <div className="notice invite-link" role="status">
          <p>Invite link for <strong>{link.email}</strong>. Copy it now: it won't be shown again.</p>
          <input readOnly value={link.url} aria-label="Invite link" onFocus={(e) => e.target.select()} />
          <button type="button" onClick={() => void navigator.clipboard?.writeText(link.url)}>Copy link</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      <ul className="list">
        {invites.data?.map((i) => (
          <li key={i.id} className="list-row">
            <span>
              <strong>{i.email}</strong>{" "}
              <span className="muted">
                {ROLE_LABELS[i.role]}{i.client_id && clientName(i.client_id) ? ` · ${clientName(i.client_id)}` : ""}
                {" · "}{i.status === "pending" ? `expires ${formatDate(i.expires_at)}` : i.status}
                {i.send_count > 1 && ` · sent ${i.send_count}×`}
              </span>
            </span>
            {i.status === "pending" && (
              <span className="row-actions">
                <button type="button" className="link-button" onClick={() => void run(() => api.invites.resend(i.id))}>
                  Resend
                </button>
                <button type="button" className="link-button danger" onClick={() => void run(() => api.invites.revoke(i.id))}>
                  Revoke
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
