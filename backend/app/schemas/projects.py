"""Request/response models for clients, projects and project members.

Projects have two response models: StaffProject for staff, ClientProject
for client users. ClientProject leaves out internal fields, as a second
guard on top of RLS (AGENTS.md rule 8).
"""
import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.schemas.auth import Role


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class StaffClient(BaseModel):
    id: uuid.UUID
    name: str
    created_at: dt.datetime


class ProjectCreate(BaseModel):
    client_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)


class StaffProject(BaseModel):
    id: uuid.UUID
    name: str
    client_id: uuid.UUID
    client_name: str
    created_at: dt.datetime


class ClientProject(BaseModel):
    id: uuid.UUID
    name: str
    created_at: dt.datetime


class ProjectMemberAdd(BaseModel):
    user_id: uuid.UUID


class ProjectMember(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: Role
    added_at: dt.datetime


class ProjectMemberRemoved(BaseModel):
    # Their tasks on this project that the database unassigned (and logged).
    unassigned_task_count: int
