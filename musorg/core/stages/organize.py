from pathlib import Path

from musorg.api.services.workspace_runtime import runtime_album_payload, source_album_id_for_tracks
from musorg.core.events import publish_runtime_event
from musorg.core.metadata_intelligence import augment_metadata_intelligence
from musorg.core.release_intelligence import build_release_intelligence_registry
from musorg.core.stages.metadata_read import source_album_group_key
from musorg.filesystem.naming import default_output_format_settings, format_output_destination
from musorg.filesystem.organizer import (
    claim_album_root,
    cleanup_existing_album_folders,
    cleanup_stale_single_track,
    is_standalone_single,
    organize_single_tracks,
    organize_track,
    reset_session_state,
    single_release_group_key,
)
from musorg.filesystem.rollback import OperationJournal
from musorg.utils.debug import log, success

def organize_stage(context):
    input_root = Path(context.root_path).expanduser()
    configured_output = getattr(context, "output_root", None)
    output = configured_output or str(input_root.parent / f"{input_root.name}_organized")
    dry_run = getattr(context, "dry_run", False)
    reset_session_state()
    journal = OperationJournal(output, dry_run=dry_run, run_report=getattr(context, "run_report", None))
    context.operation_journal = journal
    duplicate_handling = getattr(context, "duplicate_handling", "keep_everything")
    filename_compatibility = getattr(context, "filename_compatibility", "preserve_original")
    metadata_intelligence_by_path = _metadata_intelligence_by_source_folder(context.tracks)
    release_registry = build_release_intelligence_registry(
        str(input_root),
        metadata_intelligence_by_path=metadata_intelligence_by_path,
    )
    copied = 0
    single_tracks = []
    single_group_counts = {}
    album_groups = list(getattr(context, "albums", {}).values())
    if not album_groups:
        album_groups = [[track] for track in context.tracks]
    total_albums = len(album_groups)

    for track in context.tracks:
        key = single_release_group_key(track)
        single_group_counts[key] = single_group_counts.get(key, 0) + 1

    for index, album_tracks in enumerate(album_groups, start=1):
        sample_track = album_tracks[0]
        max_disc = max((int(track.get("discnumber") or 0) for track in album_tracks), default=0)
        for track in album_tracks:
            track["_album_max_discnumber"] = max_disc
            track["_output_format_settings"] = getattr(context, "output_format_settings", None) or {}
            track["_metadata_preservation_settings"] = getattr(context, "metadata_preservation_settings", None) or {}
            track["_filename_compatibility"] = filename_compatibility
        album_artist = sample_track.get("albumartist") or sample_track.get("artist") or "Unknown"
        album_title = sample_track.get("album") or "Unknown"
        album_root_output = _album_output_root(
            output,
            sample_track,
            release_registry=release_registry,
            duplicate_handling=duplicate_handling,
        )
        output_settings = sample_track.get("_output_format_settings") or default_output_format_settings()
        album_destination = format_output_destination(sample_track, album_root_output, output_settings)
        # Keep two distinct albums that resolve to the same folder apart: claim
        # the folder for this group; if a different group already owns it, pin a
        # disambiguated folder on every track so they don't merge.
        resolved_album_root = claim_album_root(album_destination.album_root, source_album_group_key(sample_track))
        if resolved_album_root != album_destination.album_root:
            for track in album_tracks:
                track["_album_root_override"] = resolved_album_root
            album_destination = format_output_destination(sample_track, album_root_output, output_settings)
        run_report = getattr(context, "run_report", None)
        if run_report:
            with run_report.measure("album_conflict_cleanup"):
                cleanup_existing_album_folders(
                    album_root_output,
                    album_destination.album_root,
                    album_title,
                    album_aliases=[sample_track.get("_source_album")],
                    dry_run=dry_run,
                    journal=journal,
                )
        else:
            cleanup_existing_album_folders(
                album_root_output,
                album_destination.album_root,
                album_title,
                album_aliases=[sample_track.get("_source_album")],
                dry_run=dry_run,
                journal=journal,
            )
        log("Organize", f"Organizing album {index}/{total_albums}: {album_artist} — {album_title}", "📦")
        album_id = source_album_id_for_tracks(album_tracks)
        if album_id:
            publish_runtime_event(context, {
                "severity": "info",
                "source": "Organize",
                "type": "album_processing_started",
                "stage": "organize_stage",
                "albumId": album_id,
                "message": f"Saving cleaned tracks for {album_artist} — {album_title}",
                "payload": {
                    "progress": "writing",
                },
            })

        album_destinations = []
        album_root = None
        for track in album_tracks:
            group_size = single_group_counts.get(single_release_group_key(track), 0)
            if is_standalone_single(track, group_size):
                single_tracks.append(track)
                continue

            cleanup_stale_single_track(track, album_root_output, dry_run=dry_run, journal=journal)
            destination = organize_track(
                track,
                album_root_output,
                dry_run=dry_run,
                journal=journal,
                cleanup_conflicts=False,
            )
            if destination:
                copied += 1
                album_destinations.append(destination)
                album_root = track.get("_organized_album_root") or album_root

        if album_id and album_destinations:
            group_key = source_album_group_key(album_tracks[0])
            final_intelligence = augment_metadata_intelligence(
                album_tracks[0].get("_metadata_intelligence"),
                output_path=album_root or album_destinations[0],
                complete=True,
            )
            for track in album_tracks:
                track["_metadata_intelligence"] = final_intelligence
            payload = runtime_album_payload(
                album_tracks,
                processing_state="writing",
                output_path=album_root or album_destinations[0],
                complete=False,
            )
            if payload:
                publish_runtime_event(context, {
                    "severity": "success",
                    "source": "Tags",
                    "type": "tags_written",
                    "stage": "organize_stage",
                    "albumId": album_id,
                    "message": f"Saved cleaned tags for {album_artist} — {album_title}",
                    "payload": payload,
                })
                publish_runtime_event(context, {
                    "severity": "success",
                    "source": "Organize",
                    "type": "organize_completed",
                    "stage": "organize_stage",
                    "albumId": album_id,
                    "message": f"Finished organizing {album_artist} — {album_title}",
                    "payload": payload,
                })
                final_payload = runtime_album_payload(
                    album_tracks,
                    processing_state="completed",
                    output_path=album_root or album_destinations[0],
                    complete=True,
                )
                if run_report is not None:
                    run_report.update_changed_album(
                        group_key,
                        output_dir=str(album_root or Path(album_destinations[0]).parent),
                        metadata_intelligence=final_intelligence,
                    )
                publish_runtime_event(context, {
                    "severity": "success",
                    "source": "Organize",
                    "type": "album_output_ready",
                    "stage": "organize_stage",
                    "albumId": album_id,
                    "message": f"Output ready for {album_artist} — {album_title}",
                    "payload": final_payload,
                })
                publish_runtime_event(context, {
                    "severity": "success",
                    "source": "Organize",
                    "type": "album_processed",
                    "stage": "organize_stage",
                    "albumId": album_id,
                    "message": f"Album completed: {album_artist} — {album_title}",
                    "payload": final_payload,
                })

    single_copied, _single_total = organize_single_tracks(single_tracks, output, dry_run=dry_run, journal=journal)
    copied += single_copied
    journal.finalize()

    action = "Would save" if dry_run else "Saved"
    success("Organize", f"{action} {copied} cleaned tracks to output library")

    return context


def _metadata_intelligence_by_source_folder(tracks: list[dict]) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for track in tracks:
        folder_path = str(Path(str(track.get("path") or "")).expanduser().resolve().parent)
        intelligence = track.get("_metadata_intelligence")
        if folder_path and isinstance(intelligence, dict):
            payloads[folder_path] = intelligence
    return payloads


def _album_output_root(
    output_root: str,
    track: dict,
    *,
    release_registry,
    duplicate_handling: str,
) -> str:
    if duplicate_handling != "move_duplicates_to_archive":
        return output_root
    source_folder = str(Path(str(track.get("path") or "")).expanduser().resolve().parent)
    summary = release_registry.summaries_by_path.get(source_folder) or {}
    confidence = int(summary.get("duplicateConfidence") or 0)
    quality_rank = int(summary.get("qualityRank") or 0)
    relationship_status = str(summary.get("relationshipStatus") or "standalone")
    best_version = bool(summary.get("bestVersion"))
    if relationship_status not in {"exact_duplicate", "better_version_available"}:
        return output_root
    if best_version or confidence < 85 or quality_rank <= 1:
        return output_root
    return str(Path(output_root) / "Archive")
