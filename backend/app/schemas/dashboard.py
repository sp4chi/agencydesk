"""Project dashboard. Same shape for staff and clients; the numbers differ,
because both come from queries that run under RLS (a client's counts and
hours only include client-visible tasks)."""
import uuid

from pydantic import BaseModel


class TaskCounts(BaseModel):
    todo: int
    in_progress: int
    in_review: int
    done: int


class ProjectDashboard(BaseModel):
    project_id: uuid.UUID
    project_name: str
    task_counts: TaskCounts
    total_tasks: int
    total_hours: float
