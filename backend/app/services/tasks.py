"""Task rules.

Who can do what (also enforced by RLS):
  * read: staff on the project (admins: every project) see all its tasks;
    client users see only client-visible tasks of their own client's projects.
  * create / update: staff on the project. Client users can do neither
    (no task creation, no status changes).
"""
import uuid
from typing import Any, NoReturn

from sqlalchemy.exc import IntegrityError

from app.db import TenantDb
from app.errors import FOREIGN_KEY_VIOLATION, Forbidden, Invalid, NotFound, sqlstate
from app.repositories import projects as project_repository
from app.repositories import tasks as repository
from app.repositories.tasks import TaskFilters, TaskRow

ASSIGNEE_NOT_ON_PROJECT = "The assignee must be a member of this project"


def _require_staff(db: TenantDb, action: str) -> None:
    if not db.is_staff:
        raise Forbidden(f"Client users can't {action}")


def _require_visible_project(db: TenantDb, project_id: uuid.UUID) -> None:
    if project_repository.get_project(db.conn, project_id) is None:
        raise NotFound()


def _get_visible_task(db: TenantDb, task_id: uuid.UUID) -> TaskRow:
    task = repository.get_task(db.conn, task_id)
    if task is None:  # doesn't exist, other agency, not on the project, or internal: same answer
        raise NotFound()
    return task


def list_tasks(db: TenantDb, project_id: uuid.UUID, filters: TaskFilters) -> list[TaskRow]:
    _require_visible_project(db, project_id)
    if filters.assignee is not None and not db.is_staff:
        # Assignees are staff-only information; even filtering by them would
        # let a client probe who works on what.
        raise Forbidden("The assignee filter is for staff only")
    if filters.assignee == "me":
        filters = TaskFilters(filters.status, filters.priority, db.user_id, filters.q)
    return repository.list_tasks(db.conn, project_id, filters)


def get_task(db: TenantDb, task_id: uuid.UUID) -> TaskRow:
    return _get_visible_task(db, task_id)


def _translate_assignee_error(exc: IntegrityError) -> NoReturn:
    # Composite FK tasks(agency_id, project_id, assignee_user_id) ->
    # project_members: someone not on this project (or in another agency) fails.
    if sqlstate(exc) == FOREIGN_KEY_VIOLATION:
        raise Invalid(ASSIGNEE_NOT_ON_PROJECT) from None
    raise exc


def create_task(db: TenantDb, project_id: uuid.UUID, fields: dict[str, Any]) -> TaskRow:
    _require_staff(db, "create tasks")
    _require_visible_project(db, project_id)
    fields = {**fields, "title": fields["title"].strip()}
    if not fields["title"]:
        raise Invalid("Title is required")
    try:
        task_id = repository.create_task(db.conn, db.agency_id, project_id, db.user_id, fields)
    except IntegrityError as exc:
        _translate_assignee_error(exc)
    return _get_visible_task(db, task_id)


def update_task(db: TenantDb, task_id: uuid.UUID, changes: dict[str, Any]) -> TaskRow:
    _require_staff(db, "change tasks")
    _get_visible_task(db, task_id)
    if "title" in changes:
        changes = {**changes, "title": (changes["title"] or "").strip()}
        if not changes["title"]:
            raise Invalid("Title can't be empty")
    for required in ("status", "priority", "visibility", "description"):
        if required in changes and changes[required] is None:
            raise Invalid(f"{required} can't be null")
    if changes:
        try:
            updated = repository.update_task(db.conn, task_id, changes)
        except IntegrityError as exc:
            _translate_assignee_error(exc)
        if not updated:
            raise NotFound()
    return _get_visible_task(db, task_id)
