"""SQL for task files. Runs under get_tenant_db.

No visibility filter here: the files read policy shows a client user only
files where the file AND its task are client-visible. The files update
policy plus the files_client_guard trigger let a client change nothing
but the approval decision.
"""
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class FileRow:
    id: uuid.UUID
    task_id: uuid.UUID
    storage_key: str
    filename: str
    content_type: str
    size_bytes: int
    visibility: str
    task_visibility: str
    approval_status: str
    reviewed_by: uuid.UUID | None
    reviewed_by_name: str | None
    reviewed_at: dt.datetime | None
    uploaded_by: uuid.UUID
    uploaded_by_name: str
    created_at: dt.datetime


_SELECT = """
    SELECT f.id, f.task_id, f.storage_key, f.filename, f.content_type, f.size_bytes,
           f.visibility, t.visibility AS task_visibility, f.approval_status,
           f.reviewed_by, reviewer.name AS reviewed_by_name, f.reviewed_at,
           f.uploaded_by, uploader.name AS uploaded_by_name, f.created_at
    FROM files f
    JOIN tasks t ON t.agency_id = f.agency_id AND t.id = f.task_id
    JOIN users uploader ON uploader.id = f.uploaded_by
    LEFT JOIN users reviewer ON reviewer.id = f.reviewed_by
"""

UPDATABLE_COLUMNS = frozenset({"filename", "visibility"})


def list_files(conn: Connection, task_id: uuid.UUID) -> list[FileRow]:
    rows = conn.execute(
        text(_SELECT + " WHERE f.task_id = :task_id ORDER BY f.created_at, f.id"),
        {"task_id": task_id},
    )
    return [FileRow(**r._asdict()) for r in rows]


def get_file(conn: Connection, file_id: uuid.UUID) -> FileRow | None:
    row = conn.execute(text(_SELECT + " WHERE f.id = :id"), {"id": file_id}).one_or_none()
    return FileRow(**row._asdict()) if row else None


def create_file(conn: Connection, values: dict[str, Any]) -> uuid.UUID:
    return conn.execute(
        text(
            """INSERT INTO files (agency_id, task_id, uploaded_by, storage_key, filename,
                                  content_type, size_bytes, visibility)
               VALUES (:agency_id, :task_id, :uploaded_by, :storage_key, :filename,
                       :content_type, :size_bytes, :visibility)
               RETURNING id"""
        ),
        values,
    ).scalar_one()


def update_file(conn: Connection, file_id: uuid.UUID, changes: dict[str, Any]) -> bool:
    unknown = set(changes) - UPDATABLE_COLUMNS
    if unknown:  # column names go into the SQL text, so only allow known ones
        raise ValueError(f"not updatable: {sorted(unknown)}")
    assignments = ", ".join(f"{column} = :{column}" for column in sorted(changes))
    result = conn.execute(
        text(f"UPDATE files SET {assignments} WHERE id = :id"), {"id": file_id, **changes}
    )
    return result.rowcount == 1


def record_review(
    conn: Connection, file_id: uuid.UUID, decision: str, reviewer_id: uuid.UUID
) -> bool:
    # reviewed_at is set by the files_client_guard trigger.
    result = conn.execute(
        text("UPDATE files SET approval_status = :decision, reviewed_by = :reviewer WHERE id = :id"),
        {"id": file_id, "decision": decision, "reviewer": reviewer_id},
    )
    return result.rowcount == 1
