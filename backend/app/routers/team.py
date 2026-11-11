"""Agency team list (staff only)."""
from fastapi import APIRouter, Depends

from app.db import TenantDb, get_tenant_db
from app.schemas.team import TeamMember
from app.services import team as service

router = APIRouter(prefix="/team", tags=["team"])


@router.get("/staff", response_model=list[TeamMember])
def list_staff(db: TenantDb = Depends(get_tenant_db)) -> list[TeamMember]:
    return [
        TeamMember(user_id=r.user_id, name=r.name, email=r.email, role=r.role)
        for r in service.list_staff(db)
    ]
