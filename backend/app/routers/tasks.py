"""Tasks. Thin: parse, call the service, pick StaffTask or ClientTask."""
import uuid

from fastapi import APIRouter, Depends, Query, status

from app.db import TenantDb, get_tenant_db
from app.errors import Invalid
from app.repositories.tasks import TaskFilters, TaskRow
from app.schemas.tasks import ClientTask, StaffTask, TaskCreate, TaskPriority, TaskStatus, TaskUpdate
from app.services import tasks as service

router = APIRouter(tags=["tasks"])


def _task(db: TenantDb, row: TaskRow) -> StaffTask | ClientTask:
    if db.is_staff:
        return StaffTask(
            id=row.id, project_id=row.project_id, title=row.title, description=row.description,
            status=row.status, priority=row.priority, visibility=row.visibility,
            assignee_user_id=row.assignee_user_id, assignee_name=row.assignee_name,
            due_date=row.due_date, created_by=row.created_by,
            created_at=row.created_at, updated_at=row.updated_at,
        )
    return ClientTask(
        id=row.id, project_id=row.project_id, title=row.title, description=row.description,
        status=row.status, priority=row.priority, due_date=row.due_date,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _parse_assignee(value: str | None) -> uuid.UUID | str | None:
    if value is None or value in ("me", "unassigned"):
        return value
    try:
        return uuid.UUID(value)
    except ValueError:
        raise Invalid("assignee must be a user id, 'me' or 'unassigned'") from None


@router.get(
    "/projects/{project_id}/tasks", response_model=list[StaffTask] | list[ClientTask]
)
def list_tasks(
    project_id: uuid.UUID,
    status_: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    assignee: str | None = Query(default=None, description="user id, 'me' or 'unassigned' (staff only)"),
    q: str | None = Query(default=None, max_length=200, description="search title and description"),
    db: TenantDb = Depends(get_tenant_db),
) -> list[StaffTask] | list[ClientTask]:
    filters = TaskFilters(
        status=status_, priority=priority, assignee=_parse_assignee(assignee),
        q=q.strip() if q else None,
    )
    return [_task(db, row) for row in service.list_tasks(db, project_id, filters)]


@router.post(
    "/projects/{project_id}/tasks", response_model=StaffTask, status_code=status.HTTP_201_CREATED
)
def create_task(
    project_id: uuid.UUID, body: TaskCreate, db: TenantDb = Depends(get_tenant_db)
) -> StaffTask | ClientTask:
    return _task(db, service.create_task(db, project_id, body.model_dump()))


@router.get("/tasks/{task_id}", response_model=StaffTask | ClientTask)
def get_task(task_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> StaffTask | ClientTask:
    return _task(db, service.get_task(db, task_id))


@router.patch("/tasks/{task_id}", response_model=StaffTask)
def update_task(
    task_id: uuid.UUID, body: TaskUpdate, db: TenantDb = Depends(get_tenant_db)
) -> StaffTask | ClientTask:
    # exclude_unset: only fields the caller actually sent, so an explicit
    # null (unassign, clear due date) is different from "not sent".
    return _task(db, service.update_task(db, task_id, body.model_dump(exclude_unset=True)))
