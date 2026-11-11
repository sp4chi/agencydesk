"""File rules.

  * read / download: anyone who can see the task; client users only files
    where the file AND its task are client-visible (RLS). Download reads
    the row under RLS first, and only then opens the stored bytes.
  * upload, rename, change visibility: staff on the project.
  * review (approve / request changes): client users only, on files they
    can see. The DB trigger also stops clients changing any other column.
"""
import re
import uuid
from collections.abc import Iterator
from typing import Any, BinaryIO

from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db import TenantDb
from app.errors import (
    CHECK_VIOLATION,
    Conflict,
    Forbidden,
    Invalid,
    NotFound,
    PayloadTooLarge,
    sqlstate,
)
from app.repositories import files as repository
from app.repositories import tasks as task_repository
from app.repositories.files import FileRow
from app.services.storage import EmptyFile, FileStorage, FileTooLarge, StoredFileMissing

MAX_FILENAME_LENGTH = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def clean_filename(raw: str | None) -> str:
    """Display name only (storage keys never use it): last path segment,
    no control characters, at most 255 characters."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL_CHARS.sub("", name).strip()
    if name in ("", ".", ".."):
        name = "file"
    return name[:MAX_FILENAME_LENGTH]


def _require_staff(db: TenantDb, action: str) -> None:
    if not db.is_staff:
        raise Forbidden(f"Client users can't {action}")


def _require_visible_task(db: TenantDb, task_id: uuid.UUID) -> None:
    if task_repository.get_task(db.conn, task_id) is None:
        raise NotFound()


def _get_visible_file(db: TenantDb, file_id: uuid.UUID) -> FileRow:
    file = repository.get_file(db.conn, file_id)
    if file is None:  # missing, other agency, not on project, or internal: same answer
        raise NotFound()
    return file


def list_files(db: TenantDb, task_id: uuid.UUID) -> list[FileRow]:
    _require_visible_task(db, task_id)
    return repository.list_files(db.conn, task_id)


def get_file(db: TenantDb, file_id: uuid.UUID) -> FileRow:
    return _get_visible_file(db, file_id)


def upload_file(
    db: TenantDb,
    storage: FileStorage,
    settings: Settings,
    task_id: uuid.UUID,
    filename: str | None,
    content_type: str | None,
    stream: BinaryIO,
    visibility: str,
) -> FileRow:
    _require_staff(db, "upload files")
    _require_visible_task(db, task_id)

    # Our key, not the user's filename: nothing they send can pick the path.
    key = f"{db.agency_id}/{uuid.uuid4().hex}"
    try:
        size = storage.save(key, stream, settings.max_upload_bytes)
    except EmptyFile:
        raise Invalid("The file is empty") from None
    except FileTooLarge:
        raise PayloadTooLarge(
            f"Files can be at most {settings.max_upload_bytes // (1024 * 1024)} MB"
        ) from None

    try:
        file_id = repository.create_file(db.conn, {
            "agency_id": db.agency_id, "task_id": task_id, "uploaded_by": db.user_id,
            "storage_key": key, "filename": clean_filename(filename),
            "content_type": (content_type or "application/octet-stream")[:200],
            "size_bytes": size, "visibility": visibility,
        })
    except Exception:
        storage.delete(key)  # don't leave bytes behind without a row pointing at them
        raise
    return _get_visible_file(db, file_id)


def open_download(
    db: TenantDb, storage: FileStorage, file_id: uuid.UUID
) -> tuple[FileRow, Iterator[bytes]]:
    file = _get_visible_file(db, file_id)  # RLS decides first; only then touch storage
    try:
        return file, storage.open_chunks(file.storage_key)
    except StoredFileMissing:
        raise NotFound("File content is missing") from None


def update_file(db: TenantDb, file_id: uuid.UUID, changes: dict[str, Any]) -> FileRow:
    _require_staff(db, "rename files or change who can see them")
    file = _get_visible_file(db, file_id)
    for field in ("filename", "visibility"):
        if field in changes and changes[field] is None:
            raise Invalid(f"{field} can't be null")
    if "filename" in changes:
        changes = {**changes, "filename": clean_filename(changes["filename"])}
    if changes.get("visibility") == "internal" and file.approval_status != "pending":
        # The DB CHECK forbids it too; say why in plain words.
        raise Conflict("The client has already reviewed this file, so it can't be made internal")
    if changes:
        try:
            updated = repository.update_file(db.conn, file_id, changes)
        except IntegrityError as exc:
            if sqlstate(exc) == CHECK_VIOLATION:
                raise Conflict("The client has already reviewed this file, so it can't be made internal") from None
            raise
        if not updated:
            raise NotFound()
    return _get_visible_file(db, file_id)


def review_file(db: TenantDb, file_id: uuid.UUID, decision: str) -> FileRow:
    if db.role != "client_user":
        raise Forbidden("Only the client can approve a file or request changes")
    _get_visible_file(db, file_id)  # internal file, or file on an internal task: 404
    if not repository.record_review(db.conn, file_id, decision, db.user_id):
        raise NotFound()
    return _get_visible_file(db, file_id)
