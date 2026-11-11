"""SQL for projects and project members. Runs under get_tenant_db: RLS
(app.can_access_project) decides which projects exist for the caller, and
only staff can read project_members. No query here filters by agency."""
import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class ProjectRow:
    id: uuid.UUID
    name: str
    client_id: uuid.UUID
    client_name: str
    created_at: dt.datetime


@dataclass(frozen=True)
class ProjectMemberRow:
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    added_at: dt.datetime


_PROJECT_SELECT = """
    SELECT p.id, p.name, p.client_id, c.name AS client_name, p.created_at
    FROM projects p
    JOIN clients c ON c.agency_id = p.agency_id AND c.id = p.client_id
"""


def list_projects(conn: Connection) -> list[ProjectRow]:
    rows = conn.execute(text(_PROJECT_SELECT + " ORDER BY p.created_at, p.name"))
    return [ProjectRow(**r._asdict()) for r in rows]


def get_project(conn: Connection, project_id: uuid.UUID) -> ProjectRow | None:
    row = conn.execute(
        text(_PROJECT_SELECT + " WHERE p.id = :id"), {"id": project_id}
    ).one_or_none()
    return ProjectRow(**row._asdict()) if row else None


def create_project(
    conn: Connection, agency_id: uuid.UUID, client_id: uuid.UUID, name: str
) -> uuid.UUID:
    return conn.execute(
        text(
            """INSERT INTO projects (agency_id, client_id, name)
               VALUES (:agency_id, :client_id, :name) RETURNING id"""
        ),
        {"agency_id": agency_id, "client_id": client_id, "name": name},
    ).scalar_one()


# ------------------------------------------------------------- members
def list_members(conn: Connection, project_id: uuid.UUID) -> list[ProjectMemberRow]:
    rows = conn.execute(
        text(
            """SELECT pm.user_id, u.name, u.email, m.role, pm.added_at
               FROM project_members pm
               JOIN users u ON u.id = pm.user_id
               JOIN agency_memberships m
                 ON m.agency_id = pm.agency_id AND m.user_id = pm.user_id
               WHERE pm.project_id = :project_id
               ORDER BY u.name"""
        ),
        {"project_id": project_id},
    )
    return [ProjectMemberRow(**r._asdict()) for r in rows]


def is_active_staff(conn: Connection, user_id: uuid.UUID) -> bool:
    return conn.execute(
        text(
            """SELECT EXISTS (
                 SELECT 1 FROM agency_memberships
                 WHERE user_id = :user_id AND is_staff AND removed_at IS NULL)"""
        ),
        {"user_id": user_id},
    ).scalar_one()


def add_member(
    conn: Connection, agency_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    conn.execute(
        text(
            """INSERT INTO project_members (agency_id, project_id, user_id)
               VALUES (:agency_id, :project_id, :user_id)"""
        ),
        {"agency_id": agency_id, "project_id": project_id, "user_id": user_id},
    )


def count_assigned_tasks(conn: Connection, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return conn.execute(
        text(
            """SELECT count(*) FROM tasks
               WHERE project_id = :project_id AND assignee_user_id = :user_id"""
        ),
        {"project_id": project_id, "user_id": user_id},
    ).scalar_one()


def remove_member(conn: Connection, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Deleting the row is all it takes: the tasks FK
    ON DELETE SET NULL (assignee_user_id) unassigns their tasks on this
    project, and the tasks_assignee_log trigger records each one as
    auto_unassigned_member_removed. Don't reimplement that here."""
    result = conn.execute(
        text("DELETE FROM project_members WHERE project_id = :project_id AND user_id = :user_id"),
        {"project_id": project_id, "user_id": user_id},
    )
    return result.rowcount == 1
