"""Projects and project members. Thin: parse, call the service, pick the
response model for the caller (staff vs client)."""
import uuid

from fastapi import APIRouter, Depends, status

from app.db import TenantDb, get_tenant_db
from app.repositories.projects import ProjectMemberRow, ProjectRow
from app.schemas.projects import (
    ClientProject,
    ProjectCreate,
    ProjectMember,
    ProjectMemberAdd,
    ProjectMemberRemoved,
    StaffProject,
)
from app.services import projects as service

router = APIRouter(prefix="/projects", tags=["projects"])


def _project(db: TenantDb, row: ProjectRow) -> StaffProject | ClientProject:
    if db.is_staff:
        return StaffProject(
            id=row.id, name=row.name, client_id=row.client_id,
            client_name=row.client_name, created_at=row.created_at,
        )
    return ClientProject(id=row.id, name=row.name, created_at=row.created_at)


def _member(row: ProjectMemberRow) -> ProjectMember:
    return ProjectMember(
        user_id=row.user_id, name=row.name, email=row.email, role=row.role, added_at=row.added_at
    )


@router.get("", response_model=list[StaffProject] | list[ClientProject])
def list_projects(db: TenantDb = Depends(get_tenant_db)) -> list[StaffProject] | list[ClientProject]:
    return [_project(db, row) for row in service.list_projects(db)]


@router.get("/{project_id}", response_model=StaffProject | ClientProject)
def get_project(
    project_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)
) -> StaffProject | ClientProject:
    return _project(db, service.get_project(db, project_id))


@router.post("", response_model=StaffProject, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: TenantDb = Depends(get_tenant_db)) -> StaffProject:
    return _project(db, service.create_project(db, body.client_id, body.name))


@router.get("/{project_id}/members", response_model=list[ProjectMember])
def list_members(
    project_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)
) -> list[ProjectMember]:
    return [_member(row) for row in service.list_members(db, project_id)]


@router.post(
    "/{project_id}/members", response_model=list[ProjectMember], status_code=status.HTTP_201_CREATED
)
def add_member(
    project_id: uuid.UUID, body: ProjectMemberAdd, db: TenantDb = Depends(get_tenant_db)
) -> list[ProjectMember]:
    return [_member(row) for row in service.add_member(db, project_id, body.user_id)]


@router.delete("/{project_id}/members/{user_id}", response_model=ProjectMemberRemoved)
def remove_member(
    project_id: uuid.UUID, user_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)
) -> ProjectMemberRemoved:
    return ProjectMemberRemoved(
        unassigned_task_count=service.remove_member(db, project_id, user_id)
    )
