// Task board: one column per status, with filters and search. Filtering and
// search happen on the server, so they go through the same RLS checks as
// everything else.

import { useState, type FormEvent } from "react";

import type { TaskFilters, TaskPriority } from "../api/types";
import { useActiveSession } from "../auth/SessionProvider";
import { PRIORITIES, PRIORITY_LABELS, STATUSES, STATUS_LABELS, formatDate, groupByStatus } from "../shared/format";
import { errorText, useLoad } from "../shared/useLoad";

interface Props {
  projectId: string;
  refreshKey: number;
  onOpenTask: (taskId: string) => void;
  onChanged: () => void;
}

export function TaskBoard({ projectId, refreshKey, onOpenTask, onChanged }: Props) {
  const { api } = useActiveSession();
  const [filters, setFilters] = useState<TaskFilters>({});
  const [search, setSearch] = useState("");
  const members = useLoad(() => api.projects.members(projectId), [api, projectId]);
  const tasks = useLoad(
    () => api.tasks.list(projectId, filters),
    [api, projectId, filters, refreshKey],
  );
  const columns = groupByStatus(tasks.data ?? []);

  return (
    <div>
      <form className="filters" role="search" onSubmit={(e) => {
        e.preventDefault();
        setFilters((f) => ({ ...f, q: search.trim() || undefined }));
      }}>
        <input type="search" aria-label="Search tasks" placeholder="Search title and description"
               value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Priority" value={filters.priority ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, priority: (e.target.value || undefined) as TaskPriority | undefined }))}>
          <option value="">Any priority</option>
          {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
        </select>
        <select aria-label="Assignee" value={filters.assignee ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, assignee: e.target.value || undefined }))}>
          <option value="">Anyone</option>
          <option value="me">Assigned to me</option>
          <option value="unassigned">Unassigned</option>
          {members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
        </select>
        <button type="submit">Search</button>
      </form>

      {tasks.error && <p className="error" role="alert">{tasks.error}</p>}

      <div className="board">
        {STATUSES.map((status) => (
          <section key={status} className="column" aria-label={STATUS_LABELS[status]}>
            <h2>{STATUS_LABELS[status]} <span className="muted">{columns[status].length}</span></h2>
            <ul>
              {columns[status].map((t) => (
                <li key={t.id}>
                  <button type="button" className="task-card" onClick={() => onOpenTask(t.id)}>
                    <span>{t.title}</span>
                    <span className="task-meta">
                      <span className={`badge priority-${t.priority}`}>{PRIORITY_LABELS[t.priority]}</span>
                      {t.visibility === "client"
                        ? <span className="badge shared">Shared with client</span>
                        : <span className="badge internal">Internal</span>}
                      <span className="muted">{t.assignee_name ?? "Unassigned"}</span>
                      {t.due_date && <span className="muted">Due {formatDate(t.due_date)}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <NewTaskForm projectId={projectId} onCreated={onChanged} />
    </div>
  );
}

function NewTaskForm({ projectId, onCreated }: { projectId: string; onCreated: () => void }) {
  const { api } = useActiveSession();
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      // New tasks are internal: sharing with the client is a deliberate step.
      await api.tasks.create(projectId, { title });
      setTitle("");
      onCreated();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form className="inline-form" onSubmit={submit}>
      <label>
        New task
        <input required placeholder="What needs doing?" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <button type="submit">Add task</button>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}
