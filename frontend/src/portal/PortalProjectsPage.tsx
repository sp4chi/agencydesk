// A client user's projects: only their own client's, decided by the API.

import { Link } from "react-router-dom";

import { useActiveSession } from "../auth/SessionProvider";
import { useLoad } from "../shared/useLoad";

export function PortalProjectsPage() {
  const { api, session } = useActiveSession();
  const projects = useLoad(() => api.portal.projects.list(), [api]);

  return (
    <section aria-labelledby="portal-projects-title">
      <h1 id="portal-projects-title">Your projects</h1>
      <p className="muted">{session.me.client?.name} with {session.me.agency.name}</p>
      {projects.error && <p className="error" role="alert">{projects.error}</p>}
      {projects.data && projects.data.length === 0 && <p className="muted">No projects yet.</p>}
      <ul className="card-grid">
        {projects.data?.map((p) => (
          <li key={p.id}>
            <Link className="card project-card" to={`/portal/projects/${p.id}`}>
              <strong>{p.name}</strong>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
