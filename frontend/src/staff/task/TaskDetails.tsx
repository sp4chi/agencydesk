import { useState, type FormEvent } from "react";

import type { StaffTask, TaskUpdate } from "../../api/types";
import { useActiveSession } from "../../auth/SessionProvider";
import { PRIORITIES, PRIORITY_LABELS, STATUSES, STATUS_LABELS } from "../../shared/format";
import { errorText, useLoad } from "../../shared/useLoad";

interface Props {
  task: StaffTask;
  projectId: string;
  onSaved: () => void;
}

/** Only the fields that changed, so PATCH doesn't overwrite anything else. */
export function changedFields(original: StaffTask, draft: StaffTask): TaskUpdate {
  const changes: TaskUpdate = {};
  if (draft.title !== original.title) changes.title = draft.title;
  if (draft.description !== original.description) changes.description = draft.description;
  if (draft.status !== original.status) changes.status = draft.status;
  if (draft.priority !== original.priority) changes.priority = draft.priority;
  if (draft.visibility !== original.visibility) changes.visibility = draft.visibility;
  if (draft.assignee_user_id !== original.assignee_user_id) changes.assignee_user_id = draft.assignee_user_id;
  if (draft.due_date !== original.due_date) changes.due_date = draft.due_date;
  return changes;
}

export function TaskDetails({ task, projectId, onSaved }: Props) {
  const { api } = useActiveSession();
  const members = useLoad(() => api.projects.members(projectId), [api, projectId]);
  const [draft, setDraft] = useState<StaffTask>(task);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const changes = changedFields(task, draft);
  const dirty = Object.keys(changes).length > 0;

  function set<K extends keyof StaffTask>(key: K, value: StaffTask[K]) {
    setSaved(false);
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      // Use the server's copy (e.g. a trimmed title), so the form isn't left "dirty".
      setDraft(await api.tasks.update(task.id, changes));
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form className="task-details" onSubmit={save}>
      <label className="title-field">
        <span className="visually-hidden">Title</span>
        <input id="drawer-title" required value={draft.title} onChange={(e) => set("title", e.target.value)} />
      </label>
      <div className="field-grid">
        <label>
          Status
          <select value={draft.status} onChange={(e) => set("status", e.target.value as StaffTask["status"])}>
            {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
        </label>
        <label>
          Priority
          <select value={draft.priority} onChange={(e) => set("priority", e.target.value as StaffTask["priority"])}>
            {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
          </select>
        </label>
        <label>
          Assignee
          <select value={draft.assignee_user_id ?? ""}
                  onChange={(e) => set("assignee_user_id", e.target.value || null)}>
            <option value="">Unassigned</option>
            {members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
          </select>
        </label>
        <label>
          Due date
          <input type="date" value={draft.due_date ?? ""} onChange={(e) => set("due_date", e.target.value || null)} />
        </label>
        <label>
          Who can see it
          <select value={draft.visibility} onChange={(e) => set("visibility", e.target.value as StaffTask["visibility"])}>
            <option value="internal">Internal (agency only)</option>
            <option value="client">Shared with client</option>
          </select>
        </label>
      </div>
      {draft.visibility === "internal" && task.visibility === "client" && (
        <p className="notice">Making this internal also hides its comments and files from the client.</p>
      )}
      <label>
        Description
        <textarea rows={4} value={draft.description} onChange={(e) => set("description", e.target.value)} />
      </label>
      <div className="form-actions">
        <button type="submit" disabled={!dirty}>Save changes</button>
        {saved && !dirty && <span className="muted" role="status">Saved</span>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}
