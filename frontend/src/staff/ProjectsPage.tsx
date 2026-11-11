// Project list. Admins see every project and can create clients and
// projects; members only see projects they're on (the API decides that).

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { useActiveSession } from "../auth/SessionProvider";
import { errorText, useLoad } from "../shared/useLoad";

export function ProjectsPage() {
  const { api, session } = useActiveSession();
  const isAdmin = session.me.role === "agency_admin";
  const projects = useLoad(() => api.projects.list(), [api]);

  return (
    <section aria-labelledby="projects-title">
      <h1 id="projects-title">Projects</h1>
      {projects.error && <p className="error" role="alert">{projects.error}</p>}
      {projects.loading && !projects.data && <p className="muted">Loading…</p>}
      {projects.data && projects.data.length === 0 && (
        <p className="muted">{isAdmin ? "No projects yet." : "You're not on any projects yet."}</p>
      )}
      <ul className="card-grid">
        {projects.data?.map((p) => (
          <li key={p.id}>
            <Link className="card project-card" to={`/projects/${p.id}`}>
              <strong>{p.name}</strong>
              <span className="muted">{p.client_name}</span>
            </Link>
          </li>
        ))}
      </ul>
      {isAdmin && <NewProjectForm onCreated={projects.reload} />}
    </section>
  );
}

function NewProjectForm({ onCreated }: { onCreated: () => void }) {
  const { api } = useActiveSession();
  const clients = useLoad(() => api.clients.list(), [api]);
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [newClient, setNewClient] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function createProject(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.projects.create(clientId, name);
      setName("");
      onCreated();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function createClient(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const created = await api.clients.create(newClient);
      setNewClient("");
      clients.reload();
      setClientId(created.id);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="card form-row-card">
      <h2>New project</h2>
      <form className="inline-form" onSubmit={createProject}>
        <label>
          Client
          <select required value={clientId} onChange={(e) => setClientId(e.target.value)}>
            <option value="">Choose a client…</option>
            {clients.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>
          Project name
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="submit">Create project</button>
      </form>
      <form className="inline-form" onSubmit={createClient}>
        <label>
          Or add a client
          <input required placeholder="Client company name" value={newClient}
                 onChange={(e) => setNewClient(e.target.value)} />
        </label>
        <button type="submit">Add client</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
