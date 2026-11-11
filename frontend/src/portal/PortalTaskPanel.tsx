// A shared task, as the client sees it: details, files to download and
// approve, and the conversation. Clients can't change the task itself.

import { useEffect, useState, type FormEvent } from "react";

import { saveBlob } from "../api/client";
import type { ApprovalStatus, ClientFile, ReviewDecision } from "../api/types";
import { useActiveSession } from "../auth/SessionProvider";
import { PRIORITY_LABELS, STATUS_LABELS, formatBytes, formatDate } from "../shared/format";
import { errorText, useLoad } from "../shared/useLoad";

// Worded for the client ("you"), unlike the staff labels.
export const CLIENT_APPROVAL_LABELS: Record<ApprovalStatus, string> = {
  pending: "Waiting for your review",
  approved: "You approved this",
  changes_requested: "You requested changes",
};

interface Props {
  taskId: string;
  onClose: () => void;
  onChanged: () => void;
}

export function PortalTaskPanel({ taskId, onClose, onChanged }: Props) {
  const { api } = useActiveSession();
  const task = useLoad(() => api.portal.tasks.get(taskId), [api, taskId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="portal-task-title"
             onClick={(e) => e.stopPropagation()}>
        <button type="button" className="link-button drawer-close" onClick={onClose} aria-label="Close task">
          Close
        </button>
        {task.error && <p className="error" role="alert">{task.error}</p>}
        {task.data && (
          <>
            <h1 id="portal-task-title" className="drawer-title">{task.data.title}</h1>
            <p className="task-meta">
              <span className="badge">{STATUS_LABELS[task.data.status]}</span>
              <span className={`badge priority-${task.data.priority}`}>{PRIORITY_LABELS[task.data.priority]}</span>
              {task.data.due_date && <span className="muted">Due {formatDate(task.data.due_date)}</span>}
            </p>
            {task.data.description && <p className="description">{task.data.description}</p>}
            <PortalFiles taskId={taskId} onReviewed={onChanged} />
            <PortalComments taskId={taskId} />
          </>
        )}
      </aside>
    </div>
  );
}

export function PortalFiles({ taskId, onReviewed }: { taskId: string; onReviewed: () => void }) {
  const { api } = useActiveSession();
  const files = useLoad(() => api.portal.files.list(taskId), [api, taskId]);
  const [error, setError] = useState<string | null>(null);

  async function download(file: ClientFile) {
    setError(null);
    try {
      saveBlob(await api.portal.files.download(file.id), file.filename);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function review(file: ClientFile, decision: ReviewDecision) {
    setError(null);
    try {
      await api.portal.files.review(file.id, decision);
      files.reload();
      onReviewed();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="drawer-section" aria-labelledby="portal-files-title">
      <h2 id="portal-files-title">Files for review</h2>
      {files.data && files.data.length === 0 && <p className="muted">No files shared yet.</p>}
      <ul className="list">
        {files.data?.map((f) => (
          <li key={f.id} className="list-row">
            <span>
              <strong>{f.filename}</strong> <span className="muted">{formatBytes(f.size_bytes)}</span>
              <br />
              <span className={`badge ${f.approval_status === "approved" ? "shared" : ""}`}>
                {CLIENT_APPROVAL_LABELS[f.approval_status]}
              </span>
            </span>
            <span className="row-actions">
              <button type="button" className="link-button" onClick={() => void download(f)}>Download</button>
              <button type="button" className="link-button" disabled={f.approval_status === "approved"}
                      onClick={() => void review(f, "approved")}>Approve</button>
              <button type="button" className="link-button danger"
                      disabled={f.approval_status === "changes_requested"}
                      onClick={() => void review(f, "changes_requested")}>Request changes</button>
            </span>
          </li>
        ))}
      </ul>
      {(error ?? files.error) && <p className="error" role="alert">{error ?? files.error}</p>}
    </section>
  );
}

export function PortalComments({ taskId }: { taskId: string }) {
  const { api } = useActiveSession();
  const comments = useLoad(() => api.portal.comments.list(taskId), [api, taskId]);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.portal.comments.create(taskId, body);
      setBody("");
      comments.reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="drawer-section" aria-labelledby="portal-comments-title">
      <h2 id="portal-comments-title">Conversation</h2>
      {comments.data && comments.data.length === 0 && <p className="muted">No messages yet.</p>}
      <ul className="list">
        {comments.data?.map((c) => (
          <li key={c.id} className="comment">
            <div className="comment-head">
              <strong>{c.author_name}</strong>
              <span className="muted">{formatDate(c.created_at)}</span>
            </div>
            <p>{c.body}</p>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="composer">
        <label>
          <span className="visually-hidden">Message</span>
          <textarea rows={3} required placeholder="Write a message to the team" value={body}
                    onChange={(e) => setBody(e.target.value)} />
        </label>
        <p className="muted small">The agency team will see your message.</p>
        <button type="submit">Send</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </section>
  );
}
