from __future__ import annotations

from fastapi import APIRouter

from musorg.api.schemas.music import (
    ClearCacheResponse,
    LibraryPickerResponse,
    LibrarySettingsResponse,
    UpdateLibrarySettingsRequest,
)
from musorg.api.services.cache_control import clear_pipeline_cache
from musorg.api.services.settings import (
    get_library_settings_state,
    pick_library_root,
    pick_output_root,
    save_library_settings,
)


router = APIRouter(tags=["settings"])


@router.get("/settings/library", response_model=LibrarySettingsResponse)
def library_settings() -> LibrarySettingsResponse:
    return get_library_settings_state()


@router.post("/settings/library", response_model=LibrarySettingsResponse)
def update_library_settings(payload: UpdateLibrarySettingsRequest) -> LibrarySettingsResponse:
    return save_library_settings(
        payload.libraryRoot,
        payload.outputRoot,
        payload.developerMode,
        payload.language,
        payload.themeMode,
        payload.accentColor,
        payload.duplicateHandling,
        payload.filenameCompatibility,
        payload.outputFormat.model_dump(),
        payload.metadataPreservation.model_dump(),
        payload.onboardingCompleted,
        payload.onboardingDismissed,
    )


@router.post("/settings/library/pick", response_model=LibraryPickerResponse)
def pick_library_settings() -> LibraryPickerResponse:
    return pick_library_root()


@router.post("/settings/output/pick", response_model=LibraryPickerResponse)
def pick_output_settings() -> LibraryPickerResponse:
    return pick_output_root()


@router.post("/settings/cache/clear", response_model=ClearCacheResponse)
def clear_settings_cache() -> ClearCacheResponse:
    return clear_pipeline_cache()
