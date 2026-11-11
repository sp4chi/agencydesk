"""SQL for the project dashboard. Runs under get_tenant_db.

The count has no visibility filter: the tasks read policy already hides
internal tasks from client users, so their counts simply don't include
them. Hours come from app.project_hours() (see repositories/time_entries.py).
"""
import uuid

from sqlalchemy import Connection, text


def task_counts_by_status(conn: Connection, project_id: uuid.UUID) -> dict[str, int]:
    rows = conn.execute(
        text("SELECT status, count(*) FROM tasks WHERE project_id = :project_id GROUP BY status"),
        {"project_id": project_id},
    )
    return {status: count for status, count in rows}
