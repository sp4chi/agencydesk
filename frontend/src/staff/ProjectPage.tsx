// One project: summary numbers, then the task board or the team.
// The open task lives in the URL (?task=<id>) so it can be linked and the
// back button closes it.

import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useActiveSession } from "../auth/SessionProvider";
import { STATUSES, STATUS_LABELS } from "../shared/format";
import { useLoad } from "../shared/useLoad";
import { MembersPanel } from "./MembersPanel";
import { TaskBoard } from "./TaskBoard";
import { TaskDrawer } from "./task/TaskDrawer";

type Tab = "board" | "members";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const { api } = useActiveSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>("board");
  // Bumped after any task change so the board and the numbers refresh.
  const [changes, setChanges] = useState(0);
  const project = useLoad(() => api.projects.get(projectId), [api, projectId]);
  const dashboard = useLoad(() => api.projects.dashboard(projectId), [api, projectId, changes]);
  const openTaskId = searchParams.get("task");

  if (project.error) {
    return (
      <section>
        <p className="error" role="alert">{project.error}</p>
        <Link to="/">Back to projects</Link>
      </section>
    );
  }
  if (!project.data) return <p className="muted">Loading…</p>;

  const openTask = (taskId: string | null) =>
    setSearchParams(taskId ? { task: taskId } : {}, { replace: false });

  return (
    <section aria-labelledby="project-title">
      <p className="muted"><Link to="/">Projects</Link> / {project.data.client_name}</p>
      <h1 id="project-title">{project.data.name}</h1>

      {dashboard.data && (
        <dl className="stats" aria-label="Project summary">
          {STATUSES.map((s) => (
            <div key={s}><dt>{STATUS_LABELS[s]}</dt><dd>{dashboard.data?.task_counts[s]}</dd></div>
          ))}
          <div><dt>Hours logged</dt><dd>{dashboard.data.total_hours}</dd></div>
        </dl>
      )}

      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "board"} onClick={() => setTab("board")}>
          Task board
        </button>
        <button type="button" role="tab" aria-selected={tab === "members"} onClick={() => setTab("members")}>
          Team
        </button>
      </div>

      {tab === "board" ? (
        <TaskBoard projectId={projectId} refreshKey={changes} onOpenTask={openTask}
                   onChanged={() => setChanges((n) => n + 1)} />
      ) : (
        <MembersPanel projectId={projectId} onChanged={() => setChanges((n) => n + 1)} />
      )}

      {openTaskId && (
        <TaskDrawer taskId={openTaskId} projectId={projectId} onClose={() => openTask(null)}
                    onChanged={() => setChanges((n) => n + 1)} />
      )}
    </section>
  );
}
