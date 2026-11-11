"""Project and project-membership rules.

Reads are scoped by RLS alone (admin: all; member: projects they're on;
client: their client's projects). Writes are admin-only: checked here for a
clear 403, and enforced again by the RLS `write` policies.
"""
import uuid

from sqlalchemy.exc import IntegrityError

from app.db import TenantDb
from app.errors import (
    FOREIGN_KEY_VIOLATION,
    UNIQUE_VIOLATION,
    Conflict,
    Forbidden,
    Invalid,
    NotFound,
    sqlstate,
)
from app.repositories import projects as repository
from app.repositories.projects import ProjectMemberRow, ProjectRow


def _require_admin(db: TenantDb, action: str) -> None:
    if db.role != "agency_admin":
        raise Forbidden(f"Only agency admins can {action}")


def _get_visible_project(db: TenantDb, project_id: uuid.UUID) -> ProjectRow:
    project = repository.get_project(db.conn, project_id)
    if project is None:  # doesn't exist, other agency, or not on it: same answer
        raise NotFound()
    return project


def list_projects(db: TenantDb) -> list[ProjectRow]:
    return repository.list_projects(db.conn)


def get_project(db: TenantDb, project_id: uuid.UUID) -> ProjectRow:
    return _get_visible_project(db, project_id)


def create_project(db: TenantDb, client_id: uuid.UUID, name: str) -> ProjectRow:
    _require_admin(db, "create projects")
    name = name.strip()
    if not name:
        raise Invalid("Name is required")
    try:
        project_id = repository.create_project(db.conn, db.agency_id, client_id, name)
    except IntegrityError as exc:
        if sqlstate(exc) == FOREIGN_KEY_VIOLATION:
            # Composite FK (agency_id, client_id): another agency's client fails too.
            raise Invalid("Unknown client") from None
        raise
    return _get_visible_project(db, project_id)


# ------------------------------------------------------------- members
def list_members(db: TenantDb, project_id: uuid.UUID) -> list[ProjectMemberRow]:
    if not db.is_staff:
        raise Forbidden("Staff only")  # the team list is internal
    _get_visible_project(db, project_id)
    return repository.list_members(db.conn, project_id)


def add_member(db: TenantDb, project_id: uuid.UUID, user_id: uuid.UUID) -> list[ProjectMemberRow]:
    _require_admin(db, "change project members")
    _get_visible_project(db, project_id)
    # The FK only proves a staff membership row exists; it doesn't know about
    # removed_at. Same message for "removed", "a client" and "another agency's
    # user", so nothing about other tenants leaks.
    if not repository.is_active_staff(db.conn, user_id):
        raise Invalid("Only active staff members of this agency can be added to a project")
    try:
        repository.add_member(db.conn, db.agency_id, project_id, user_id)
    except IntegrityError as exc:
        if sqlstate(exc) == UNIQUE_VIOLATION:
            raise Conflict("Already a member of this project") from None
        raise
    return repository.list_members(db.conn, project_id)


def remove_member(db: TenantDb, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """Returns how many of their tasks on this project were unassigned.
    The unassignment and its task_events log are done by the database."""
    _require_admin(db, "change project members")
    _get_visible_project(db, project_id)
    assigned = repository.count_assigned_tasks(db.conn, project_id, user_id)
    if not repository.remove_member(db.conn, project_id, user_id):
        raise NotFound()
    return assigned
