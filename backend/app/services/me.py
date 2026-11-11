from app.db import TenantDb
from app.repositories import me as repository
from app.schemas.auth import Me, MeAgency, MeClient, MeUser


class MeNotVisible(Exception):
    """The caller's own rows aren't visible. Should be impossible after
    get_tenant_db succeeded; treated as unauthenticated rather than leaking why."""


def get_me(db: TenantDb) -> Me:
    row = repository.load_me(db.conn, db.user_id, db.agency_id, db.client_id)
    if row is None:
        raise MeNotVisible
    return Me(
        user=MeUser(id=row.user_id, email=row.email, name=row.user_name),
        agency=MeAgency(id=row.agency_id, name=row.agency_name),
        role=db.role,
        client=MeClient(id=row.client_id, name=row.client_name) if row.client_id else None,
    )
