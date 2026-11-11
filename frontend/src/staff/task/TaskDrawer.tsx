// Side panel for one task: details, comments, files and time.

import { useEffect } from "react";

import { useActiveSession } from "../../auth/SessionProvider";
import { useLoad } from "../../shared/useLoad";
import { CommentsSection } from "./CommentsSection";
import { FilesSection } from "./FilesSection";
import { TaskDetails } from "./TaskDetails";
import { TimeSection } from "./TimeSection";

interface Props {
  taskId: string;
  projectId: string;
  onClose: () => void;
  onChanged: () => void;
}

export function TaskDrawer({ taskId, projectId, onClose, onChanged }: Props) {
  const { api } = useActiveSession();
  const task = useLoad(() => api.tasks.get(taskId), [api, taskId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"
             onClick={(e) => e.stopPropagation()}>
        <button type="button" className="link-button drawer-close" onClick={onClose} aria-label="Close task">
          Close
        </button>
        {task.error && <p className="error" role="alert">{task.error}</p>}
        {task.data && (
          <>
            {/* key: a fresh form per task; after a save the form takes the server's copy itself */}
            <TaskDetails key={task.data.id} task={task.data}
                         projectId={projectId} onSaved={() => {
              task.reload();
              onChanged();
            }} />
            <CommentsSection taskId={taskId} taskVisibility={task.data.visibility} />
            <FilesSection taskId={taskId} taskVisibility={task.data.visibility} />
            <TimeSection taskId={taskId} onLogged={onChanged} />
          </>
        )}
      </aside>
    </div>
  );
}
