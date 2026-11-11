"""SQL for time entries. Runs under get_tenant_db.

The time_entries read policy is staff-only, so for a client user every
query here returns nothing. Project totals go through app.project_hours(),
which counts only client-visible tasks when the caller is a client.
"""
import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class TimeEntryRow:
    id: uuid.UUID
    task_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    minutes: int
    entry_date: dt.date
    note: str
    created_at: dt.datetime


_SELECT = """
    SELECT te.id, te.task_id, te.user_id, u.name AS user_name, te.minutes, te.entry_date,
           te.note, te.created_at
    FROM time_entries te
    JOIN users u ON u.id = te.user_id
"""

UPDATABLE_COLUMNS = frozenset({"minutes", "entry_date", "note"})


def list_entries(conn: Connection, task_id: uuid.UUID) -> list[TimeEntryRow]:
    rows = conn.execute(
        text(_SELECT + " WHERE te.task_id = :task_id ORDER BY te.entry_date, te.created_at"),
        {"task_id": task_id},
    )
    return [TimeEntryRow(**r._asdict()) for r in rows]


def get_entry(conn: Connection, entry_id: uuid.UUID) -> TimeEntryRow | None:
    row = conn.execute(text(_SELECT + " WHERE te.id = :id"), {"id": entry_id}).one_or_none()
    return TimeEntryRow(**row._asdict()) if row else None


def create_entry(
    conn: Connection, agency_id: uuid.UUID, task_id: uuid.UUID, user_id: uuid.UUID,
    minutes: int, entry_date: dt.date | None, note: str,
) -> uuid.UUID:
    return conn.execute(
        text(
            """INSERT INTO time_entries (agency_id, task_id, user_id, minutes, entry_date, note)
               VALUES (:agency_id, :task_id, :user_id, :minutes,
                       coalesce(:entry_date, current_date), :note)
               RETURNING id"""
        ),
        {
            "agency_id": agency_id, "task_id": task_id, "user_id": user_id,
            "minutes": minutes, "entry_date": entry_date, "note": note,
        },
    ).scalar_one()


def update_entry(conn: Connection, entry_id: uuid.UUID, changes: dict[str, Any]) -> bool:
    unknown = set(changes) - UPDATABLE_COLUMNS
    if unknown:  # column names go into the SQL text, so only allow known ones
        raise ValueError(f"not updatable: {sorted(unknown)}")
    assignments = ", ".join(f"{column} = :{column}" for column in sorted(changes))
    result = conn.execute(
        text(f"UPDATE time_entries SET {assignments} WHERE id = :id"), {"id": entry_id, **changes}
    )
    return result.rowcount == 1


def project_hours(conn: Connection, project_id: uuid.UUID) -> Decimal | None:
    """None if the caller can't access the project."""
    return conn.execute(
        text("SELECT app.project_hours(:project_id)"), {"project_id": project_id}
    ).scalar_one()
