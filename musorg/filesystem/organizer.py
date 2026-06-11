import os
import shutil
import tempfile

from musorg.core.cover_art import load_album_cover_bytes
from musorg.filesystem.media import create_flac_file, normalize_picture_data, resolve_executable
from musorg.filesystem.naming import (
    SINGLES_ALBUM_TITLE,
    album_folder_title,
    default_output_format_settings,
    extract_year,
    filesystem_path_key,
    filesystem_safe_name,
    format_output_destination,
    is_standalone_single,
    normalize_lookup_text,
    normalize_filesystem_path,
    parse_sort_date_value,
    preferred_folder_artist,
    resolved_track_number,
    resolved_track_title,
    single_release_group_key,
    single_track_identity,
)
from musorg.filesystem.tagging import (
    clear_comment_tags,
    download_cover_bytes,
    normalize_metadata_preservation_settings,
    read_existing_flac_pictures,
    reset_cover_download_cache,
    restore_flac_pictures,
    write_cover_art,
    write_metadata_tags,
)
from musorg.utils.debug import error, log


_SESSION_DESTINATIONS = set()
_SESSION_CLEANED_ALBUMS = set()
_SESSION_WRITTEN_COVER_FILES = set()


def reset_session_state() -> None:
    _SESSION_DESTINATIONS.clear()
    _SESSION_CLEANED_ALBUMS.clear()
    _SESSION_WRITTEN_COVER_FILES.clear()
    reset_cover_download_cache()


def iter_audio_files(root_path: str) -> list[str]:
    files = []
    for root, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.lower().endswith(".flac"):
                files.append(os.path.join(root, filename))
    return files


def iter_files(root_path: str) -> list[str]:
    files = []
    for root, _, filenames in os.walk(root_path):
        for filename in filenames:
            files.append(os.path.join(root, filename))
    return files


def preview_tag_changes(track: dict) -> list[str]:
    changes = []

    for tag_name in ("artist", "album", "title", "albumartist", "genre", "releasetype"):
        value = track.get(tag_name)
        if value and value != "Unknown":
            changes.append(f"{tag_name}={value}")

    if track.get("tracknumber"):
        changes.append(f"tracknumber={track.get('tracknumber')}")
    if track.get("discnumber"):
        changes.append(f"discnumber={track.get('discnumber')}")
    if track.get("singleoriginaltracknumber"):
        changes.append(f"singleoriginaltracknumber={track.get('singleoriginaltracknumber')}")

    release_date_iso = str(track.get("release_date_iso") or "").strip()
    date = str(track.get("date") or "").strip()
    if len(release_date_iso) == 10 and release_date_iso[4] == "-" and release_date_iso[7] == "-":
        changes.append(f"DATE={release_date_iso[:4]}")
        changes.append(f"RELEASETIME={release_date_iso}")
    elif len(release_date_iso) == 4 and release_date_iso.isdigit():
        changes.append(f"DATE={release_date_iso}")
    elif len(date) == 4 and date.isdigit():
        changes.append(f"DATE={date}")
    elif len(date) == 10 and date[2] == "-" and date[5] == "-":
        changes.append(f"DATE={date[-4:]}")

    return changes


def preview_copy_track_to_destination(track: dict, destination: str) -> None:
    source_path = track["path"]
    if source_path.lower().endswith(".flac"):
        log("DryRun", f"Would copy {source_path} -> {destination}", "📝")
    else:
        log("DryRun", f"Would transcode {source_path} -> {destination}", "📝")

    tag_changes = preview_tag_changes(track)
    if tag_changes:
        log("DryRun", f"Would write tags on {destination}: {', '.join(tag_changes)}", "📝")

    if track.get("cover"):
        log("DryRun", f"Would download cover art for {destination} from {track['cover']}", "📝")


def copy_track_to_destination(track: dict, destination: str, dry_run: bool = False, journal=None) -> None:
    run_report = getattr(journal, "run_report", None) if journal else None
    metadata_settings = track.get("_metadata_preservation_settings")
    if dry_run:
        if journal:
            journal.record(
                "preview_copy",
                source=track["path"],
                destination=destination,
                tags=preview_tag_changes(track),
                cover=track.get("cover"),
            )
        preview_copy_track_to_destination(track, destination)
        return

    if run_report:
        with run_report.measure("audio_write"):
            create_flac_file(track["path"], destination)
        with run_report.measure("tag_write"):
            write_metadata_tags(
                destination,
                track,
                run_report=run_report,
                metadata_preservation_settings=metadata_settings,
            )
    else:
        create_flac_file(track["path"], destination)
        write_metadata_tags(destination, track, metadata_preservation_settings=metadata_settings)
    if journal:
        journal.record(
            "write_file",
            source=track["path"],
            destination=destination,
            tags=preview_tag_changes(track),
            cover=track.get("cover"),
        )


def unique_destination_path(destination: str, record: bool = True) -> str:
    destination = normalize_filesystem_path(destination)
    destination_key = filesystem_path_key(destination)
    if destination_key not in _SESSION_DESTINATIONS:
        if record:
            _SESSION_DESTINATIONS.add(destination_key)
        return destination

    stem, extension = os.path.splitext(destination)
    index = 2
    while True:
        candidate = f"{stem} ({index}){extension}"
        candidate = normalize_filesystem_path(candidate)
        candidate_key = filesystem_path_key(candidate)
        if candidate_key not in _SESSION_DESTINATIONS:
            if record:
                _SESSION_DESTINATIONS.add(candidate_key)
            return candidate
        index += 1


def _save_cover_sidecar_enabled(track: dict) -> bool:
    settings = normalize_metadata_preservation_settings(track.get("_metadata_preservation_settings"))
    return bool(settings["artwork"]["saveCoverJpg"])


def resolve_cover_sidecar_bytes(track: dict, run_report=None) -> bytes | None:
    cover_url = str(track.get("cover") or "").strip()
    if cover_url:
        download = download_cover_bytes(cover_url, run_report=run_report)
        if download is not None:
            return download[0]

    source_folder = os.path.dirname(str(track.get("path") or ""))
    if source_folder:
        return load_album_cover_bytes(source_folder)
    return None


def ensure_cover_sidecar(track: dict, album_root: str, dry_run: bool = False, journal=None) -> None:
    if not _save_cover_sidecar_enabled(track):
        return

    cover_path = normalize_filesystem_path(os.path.join(album_root, "Cover.jpg"))
    cover_key = filesystem_path_key(cover_path)
    if cover_key in _SESSION_WRITTEN_COVER_FILES:
        return

    run_report = getattr(journal, "run_report", None) if journal else None
    cover_bytes = resolve_cover_sidecar_bytes(track, run_report=run_report)
    if not cover_bytes:
        return

    _SESSION_WRITTEN_COVER_FILES.add(cover_key)
    if dry_run:
        if journal:
            journal.record("preview_write_file", path=cover_path)
        log("DryRun", f"Would save cover sidecar {cover_path}", "📝")
        return

    os.makedirs(album_root, exist_ok=True)
    with open(cover_path, "wb") as handle:
        handle.write(cover_bytes)
    if journal:
        journal.record("write_file", destination=cover_path, source=track.get("path"), kind="cover_sidecar")


def cleanup_existing_album_folders(
    root_output: str,
    target_folder: str,
    album: str,
    album_aliases: list[str] | None = None,
    dry_run: bool = False,
    journal=None,
) -> None:
    root_output = normalize_filesystem_path(root_output)
    target_folder = normalize_filesystem_path(target_folder)
    cleanup_key = (
        filesystem_path_key(root_output),
        filesystem_path_key(target_folder),
    )
    if cleanup_key in _SESSION_CLEANED_ALBUMS:
        return

    if not dry_run:
        _SESSION_CLEANED_ALBUMS.add(cleanup_key)

    if os.path.isdir(target_folder):
        if dry_run:
            if journal:
                journal.record("preview_remove_directory", path=target_folder)
            log("DryRun", f"Would remove existing album folder {target_folder}", "📝")
        else:
            backup_path = journal.move_to_backup(target_folder) if journal else None
            if not journal:
                shutil.rmtree(target_folder)
            if journal:
                journal.record("backup_directory", original_path=target_folder, backup_path=backup_path)

    safe_album_titles = {
        filesystem_safe_name(title)
        for title in [album, *(album_aliases or [])]
        if title
    }
    if not os.path.isdir(root_output):
        return

    for artist_name in os.listdir(root_output):
        artist_path = os.path.join(root_output, artist_name)
        if not os.path.isdir(artist_path):
            continue

        for folder_name in os.listdir(artist_path):
            candidate = os.path.join(artist_path, folder_name)
            if filesystem_path_key(candidate) == filesystem_path_key(target_folder) or not os.path.isdir(candidate):
                continue

            if album_folder_title(folder_name) in safe_album_titles:
                if dry_run:
                    if journal:
                        journal.record("preview_remove_directory", path=candidate)
                    log("DryRun", f"Would remove conflicting album folder {candidate}", "📝")
                else:
                    backup_path = journal.move_to_backup(candidate) if journal else None
                    if not journal:
                        shutil.rmtree(candidate)
                    if journal:
                        journal.record("backup_directory", original_path=candidate, backup_path=backup_path)


def replace_directory(source: str, destination: str, dry_run: bool = False, journal=None) -> None:
    source = normalize_filesystem_path(source)
    destination = normalize_filesystem_path(destination)
    if dry_run:
        if journal:
            journal.record("preview_replace_directory", source=source, destination=destination)
        log("DryRun", f"Would replace directory {destination} with staged content from {source}", "📝")
        return

    old_destination = None
    parent = os.path.dirname(destination)

    if os.path.isdir(destination):
        old_destination = tempfile.mkdtemp(prefix=".Singles.old.", dir=parent)
        os.rmdir(old_destination)
        os.rename(destination, old_destination)

    try:
        os.rename(source, destination)
    except Exception:
        if old_destination and not os.path.isdir(destination):
            os.rename(old_destination, destination)
        raise

    if old_destination:
        if journal:
            backup_path = journal.move_to_backup(old_destination)
            journal.record("backup_directory", original_path=destination, backup_path=backup_path)
        else:
            shutil.rmtree(old_destination)


def organize_single_tracks(tracks: list[dict], root_output: str, dry_run: bool = False, journal=None) -> tuple[int, int]:
    copied = 0
    affected_artists = {}

    for track in tracks:
        artist_folder = preferred_folder_artist(track.get("albumartist"), track.get("artist") or "Unknown")
        affected_artists.setdefault(artist_folder, []).append(track)

    for artist_folder, incoming_tracks in affected_artists.items():
        artist_root = normalize_filesystem_path(os.path.join(root_output, filesystem_safe_name(artist_folder)))
        singles_folder = normalize_filesystem_path(os.path.join(artist_root, SINGLES_ALBUM_TITLE))

        merged_tracks = {}
        for track in incoming_tracks:
            identity = single_track_identity(track)
            if identity in merged_tracks and journal and getattr(journal, "run_report", None):
                journal.run_report.record_duplicate(
                    "single_track_identity",
                    source_path=track.get("path"),
                    details={
                        "albumartist": track.get("albumartist"),
                        "album": track.get("album"),
                        "title": track.get("title"),
                    },
                )
            merged_tracks[identity] = track

        preserved_existing_files = []

        if os.path.isdir(singles_folder):
            from musorg.metadata.normalizer import normalize_track
            from musorg.metadata.parser import read_tags

            for existing_file in iter_files(singles_folder):
                if not existing_file.lower().endswith(".flac"):
                    preserved_existing_files.append(existing_file)
                    continue

                tags = read_tags(existing_file)
                if not tags:
                    preserved_existing_files.append(existing_file)
                    continue
                existing_track = normalize_track(tags)
                existing_track["releasetype"] = existing_track.get("releasetype") or "single"
                key = single_track_identity(existing_track)
                if key not in merged_tracks:
                    merged_tracks[key] = existing_track

        staged_singles_folder = os.path.join(artist_root, ".Singles.preview")
        if not dry_run:
            os.makedirs(artist_root, exist_ok=True)
            staged_singles_folder = tempfile.mkdtemp(prefix=".Singles.new.", dir=artist_root)

        ordered_tracks = sorted(
            merged_tracks.values(),
            key=lambda track: (
                parse_sort_date_value(track),
                normalize_lookup_text(track.get("album") or ""),
                int(track.get("discnumber") or 0),
                int(track.get("singleoriginaltracknumber") or resolved_track_number(track) or 0),
                normalize_lookup_text(resolved_track_title(track)),
            ),
        )

        for index, track in enumerate(ordered_tracks, start=1):
            title = resolved_track_title(track)
            destination = os.path.join(
                staged_singles_folder,
                filesystem_safe_name(f"{str(index).zfill(2)}. {title}.flac"),
            )
            track_for_single_folder = dict(track)
            track_for_single_folder["album"] = SINGLES_ALBUM_TITLE
            track_for_single_folder["tracknumber"] = index
            track_for_single_folder["singleoriginaltracknumber"] = (
                track.get("singleoriginaltracknumber")
                or resolved_track_number(track)
                or index
            )
            try:
                final_destination = os.path.join(
                    singles_folder,
                    filesystem_safe_name(f"{str(index).zfill(2)}. {title}.flac"),
                )
                copy_track_to_destination(
                    track_for_single_folder,
                    final_destination if dry_run else destination,
                    dry_run=dry_run,
                    journal=journal,
                )
                ensure_cover_sidecar(
                    track_for_single_folder,
                    singles_folder if dry_run else staged_singles_folder,
                    dry_run=dry_run,
                    journal=journal,
                )
                copied += 1
            except Exception:
                if not dry_run:
                    shutil.rmtree(staged_singles_folder, ignore_errors=True)
                raise

        for existing_file in preserved_existing_files:
            if os.path.basename(existing_file).lower() == "cover.jpg":
                continue
            relative_path = os.path.relpath(existing_file, singles_folder)
            destination = os.path.join(staged_singles_folder, relative_path)
            if dry_run:
                if journal:
                    journal.record("preview_preserve_file", source=existing_file, destination=singles_folder)
                log("DryRun", f"Would preserve extra file {existing_file} in {singles_folder}", "📝")
                continue
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if not os.path.exists(destination):
                try:
                    shutil.copy2(existing_file, destination)
                except Exception:
                    shutil.rmtree(staged_singles_folder, ignore_errors=True)
                    raise

        replace_directory(staged_singles_folder, singles_folder, dry_run=dry_run, journal=journal)

    return copied, len(tracks)


def cleanup_stale_single_track(track: dict, root_output: str, dry_run: bool = False, journal=None) -> None:
    artist_folder = preferred_folder_artist(track.get("albumartist"), track.get("artist") or "Unknown")
    singles_folder = os.path.join(
        root_output,
        filesystem_safe_name(artist_folder),
        SINGLES_ALBUM_TITLE,
    )
    singles_folder = normalize_filesystem_path(singles_folder)
    if not os.path.isdir(singles_folder):
        return

    from musorg.metadata.normalizer import normalize_track
    from musorg.metadata.parser import read_tags

    target_identity = single_track_identity(track)
    removed_any = False

    for existing_file in iter_files(singles_folder):
        if not existing_file.lower().endswith(".flac"):
            continue

        tags = read_tags(existing_file)
        if not tags:
            continue

        existing_track = normalize_track(tags)
        existing_track["releasetype"] = existing_track.get("releasetype") or "single"
        if single_track_identity(existing_track) != target_identity:
            continue

        if dry_run:
            if journal:
                journal.record("preview_remove_file", path=existing_file)
            log("DryRun", f"Would remove stale single file {existing_file}", "📝")
        else:
            if journal:
                backup_path = journal.move_to_backup(existing_file)
                journal.record("backup_file", original_path=existing_file, backup_path=backup_path)
            else:
                os.remove(existing_file)
        removed_any = True

    if not removed_any:
        return

    if dry_run:
        return

    for current_root, dirnames, filenames in os.walk(singles_folder, topdown=False):
        if dirnames or filenames:
            continue
        os.rmdir(current_root)


def organize_track(track, root_output, dry_run: bool = False, journal=None, cleanup_conflicts: bool = True):
    try:
        album = track["album"]
        output_settings = track.get("_output_format_settings") or default_output_format_settings()
        destination_info = format_output_destination(track, root_output, output_settings)
        folder = destination_info.album_root

        if cleanup_conflicts:
            cleanup_existing_album_folders(
                root_output,
                folder,
                album,
                album_aliases=[track.get("_source_album")],
                dry_run=dry_run,
                journal=journal,
            )
        if dry_run:
            if journal:
                journal.record("preview_ensure_directory", path=folder)
            log("DryRun", f"Would ensure album folder exists: {folder}", "📝")
        else:
            os.makedirs(folder, exist_ok=True)
            if journal:
                journal.record("ensure_directory", path=folder)

        requested_destination = destination_info.file_path
        if destination_info.disc_folder and not dry_run:
            os.makedirs(os.path.dirname(destination_info.file_path), exist_ok=True)
            if journal:
                journal.record("ensure_directory", path=os.path.dirname(destination_info.file_path))
        elif destination_info.disc_folder and dry_run:
            if journal:
                journal.record("preview_ensure_directory", path=os.path.dirname(destination_info.file_path))
            log("DryRun", f"Would ensure disc folder exists: {os.path.dirname(destination_info.file_path)}", "📝")

        destination = unique_destination_path(requested_destination)
        if destination != requested_destination and journal and getattr(journal, "run_report", None):
            journal.run_report.record_duplicate(
                "destination_collision",
                source_path=track.get("path"),
                requested_destination=requested_destination,
                resolved_destination=destination,
                details={
                    "albumartist": track.get("albumartist"),
                    "album": album,
                    "title": resolved_track_title(track),
                },
            )

        copy_track_to_destination(track, destination, dry_run=dry_run, journal=journal)
        ensure_cover_sidecar(track, destination_info.album_root, dry_run=dry_run, journal=journal)
        track["_organized_output_path"] = destination
        track["_organized_album_root"] = destination_info.album_root
        return destination

    except Exception as e:
        error("Organize", f"Could not copy {track['path']}: {e}")
        return None
