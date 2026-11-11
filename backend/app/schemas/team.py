"""Agency team (staff) list, for pickers such as "add project member"."""
import uuid

from pydantic import BaseModel

from app.schemas.auth import Role


class TeamMember(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: Role
