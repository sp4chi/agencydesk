"""Task files. Thin: parse, call the service, pick StaffFile or ClientFile.

Downloads are always sent as attachments with nosniff and a sandbox CSP,
so an uploaded HTML/SVG file can never run as a page on the API's origin.
"""
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.db import TenantDb, get_tenant_db
from app.repositories.files import FileRow
from app.schemas.files import ClientFile, FileReview, FileUpdate, StaffFile
from app.schemas.tasks import Visibility
from app.services import files as service

router = APIRouter(tags=["files"])


def _file(db: TenantDb, row: FileRow) -> StaffFile | ClientFile:
    if db.is_staff:
        return StaffFile(
            id=row.id, task_id=row.task_id, filename=row.filename, content_type=row.content_type,
            size_bytes=row.size_bytes, visibility=row.visibility,
            visible_to_client=(row.visibility == "client" and row.task_visibility == "client"),
            approval_status=row.approval_status, reviewed_by=row.reviewed_by,
            reviewed_by_name=row.reviewed_by_name, reviewed_at=row.reviewed_at,
            uploaded_by=row.uploaded_by, uploaded_by_name=row.uploaded_by_name,
            created_at=row.created_at,
        )
    return ClientFile(
        id=row.id, task_id=row.task_id, filename=row.filename, content_type=row.content_type,
        size_bytes=row.size_bytes, approval_status=row.approval_status,
        reviewed_at=row.reviewed_at, created_at=row.created_at,
    )


def _content_disposition(filename: str) -> str:
    # ASCII fallback plus RFC 5987 UTF-8 name; quotes/newlines can't break the header.
    ascii_name = filename.encode("ascii", "replace").decode().replace('"', "'")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/tasks/{task_id}/files", response_model=list[StaffFile] | list[ClientFile])
def list_files(
    task_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)
) -> list[StaffFile] | list[ClientFile]:
    return [_file(db, row) for row in service.list_files(db, task_id)]


@router.post("/tasks/{task_id}/files", response_model=StaffFile, status_code=status.HTTP_201_CREATED)
def upload_file(
    task_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    visibility: Visibility = Form("internal"),
    db: TenantDb = Depends(get_tenant_db),
) -> StaffFile | ClientFile:
    row = service.upload_file(
        db, request.app.state.storage, request.app.state.settings, task_id,
        file.filename, file.content_type, file.file, visibility,
    )
    return _file(db, row)


@router.get("/files/{file_id}", response_model=StaffFile | ClientFile)
def get_file(file_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> StaffFile | ClientFile:
    return _file(db, service.get_file(db, file_id))


@router.get("/files/{file_id}/download")
def download_file(
    file_id: uuid.UUID, request: Request, db: TenantDb = Depends(get_tenant_db)
) -> StreamingResponse:
    row, chunks = service.open_download(db, request.app.state.storage, file_id)
    return StreamingResponse(
        chunks,
        media_type=row.content_type,
        headers={
            "Content-Disposition": _content_disposition(row.filename),
            "Content-Length": str(row.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/files/{file_id}", response_model=StaffFile)
def update_file(
    file_id: uuid.UUID, body: FileUpdate, db: TenantDb = Depends(get_tenant_db)
) -> StaffFile | ClientFile:
    return _file(db, service.update_file(db, file_id, body.model_dump(exclude_unset=True)))


@router.post("/files/{file_id}/review", response_model=StaffFile | ClientFile)
def review_file(
    file_id: uuid.UUID, body: FileReview, db: TenantDb = Depends(get_tenant_db)
) -> StaffFile | ClientFile:
    return _file(db, service.review_file(db, file_id, body.decision))
