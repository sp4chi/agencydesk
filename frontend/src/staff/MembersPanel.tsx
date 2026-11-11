// Project team. Admins can add active staff and remove people; removing
// someone unassigns their tasks on this project (done by the database).

import { useState } from "react";

import { useActiveSession } from "../auth/SessionProvider";
import { ROLE_LABELS } from "../shared/labels";
import { errorText, useLoad } from "../shared/useLoad";

export function MembersPanel({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const { api, session } = useActiveSession();
  const isAdmin = session.me.role === "agency_admin";
  const members = useLoad(() => api.projects.members(projectId), [api, projectId]);
  const staff = useLoad(() => (isAdmin ? api.team.staff() : Promise.resolve([])), [api, isAdmin]);
  const [toAdd, setToAdd] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const memberIds = new Set(members.data?.map((m) => m.user_id));
  const addable = staff.data?.filter((s) => !memberIds.has(s.user_id)) ?? [];

  async function add() {
    setError(null);
    setMessage(null);
    try {
      await api.projects.addMember(projectId, toAdd);
      setToAdd("");
      members.reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function remove(userId: string, name: string) {
    if (!window.confirm(`Remove ${name} from this project? Their tasks here will be unassigned.`)) return;
    setError(null);
    try {
      const result = await api.projects.removeMember(projectId, userId);
      const n = result.unassigned_task_count;
      setMessage(`${name} was removed. ${n} task${n === 1 ? " was" : "s were"} unassigned.`);
      members.reload();
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section aria-label="Project team">
      {members.error && <p className="error" role="alert">{members.error}</p>}
      <ul className="list">
        {members.data?.map((m) => (
          <li key={m.user_id} className="list-row">
            <span><strong>{m.name}</strong> <span className="muted">{m.email} · {ROLE_LABELS[m.role]}</span></span>
            {isAdmin && (
              <button type="button" className="link-button danger" onClick={() => remove(m.user_id, m.name)}>
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && (
        <div className="inline-form">
          <label>
            Add to project
            <select value={toAdd} onChange={(e) => setToAdd(e.target.value)}>
              <option value="">Choose a team member…</option>
              {addable.map((s) => <option key={s.user_id} value={s.user_id}>{s.name}</option>)}
            </select>
          </label>
          <button type="button" disabled={!toAdd} onClick={add}>Add</button>
        </div>
      )}
      {message && <p className="notice" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
