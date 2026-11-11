// One project in the portal: progress numbers, then the tasks the agency has
// shared, grouped by status. Internal tasks never reach this page: the API
// leaves them out of every list, search and count.

import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useActiveSession } from "../auth/SessionProvider";
import { PRIORITY_LABELS, STATUSES, STATUS_LABELS, formatDate, groupByStatus } from "../shared/format";
import { useLoad } from "../shared/useLoad";
import { PortalTaskPanel } from "./PortalTaskPanel";

export function PortalProjectPage() {
  const { projectId = "" } = useParams();
  const { api } = useActiveSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState<string | undefined>(undefined);
  const [changes, setChanges] = useState(0);
  const project = useLoad(() => api.portal.projects.get(projectId), [api, projectId]);
  const dashboard = useLoad(() => api.portal.projects.dashboard(projectId), [api, projectId, changes]);
  const tasks = useLoad(() => api.portal.tasks.list(projectId, { q }), [api, projectId, q, changes]);
  const openTaskId = searchParams.get("task");
  const groups = groupByStatus(tasks.data ?? []);

  if (project.error) {
    return (
      <section>
        <p className="error" role="alert">{project.error}</p>
        <Link to="/portal">Back to your projects</Link>
      </section>
    );
  }
  if (!project.data) return <p className="muted">Loading…</p>;

  const openTask = (taskId: string | null) => setSearchParams(taskId ? { task: taskId } : {});

  return (
    <section aria-labelledby="portal-project-title">
      <p className="muted"><Link to="/portal">Your projects</Link></p>
      <h1 id="portal-project-title">{project.data.name}</h1>

      {dashboard.data && (
        <dl className="stats" aria-label="Project progress">
          {STATUSES.map((s) => (
            <div key={s}><dt>{STATUS_LABELS[s]}</dt><dd>{dashboard.data?.task_counts[s]}</dd></div>
          ))}
          <div><dt>Hours worked</dt><dd>{dashboard.data.total_hours}</dd></div>
        </dl>
      )}

      <form className="filters" role="search" onSubmit={(e) => {
        e.preventDefault();
        setQ(search.trim() || undefined);
      }}>
        <input type="search" aria-label="Search tasks" placeholder="Search tasks"
               value={search} onChange={(e) => setSearch(e.target.value)} />
        <button type="submit">Search</button>
      </form>

      {tasks.error && <p className="error" role="alert">{tasks.error}</p>}
      {tasks.data && tasks.data.length === 0 && <p className="muted">No tasks to show.</p>}
      <div className="board">
        {STATUSES.map((status) => (
          <section key={status} className="column" aria-label={STATUS_LABELS[status]}>
            <h2>{STATUS_LABELS[status]} <span className="muted">{groups[status].length}</span></h2>
            <ul>
              {groups[status].map((t) => (
                <li key={t.id}>
                  <button type="button" className="task-card" onClick={() => openTask(t.id)}>
                    <span>{t.title}</span>
                    <span className="task-meta">
                      <span className={`badge priority-${t.priority}`}>{PRIORITY_LABELS[t.priority]}</span>
                      {t.due_date && <span className="muted">Due {formatDate(t.due_date)}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {openTaskId && (
        <PortalTaskPanel taskId={openTaskId} onClose={() => openTask(null)}
                         onChanged={() => setChanges((n) => n + 1)} />
      )}
    </section>
  );
}
