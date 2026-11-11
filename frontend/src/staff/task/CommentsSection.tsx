// Comments with a visibility toggle. New comments default to "Internal note";
// sharing with the client is an explicit choice. The badge shows what the
// client will actually see (comment AND task must both be shared).

import { useState, type FormEvent } from "react";

import type { StaffComment, Visibility } from "../../api/types";
import { useActiveSession } from "../../auth/SessionProvider";
import { formatDate } from "../../shared/format";
import { errorText, useLoad } from "../../shared/useLoad";

export function commentBadge(comment: StaffComment): { label: string; className: string } {
  if (comment.visible_to_client) return { label: "Visible to client", className: "shared" };
  if (comment.visibility === "client") {
    return { label: "Hidden: task is internal", className: "internal" };
  }
  return { label: "Internal note", className: "internal" };
}

export function CommentsSection({ taskId, taskVisibility }: { taskId: string; taskVisibility: Visibility }) {
  const { api } = useActiveSession();
  const comments = useLoad(() => api.comments.list(taskId), [api, taskId]);
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("internal");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.comments.create(taskId, body, visibility);
      setBody("");
      setVisibility("internal"); // back to the safe default after each comment
      comments.reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="drawer-section" aria-labelledby="comments-title">
      <h2 id="comments-title">Comments</h2>
      {comments.error && <p className="error" role="alert">{comments.error}</p>}
      <ul className="list">
        {comments.data?.map((c) => {
          const badge = commentBadge(c);
          return (
            <li key={c.id} className="comment">
              <div className="comment-head">
                <strong>{c.author_name}</strong>
                <span className="muted">{formatDate(c.created_at)}</span>
                <span className={`badge ${badge.className}`}>{badge.label}</span>
              </div>
              <p>{c.body}</p>
            </li>
          );
        })}
      </ul>
      <form onSubmit={submit} className="composer">
        <label>
          <span className="visually-hidden">Comment</span>
          <textarea rows={3} required placeholder="Write a comment" value={body}
                    onChange={(e) => setBody(e.target.value)} />
        </label>
        <fieldset className="segmented">
          <legend className="visually-hidden">Who can see this comment</legend>
          <label>
            <input type="radio" name="comment-visibility" value="internal"
                   checked={visibility === "internal"} onChange={() => setVisibility("internal")} />
            Internal note
          </label>
          <label>
            <input type="radio" name="comment-visibility" value="client"
                   checked={visibility === "client"} onChange={() => setVisibility("client")} />
            Reply to client
          </label>
        </fieldset>
        {visibility === "client" && taskVisibility === "internal" && (
          <p className="notice">This task is internal, so the client won't see this comment until the task is shared.</p>
        )}
        <button type="submit">Post comment</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </section>
  );
}
