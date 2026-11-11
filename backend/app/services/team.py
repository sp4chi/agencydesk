"""The agency's active staff. Staff only: client users don't get a
directory of the agency's team."""
from app.db import TenantDb
from app.errors import Forbidden
from app.repositories import team as repository
from app.repositories.team import TeamMemberRow


def list_staff(db: TenantDb) -> list[TeamMemberRow]:
    if not db.is_staff:
        raise Forbidden("Staff only")
    return repository.list_active_staff(db.conn)
