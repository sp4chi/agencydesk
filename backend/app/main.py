"""FastAPI entry point.

Run (from backend/):  uvicorn app.main:create_app --factory --env-file ../.env --reload

There is no module-level `app`: importing this module opens no pool, so
tests (and AGENTS.md's "no module-level connection" rule) stay clean.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.auth.db import create_auth_engine
from app.config import Settings
from app.db import create_api_engine
from app.routers import auth, me


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
    app.state.auth_engine = create_auth_engine(settings)  # login / select agency only

    app.include_router(auth.router)
    app.include_router(me.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        # No tenant context: proves the DB is reachable, reads no tenant data.
        with app.state.api_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app

