from __future__ import annotations

from fastapi import APIRouter

from musorg.api.schemas.music import CleanLibraryRequest, CleanLibraryResponse
from musorg.api.services.cleanup import clean_library


router = APIRouter(tags=["cleanup"])


@router.post("/clean", response_model=CleanLibraryResponse)
def clean(request: CleanLibraryRequest | None = None) -> CleanLibraryResponse:
    return clean_library(request)
