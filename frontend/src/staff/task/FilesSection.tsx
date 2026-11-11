// Files on a task: upload (internal by default), download, share/unshare,
// and the client's approval status.

import { useRef, useState, type FormEvent } from "react";

import { saveBlob } from "../../api/client";
import type { StaffFile, Visibility } from "../../api/types";
import { useActiveSession } from "../../auth/SessionProvider";
import { APPROVAL_LABELS, formatBytes } from "../../shared/format";
import { errorText, useLoad } from "../../shared/useLoad";

export function FilesSection({ taskId, taskVisibility }: { taskId: string; taskVisibility: Visibility }) {
  const { api } = useActiveSession();
  const files = useLoad(() => api.files.list(taskId), [api, taskId]);
  const input = useRef<HTMLInputElement>(null);
  const [visibility, setVisibility] = useState<Visibility>("internal");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      await api.files.upload(taskId, file, visibility);
      if (input.current) input.current.value = "";
      setVisibility("internal");
      files.reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function download(file: StaffFile) {
    setError(null);
    try {
      saveBlob(await api.files.download(file.id), file.filename);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function toggleVisibility(file: StaffFile) {
    setError(null);
    try {
      await api.files.update(file.id, { visibility: file.visibility === "client" ? "internal" : "client" });
      files.reload();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section className="drawer-section" aria-labelledby="files-title">
      <h2 id="files-title">Files</h2>
      {files.error && <p className="error" role="alert">{files.error}</p>}
      <ul className="list">
        {files.data?.map((f) => (
          <li key={f.id} className="list-row">
            <span>
              <strong>{f.filename}</strong>{" "}
              <span className="muted">{formatBytes(f.size_bytes)} · {f.uploaded_by_name}</span>
              <br />
              <span className={`badge ${f.visible_to_client ? "shared" : "internal"}`}>
                {f.visible_to_client ? "Visible to client" : f.visibility === "client" ? "Hidden: task is internal" : "Internal"}
              </span>{" "}
              {f.visibility === "client" && <span className="muted">{APPROVAL_LABELS[f.approval_status]}</span>}
            </span>
            <span className="row-actions">
              <button type="button" className="link-button" onClick={() => download(f)}>Download</button>
              <button type="button" className="link-button" onClick={() => toggleVisibility(f)}>
                {f.visibility === "client" ? "Make internal" : "Share with client"}
              </button>
            </span>
          </li>
        ))}
      </ul>
      <form className="inline-form" onSubmit={upload}>
        <label>
          Upload a file
          <input ref={input} type="file" required />
        </label>
        <label>
          Visible to
          <select value={visibility} onChange={(e) => setVisibility(e.target.value as Visibility)}>
            <option value="internal">Agency only</option>
            <option value="client">Client too</option>
          </select>
        </label>
        <button type="submit" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
      </form>
      {visibility === "client" && taskVisibility === "internal" && (
        <p className="notice">This task is internal, so the client won't see the file until the task is shared.</p>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
