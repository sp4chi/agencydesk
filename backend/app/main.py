"""FastAPI entry point.

Run (from backend/):  uvicorn app.main:create_app --factory --env-file ../.env --reload

There is no module-level `app`: importing this module opens no pool, so
tests (and AGENTS.md's "no module-level connection" rule) stay clean.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.auth.db import create_auth_engine
from app.config import Settings
from app.db import create_api_engine
from app.errors import ServiceError
from app.routers import (
    auth,
    clients,
    comments,
    dashboard,
    files,
    invites,
    me,
    projects,
    tasks,
    time,
)
from app.services.storage import LocalDiskStorage

INSUFFICIENT_PRIVILEGE = "42501"  # includes "new row violates row-level security policy"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        app.state.api_engine.dispose()
        app.state.auth_engine.dispose()

    app = FastAPI(title="AgencyDesk", lifespan=lifespan)
    # Engines live on the app, not at module level, so tests can build an
    # app against their own database.
    app.state.settings = settings
    app.state.api_engine = create_api_engine(settings)    # every request (RLS applies)
    app.state.auth_engine = create_auth_engine(settings)  # login / select agency / accept invite
    # Uploaded files. Not mounted as static files: bytes only leave through
    # GET /files/{id}/download, after an RLS-checked lookup.
    app.state.storage = LocalDiskStorage(settings.upload_dir)

    @app.exception_handler(ServiceError)
    def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        # The one place service errors become HTTP status codes (see app/errors.py).
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code, headers=headers)

    @app.exception_handler(DBAPIError)
    def database_error(_: Request, exc: DBAPIError) -> JSONResponse:
        # RLS refused a write that the service layer let through: the database
        # is the backstop, so answer 403 rather than 500. Never echo the
        # database message (it can name tables, policies or values).
        if getattr(exc.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
            return JSONResponse({"detail": "Not allowed"}, status_code=403)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    app.include_router(auth.router)
    app.include_router(auth.invite_accept_router)
    app.include_router(invites.router)
    app.include_router(me.router)
    app.include_router(clients.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(comments.router)
    app.include_router(files.router)
    app.include_router(time.router)
    app.include_router(dashboard.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        # No tenant context: proves the DB is reachable, reads no tenant data.
        with app.state.api_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app

