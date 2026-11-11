"""SQL for tasks. Runs under get_tenant_db.

There is deliberately no `visibility = 'client'` filter here: the tasks
read policy already hides internal tasks from client users, for every
query shape (list, search, filters, by id). Adding it here would suggest
the repository is the guard; it isn't.
"""
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class TaskRow:
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    status: str
    priority: str
    visibility: str
    assignee_user_id: uuid.UUID | None
    assignee_name: str | None
    due_date: dt.date | None
    created_by: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


@dataclass(frozen=True)
class TaskFilters:
    status: str | None = None
    priority: str | None = None
    # A user id, or "unassigned".
    assignee: uuid.UUID | str | None = None
    q: str | None = None


_SELECT = """
    SELECT t.id, t.project_id, t.title, t.description, t.status, t.priority, t.visibility,
           t.assignee_user_id, u.name AS assignee_name, t.due_date, t.created_by,
           t.created_at, t.updated_at
    FROM tasks t
    LEFT JOIN users u ON u.id = t.assignee_user_id
"""

# Columns PATCH may change. project_id, created_by and agency_id are never updatable.
UPDATABLE_COLUMNS = frozenset(
    {"title", "description", "status", "priority", "visibility", "assignee_user_id", "due_date"}
)


def _escape_like(term: str) -> str:
    """So a search for "50%" or "a_b" matches those characters literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_tasks(conn: Connection, project_id: uuid.UUID, filters: TaskFilters) -> list[TaskRow]:
    where = ["t.project_id = :project_id"]
    params: dict[str, Any] = {"project_id": project_id}
    if filters.status:
        where.append("t.status = :status")
        params["status"] = filters.status
    if filters.priority:
        where.append("t.priority = :priority")
        params["priority"] = filters.priority
    if filters.assignee == "unassigned":
        where.append("t.assignee_user_id IS NULL")
    elif filters.assignee is not None:
        where.append("t.assignee_user_id = :assignee")
        params["assignee"] = filters.assignee
    if filters.q:
        where.append(
            "(t.title ILIKE :pattern ESCAPE '\\' OR t.description ILIKE :pattern ESCAPE '\\')"
        )
        params["pattern"] = f"%{_escape_like(filters.q)}%"
    sql = _SELECT + " WHERE " + " AND ".join(where) + " ORDER BY t.created_at, t.title"
    return [TaskRow(**r._asdict()) for r in conn.execute(text(sql), params)]


def get_task(conn: Connection, task_id: uuid.UUID) -> TaskRow | None:
    row = conn.execute(text(_SELECT + " WHERE t.id = :id"), {"id": task_id}).one_or_none()
    return TaskRow(**row._asdict()) if row else None


def create_task(
    conn: Connection, agency_id: uuid.UUID, project_id: uuid.UUID, created_by: uuid.UUID,
    fields: dict[str, Any],
) -> uuid.UUID:
    return conn.execute(
        text(
            """INSERT INTO tasks (agency_id, project_id, created_by, title, description, status,
                                  priority, visibility, assignee_user_id, due_date)
               VALUES (:agency_id, :project_id, :created_by, :title, :description, :status,
                       :priority, :visibility, :assignee_user_id, :due_date)
               RETURNING id"""
        ),
        {"agency_id": agency_id, "project_id": project_id, "created_by": created_by, **fields},
    ).scalar_one()


def update_task(conn: Connection, task_id: uuid.UUID, changes: dict[str, Any]) -> bool:
    """Returns False if no row was updated (not visible / not writable)."""
    unknown = set(changes) - UPDATABLE_COLUMNS
    if unknown:  # column names go into the SQL text, so only allow known ones
        raise ValueError(f"not updatable: {sorted(unknown)}")
    assignments = ", ".join(f"{column} = :{column}" for column in sorted(changes))
    result = conn.execute(
        text(f"UPDATE tasks SET {assignments} WHERE id = :id"), {"id": task_id, **changes}
    )
    return result.rowcount == 1
