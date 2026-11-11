from fastapi import APIRouter, Depends

from app.db import UNAUTHORIZED, TenantDb, get_tenant_db
from app.schemas.auth import Me
from app.services import me as service

router = APIRouter(tags=["me"])


@router.get("/me", response_model=Me)
def get_me(db: TenantDb = Depends(get_tenant_db)) -> Me:
    try:
        return service.get_me(db)
    except service.MeNotVisible:
        raise UNAUTHORIZED from None
