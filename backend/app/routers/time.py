"""Time entries (staff only) and the project hours summary (everyone)."""
import uuid

from fastapi import APIRouter, Depends, status

from app.db import TenantDb, get_tenant_db
from app.repositories.time_entries import TimeEntryRow
from app.schemas.time_entries import (
    ProjectHours,
    StaffTimeEntry,
    TimeEntryCreate,
    TimeEntryUpdate,
)
from app.services import time_entries as service

router = APIRouter(tags=["time"])


def _entry(row: TimeEntryRow) -> StaffTimeEntry:
    return StaffTimeEntry(
        id=row.id, task_id=row.task_id, user_id=row.user_id, user_name=row.user_name,
        minutes=row.minutes, entry_date=row.entry_date, note=row.note, created_at=row.created_at,
    )


@router.get("/tasks/{task_id}/time-entries", response_model=list[StaffTimeEntry])
def list_entries(task_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> list[StaffTimeEntry]:
    return [_entry(row) for row in service.list_entries(db, task_id)]


@router.post(
    "/tasks/{task_id}/time-entries", response_model=StaffTimeEntry, status_code=status.HTTP_201_CREATED
)
def log_time(
    task_id: uuid.UUID, body: TimeEntryCreate, db: TenantDb = Depends(get_tenant_db)
) -> StaffTimeEntry:
    return _entry(service.log_time(db, task_id, body.minutes, body.entry_date, body.note))


@router.patch("/time-entries/{entry_id}", response_model=StaffTimeEntry)
def update_entry(
    entry_id: uuid.UUID, body: TimeEntryUpdate, db: TenantDb = Depends(get_tenant_db)
) -> StaffTimeEntry:
    return _entry(service.update_entry(db, entry_id, body.model_dump(exclude_unset=True)))


@router.get("/projects/{project_id}/hours", response_model=ProjectHours)
def project_hours(project_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> ProjectHours:
    return ProjectHours(project_id=project_id, total_hours=service.project_hours(db, project_id))
