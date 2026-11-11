"""Time tracking rules.

  * Raw time entries are staff-only. For client users every time-entry
    endpoint is 404, as if it didn't exist (notes are internal, and so are
    who worked and when).
  * Staff log time only as themselves, on tasks of projects they're on.
  * Editing: your own entries; admins can edit anyone's. No deleting
    (AGENTS.md: never hard-delete time entries).
  * Hours summary: anyone who can see the project gets a total. A client's
    total counts client-visible tasks only (app.project_hours()).
"""
import datetime as dt
import uuid
from typing import Any

from app.db import TenantDb
from app.errors import Forbidden, Invalid, NotFound
from app.repositories import tasks as task_repository
from app.repositories import time_entries as repository
from app.repositories.time_entries import TimeEntryRow


def _staff_only(db: TenantDb) -> None:
    if not db.is_staff:
        raise NotFound()  # not 403: clients shouldn't learn these endpoints hold anything


def _require_visible_task(db: TenantDb, task_id: uuid.UUID) -> None:
    if task_repository.get_task(db.conn, task_id) is None:
        raise NotFound()


def _get_visible_entry(db: TenantDb, entry_id: uuid.UUID) -> TimeEntryRow:
    entry = repository.get_entry(db.conn, entry_id)
    if entry is None:
        raise NotFound()
    return entry


def list_entries(db: TenantDb, task_id: uuid.UUID) -> list[TimeEntryRow]:
    _staff_only(db)
    _require_visible_task(db, task_id)
    return repository.list_entries(db.conn, task_id)


def log_time(
    db: TenantDb, task_id: uuid.UUID, minutes: int, entry_date: dt.date | None, note: str
) -> TimeEntryRow:
    _staff_only(db)
    _require_visible_task(db, task_id)
    entry_id = repository.create_entry(
        db.conn, db.agency_id, task_id, db.user_id, minutes, entry_date, note.strip()
    )
    return _get_visible_entry(db, entry_id)


def update_entry(db: TenantDb, entry_id: uuid.UUID, changes: dict[str, Any]) -> TimeEntryRow:
    _staff_only(db)
    entry = _get_visible_entry(db, entry_id)
    if entry.user_id != db.user_id and db.role != "agency_admin":
        raise Forbidden("You can only edit your own time entries")
    for field in ("minutes", "entry_date", "note"):
        if field in changes and changes[field] is None:
            raise Invalid(f"{field} can't be null")
    if "note" in changes:
        changes = {**changes, "note": changes["note"].strip()}
    if changes and not repository.update_entry(db.conn, entry_id, changes):
        raise NotFound()
    return _get_visible_entry(db, entry_id)


def project_hours(db: TenantDb, project_id: uuid.UUID) -> float:
    hours = repository.project_hours(db.conn, project_id)
    if hours is None:  # can't access the project
        raise NotFound()
    return float(hours)
