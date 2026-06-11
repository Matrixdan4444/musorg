from __future__ import annotations

import base64
import shutil
from pathlib import Path

from fastapi import HTTPException

from musorg.api.schemas.music import AlbumMetadataOverrideSchema, CleanLibraryRequest, CleanLibraryResponse
from musorg.api.services.cleanup_runs import finish_cleanup_run, get_active_cleanup_run, try_start_cleanup_run
from musorg.api.services.log_stream import log_broadcaster
from musorg.api.services.run_outputs import register_run_output
from musorg.api.services.settings import get_library_settings_state
from musorg.core.context import Context
from musorg.core.pipeline import Pipeline
from musorg.filesystem.naming import filesystem_path_key


def clean_library(request: CleanLibraryRequest | None = None) -> CleanLibraryResponse:
    settings_state = get_library_settings_state()
    if not settings_state.isAvailable:
        detail = settings_state.error or "Library is not available."
        raise HTTPException(status_code=400, detail=detail)

    library_root = settings_state.libraryRoot
    active_run = get_active_cleanup_run()
    if active_run is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Cleanup run {active_run.run_id} is already in progress.",
        )

    started_run = try_start_cleanup_run(library_root)
    if started_run is None:
        raise HTTPException(status_code=409, detail="Cleanup run is already in progress.")

    log_broadcaster.set_active_run(started_run.run_id)
    output_root = settings_state.outputRoot or None
    staged_album_overrides = _decode_album_overrides(request.overrides if request else [])

    try:
        context = Context(
            library_root,
            dry_run=False,
            output_root=output_root,
            developer_mode=settings_state.developerMode,
            run_id=started_run.run_id,
            log_broadcaster=log_broadcaster,
            staged_album_overrides=staged_album_overrides,
            output_format_settings=settings_state.outputFormat.model_dump(),
            metadata_preservation_settings=settings_state.metadataPreservation.model_dump(),
            duplicate_handling=settings_state.duplicateHandling,
            filename_compatibility=settings_state.filenameCompatibility,
        )
        result = Pipeline().run(context)

        if result.output_path:
            _copy_summary_to_output(result.stats.get("summary_path"), result.output_path)
            register_run_output(started_run.run_id, result.output_path)
            log_broadcaster.publish({
                "severity": "success",
                "source": "Workspace",
                "type": "output_ready",
                "stage": "pipeline",
                "message": f"Processed library is ready in {result.output_path}",
                "payload": {
                    "outputRoot": result.output_path,
                    "albumsProcessed": result.albums_processed,
                    "tracksProcessed": result.tracks_processed,
                },
                "runId": started_run.run_id,
                "_developerMode": settings_state.developerMode,
            })

        return CleanLibraryResponse(
            runId=started_run.run_id,
            status="completed",
            libraryRoot=library_root,
            outputPath=result.output_path,
            albumsProcessed=result.albums_processed,
            tracksProcessed=result.tracks_processed,
            summaryPath=_clean_text(result.stats.get("summary_path")),
        )
    finally:
        finish_cleanup_run(started_run.run_id)
        if log_broadcaster.active_run_id() == started_run.run_id:
            log_broadcaster.set_active_run(None)


def _copy_summary_to_output(summary_path: object, output_root: str) -> None:
    source_text = _clean_text(summary_path)
    if not source_text:
        return

    source = Path(source_text).expanduser()
    if not source.exists() or not source.is_file():
        return

    target_dir = Path(output_root).expanduser() / ".musorg" / "runs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.resolve() == source.resolve():
        return
    shutil.copy2(source, target)


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _decode_album_id(album_id: str) -> str:
    padding = "=" * (-len(album_id) % 4)
    return base64.urlsafe_b64decode(f"{album_id}{padding}".encode("ascii")).decode("utf-8")


def _decode_album_overrides(overrides: list[AlbumMetadataOverrideSchema]) -> dict[str, dict]:
    decoded: dict[str, dict] = {}
    for override in overrides:
        try:
            folder_path = Path(_decode_album_id(override.albumId)).expanduser().resolve()
        except Exception:
            continue
        override_dict = override.model_dump()
        override_dict.pop("albumId", None)
        cleaned = {}
        for key, value in override_dict.items():
            if value is None:
                continue
            if isinstance(value, bool):
                cleaned[key] = value
                continue
            if isinstance(value, (int, float)):
                cleaned[key] = value
                continue
            if str(value).strip():
                cleaned[key] = value
        if cleaned:
            decoded[filesystem_path_key(str(folder_path))] = cleaned
    return decoded
