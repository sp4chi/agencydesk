"""Project dashboard (staff and clients)."""
import uuid

from fastapi import APIRouter, Depends

from app.db import TenantDb, get_tenant_db
from app.schemas.dashboard import ProjectDashboard, TaskCounts
from app.services import dashboard as service

router = APIRouter(tags=["dashboard"])


@router.get("/projects/{project_id}/dashboard", response_model=ProjectDashboard)
def project_dashboard(project_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> ProjectDashboard:
    result = service.project_dashboard(db, project_id)
    return ProjectDashboard(
        project_id=result.project_id,
        project_name=result.project_name,
        task_counts=TaskCounts(**result.task_counts),
        total_tasks=sum(result.task_counts.values()),
        total_hours=result.total_hours,
    )
