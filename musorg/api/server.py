from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from musorg.api.routes.albums import router as albums_router
from musorg.api.routes.batch_edit import router as batch_edit_router
from musorg.api.routes.cleanup import router as cleanup_router
from musorg.api.routes.health import router as health_router
from musorg.api.routes.logs import router as logs_router
from musorg.api.routes.settings import router as settings_router


@dataclass(slots=True)
class ApiRuntimeConfig:
    mode: str = "standalone"
    allow_origins: list[str] = field(default_factory=lambda: [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ])
    frontend_dist: Path | None = None


def create_app(runtime_config: ApiRuntimeConfig | None = None) -> FastAPI:
    config = runtime_config or ApiRuntimeConfig()

    app = FastAPI(title="Musorg Local API", version="0.2.0")
    app.state.runtime_config = config

    if config.allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(albums_router)
    app.include_router(batch_edit_router)
    app.include_router(cleanup_router)
    app.include_router(logs_router)
    app.include_router(settings_router)

    if config.frontend_dist is not None:
        _mount_frontend(app, config.frontend_dist)

    return app


def _mount_frontend(app: FastAPI, frontend_dist: Path) -> None:
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_fallback(full_path: str) -> FileResponse:
        candidate = frontend_dist / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")


app = create_app()
