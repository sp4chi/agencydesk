"""Comment rules.

  * read: anyone who can see the task; client users only see comments
    where the comment and the task are both client-visible (RLS).
  * write: anyone who can see the task. Staff choose the visibility
    (default internal); a client user's comment is always 'client'.
"""
import uuid

from app.db import TenantDb
from app.errors import Invalid, NotFound
from app.repositories import comments as repository
from app.repositories import tasks as task_repository
from app.repositories.comments import CommentRow


def _require_visible_task(db: TenantDb, task_id: uuid.UUID) -> None:
    # For a client user an internal task is invisible, so commenting on it is 404.
    if task_repository.get_task(db.conn, task_id) is None:
        raise NotFound()


def list_comments(db: TenantDb, task_id: uuid.UUID) -> list[CommentRow]:
    _require_visible_task(db, task_id)
    return repository.list_comments(db.conn, task_id)


def create_comment(db: TenantDb, task_id: uuid.UUID, body: str, visibility: str) -> CommentRow:
    _require_visible_task(db, task_id)
    body = body.strip()
    if not body:
        raise Invalid("Comment can't be empty")
    if not db.is_staff:
        visibility = "client"  # clients can only write to the shared thread
    comment_id = repository.create_comment(
        db.conn, db.agency_id, task_id, db.user_id, body, visibility
    )
    comment = repository.get_comment(db.conn, comment_id)
    if comment is None:  # can't happen: the author can always read what they just wrote
        raise RuntimeError("new comment not readable by its author")
    return comment
