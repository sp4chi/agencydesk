"""Project dashboard: task counts by status plus total hours.

Anyone who can see the project gets it. Nothing here branches on role:
the numbers differ between staff and clients only because every query
runs under RLS.
"""
import uuid
from dataclasses import dataclass

from app.db import TenantDb
from app.errors import NotFound
from app.repositories import dashboard as repository
from app.repositories import projects as project_repository
from app.repositories import time_entries as time_repository

STATUSES = ("todo", "in_progress", "in_review", "done")


@dataclass(frozen=True)
class Dashboard:
    project_id: uuid.UUID
    project_name: str
    task_counts: dict[str, int]
    total_hours: float


def project_dashboard(db: TenantDb, project_id: uuid.UUID) -> Dashboard:
    project = project_repository.get_project(db.conn, project_id)
    if project is None:
        raise NotFound()
    counts = repository.task_counts_by_status(db.conn, project_id)
    hours = time_repository.project_hours(db.conn, project_id)
    return Dashboard(
        project_id=project.id,
        project_name=project.name,
        task_counts={status: counts.get(status, 0) for status in STATUSES},
        total_hours=float(hours or 0),
    )
