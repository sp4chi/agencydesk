"""SQL for comments. Runs under get_tenant_db.

No visibility filter here: the comments read policy shows a client user
only comments where the comment AND its task are client-visible
(app.can_see_task + visibility = 'client').
"""
import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class CommentRow:
    id: uuid.UUID
    task_id: uuid.UUID
    body: str
    visibility: str
    task_visibility: str
    author_user_id: uuid.UUID
    author_name: str
    created_at: dt.datetime


_SELECT = """
    SELECT c.id, c.task_id, c.body, c.visibility, t.visibility AS task_visibility,
           c.author_user_id, u.name AS author_name, c.created_at
    FROM comments c
    JOIN tasks t ON t.agency_id = c.agency_id AND t.id = c.task_id
    JOIN users u ON u.id = c.author_user_id
"""


def list_comments(conn: Connection, task_id: uuid.UUID) -> list[CommentRow]:
    rows = conn.execute(
        text(_SELECT + " WHERE c.task_id = :task_id ORDER BY c.created_at, c.id"),
        {"task_id": task_id},
    )
    return [CommentRow(**r._asdict()) for r in rows]


def get_comment(conn: Connection, comment_id: uuid.UUID) -> CommentRow | None:
    row = conn.execute(text(_SELECT + " WHERE c.id = :id"), {"id": comment_id}).one_or_none()
    return CommentRow(**row._asdict()) if row else None


def create_comment(
    conn: Connection, agency_id: uuid.UUID, task_id: uuid.UUID, author_user_id: uuid.UUID,
    body: str, visibility: str,
) -> uuid.UUID:
    return conn.execute(
        text(
            """INSERT INTO comments (agency_id, task_id, author_user_id, body, visibility)
               VALUES (:agency_id, :task_id, :author_user_id, :body, :visibility)
               RETURNING id"""
        ),
        {
            "agency_id": agency_id, "task_id": task_id, "author_user_id": author_user_id,
            "body": body, "visibility": visibility,
        },
    ).scalar_one()
