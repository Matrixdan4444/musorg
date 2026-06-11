from __future__ import annotations

from fastapi import APIRouter

from musorg.api.schemas.music import HealthResponse
from musorg.api.services.library import get_active_library_root


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", library_path=get_active_library_root())
