// Time log for a task. You always log your own time: the request has no
// user field, and the server uses the session's user.

import { useState, type FormEvent } from "react";

import { useActiveSession } from "../../auth/SessionProvider";
import { formatDate, formatMinutes } from "../../shared/format";
import { errorText, useLoad } from "../../shared/useLoad";

export function TimeSection({ taskId, onLogged }: { taskId: string; onLogged: () => void }) {
  const { api } = useActiveSession();
  const entries = useLoad(() => api.time.list(taskId), [api, taskId]);
  const [minutes, setMinutes] = useState("");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const total = entries.data?.reduce((sum, e) => sum + e.minutes, 0) ?? 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.time.log(taskId, { minutes: Number(minutes), entry_date: date || undefined, note });
      setMinutes("");
      setNote("");
      entries.reload();
      onLogged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="drawer-section" aria-labelledby="time-title">
      <h2 id="time-title">Time <span className="muted">{formatMinutes(total)} total</span></h2>
      <p className="muted small">Time entries are internal. Clients only see project totals.</p>
      {entries.error && <p className="error" role="alert">{entries.error}</p>}
      <ul className="list">
        {entries.data?.map((e) => (
          <li key={e.id} className="list-row">
            <span><strong>{formatMinutes(e.minutes)}</strong> {e.user_name}
              {e.note && <span className="muted"> · {e.note}</span>}</span>
            <span className="muted">{formatDate(e.entry_date)}</span>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={submit}>
        <label>
          Minutes
          <input type="number" min={1} max={1440} required value={minutes}
                 onChange={(e) => setMinutes(e.target.value)} />
        </label>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Note
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit">Log time</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
