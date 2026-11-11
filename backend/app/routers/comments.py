"""Task comments. Thin: parse, call the service, pick StaffComment or ClientComment."""
import uuid

from fastapi import APIRouter, Depends, status

from app.db import TenantDb, get_tenant_db
from app.repositories.comments import CommentRow
from app.schemas.comments import ClientComment, CommentCreate, StaffComment
from app.services import comments as service

router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["comments"])


def _comment(db: TenantDb, row: CommentRow) -> StaffComment | ClientComment:
    if db.is_staff:
        return StaffComment(
            id=row.id, task_id=row.task_id, body=row.body, visibility=row.visibility,
            visible_to_client=(row.visibility == "client" and row.task_visibility == "client"),
            author_user_id=row.author_user_id, author_name=row.author_name,
            created_at=row.created_at,
        )
    return ClientComment(
        id=row.id, body=row.body, author_name=row.author_name, created_at=row.created_at
    )


@router.get("", response_model=list[StaffComment] | list[ClientComment])
def list_comments(
    task_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)
) -> list[StaffComment] | list[ClientComment]:
    return [_comment(db, row) for row in service.list_comments(db, task_id)]


@router.post("", response_model=StaffComment | ClientComment, status_code=status.HTTP_201_CREATED)
def create_comment(
    task_id: uuid.UUID, body: CommentCreate, db: TenantDb = Depends(get_tenant_db)
) -> StaffComment | ClientComment:
    return _comment(db, service.create_comment(db, task_id, body.body, body.visibility))
