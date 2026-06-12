from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from musorg.api.schemas.music import (
    AlbumActionsResponseSchema,
    AlbumIssueSchema,
    AlbumsResponse,
    BatchEditAlbumDetailResponseSchema,
    BatchEditAlbumDraftSchema,
    BatchEditApplyReleaseRequestSchema,
    BatchEditApplyReleaseResponseSchema,
    BatchEditArtworkDraftSchema,
    BatchEditArtworkOptionSchema,
    BatchEditBulkUpdateRequestSchema,
    BatchEditBulkUpdateResponseSchema,
    BatchEditCandidateSchema,
    BatchEditEditorStateSchema,
    BatchEditFindArtworkRequestSchema,
    BatchEditFindArtworkResponseSchema,
    BatchEditFindReleaseRequestSchema,
    BatchEditFindReleaseResponseSchema,
    BatchEditSaveRequestSchema,
    BatchEditSaveResponseSchema,
    BatchEditTrackSchema,
    MetadataDiffFieldSchema,
)
from musorg.api.services.library import (
    get_album_actions_payload,
    get_album_detail_payload_for_root,
    get_related_releases_payload,
    list_albums_for_root,
    resolve_album_runtime_state,
)
from musorg.api.services.settings import get_library_settings_state
from musorg.core.metadata_intelligence import build_metadata_intelligence, metadata_snapshot
from musorg.filesystem.scanner import SUPPORTED_FORMATS
from musorg.filesystem.tagging import remove_cover_art, write_cover_art_bytes, write_metadata_tags
from musorg.metadata.parser import read_tags
from musorg.services.deezer import format_tracks as format_deezer_tracks
from musorg.services.deezer import genre_value as deezer_genre_value
from musorg.services.deezer import get_album as deezer_get_album
from musorg.services.deezer import search_album_candidates
from musorg.services.musicbrainz import artist_credit_phrase
from musorg.services.musicbrainz import cover_art_url
from musorg.services.musicbrainz import date_year
from musorg.services.musicbrainz import format_release_tracks
from musorg.services.musicbrainz import get_release_details
from musorg.services.musicbrainz import search_release_group
from musorg.utils.artist_text import first_known_artist, known_artist


def list_batch_edit_albums():
    settings_state = get_library_settings_state()
    if not settings_state.isAvailable:
        return AlbumsResponse(libraryPath=settings_state.libraryRoot, albums=[])
    return list_albums_for_root(
        settings_state.libraryRoot,
        include_metadata_intelligence=True,
        # Resolve runtime output so already-tidied albums show as "completed"
        # here too (consistent with Import); editing still targets the source
        # files because the album id encodes the source folder.
        resolve_runtime_output=True,
    )


def get_batch_edit_album_detail(album_id: str) -> BatchEditAlbumDetailResponseSchema:
    settings_state = get_library_settings_state()
    detail = get_album_detail_payload_for_root(
        album_id,
        settings_state.libraryRoot or None,
        include_metadata_intelligence=True,
        resolve_runtime_output=True,
    )
    related = get_related_releases_payload(album_id)
    actions = get_album_actions_payload(album_id)
    editor = _build_editor_state(album_id)
    return BatchEditAlbumDetailResponseSchema(
        album=detail.album,
        relatedReleases=related,
        actions=actions,
        editor=editor,
    )


def save_batch_edit_album(album_id: str, request: BatchEditSaveRequestSchema) -> BatchEditSaveResponseSchema:
    _apply_album_save(album_id, request.album, request.tracks, request.artwork)
    return BatchEditSaveResponseSchema(saved=True, albumId=album_id)


def save_batch_edit_tracks(album_id: str, tracks: list[BatchEditTrackSchema]) -> BatchEditSaveResponseSchema:
    editor = _build_editor_state(album_id)
    _apply_album_save(
        album_id,
        editor.album,
        tracks,
        BatchEditArtworkDraftSchema(mode="keep"),
    )
    return BatchEditSaveResponseSchema(saved=True, albumId=album_id)


def save_batch_edit_artwork(album_id: str, artwork: BatchEditArtworkDraftSchema) -> BatchEditSaveResponseSchema:
    editor = _build_editor_state(album_id)
    _apply_album_save(
        album_id,
        editor.album,
        editor.tracks,
        artwork,
    )
    return BatchEditSaveResponseSchema(saved=True, albumId=album_id)


def find_batch_edit_release(album_id: str, request: BatchEditFindReleaseRequestSchema) -> BatchEditFindReleaseResponseSchema:
    editor = _build_editor_state(album_id)
    query_artist = first_known_artist(request.artist, editor.album.albumArtist, editor.album.releaseArtist, fallback="") or ""
    query_album = (request.album or editor.album.albumTitle or "").strip()
    current_track_count = len(editor.tracks)

    candidates: list[BatchEditCandidateSchema] = []
    seen: set[tuple[str, str]] = set()

    for item in search_album_candidates(query_artist, query_album)[:8]:
        album_id_value = item.get("id")
        if album_id_value is None:
            continue
        key = ("deezer", str(album_id_value))
        if key in seen:
            continue
        seen.add(key)
        cover_url, cover_width, cover_height = _deezer_cover_metadata(item)
        candidates.append(
            BatchEditCandidateSchema(
                id=f"deezer:{album_id_value}",
                provider="deezer",
                providerReleaseId=str(album_id_value),
                title=str(item.get("title") or query_album or "Unknown album"),
                artist=first_known_artist(((item.get("artist") or {}).get("name")), query_artist, fallback="Unknown artist") or "Unknown artist",
                year="Unknown",
                trackCount=int(item.get("nb_tracks") or 0),
                coverUrl=cover_url,
                releaseType=str(item.get("record_type") or ""),
                artworkWidth=cover_width,
                artworkHeight=cover_height,
            )
        )

    mb_match = search_release_group(query_artist, query_album, expected_track_count=current_track_count)
    if mb_match:
        release_group = mb_match[0]
        group_id = str(release_group.get("id") or "")
        if group_id:
            releases = release_group.get("release-list") or []
            if not releases:
                release_details = get_release_details(group_id)
                if release_details:
                    releases = [release_details]
            for release in releases[:8]:
                release_id = str(release.get("id") or "")
                if not release_id:
                    continue
                key = ("musicbrainz", release_id)
                if key in seen:
                    continue
                seen.add(key)
                details = get_release_details(release_id) or release
                mb_cover_url = cover_art_url(details) or ""
                candidates.append(
                    BatchEditCandidateSchema(
                        id=f"musicbrainz:{release_id}",
                        provider="musicbrainz",
                        providerReleaseId=release_id,
                        title=str(release.get("title") or release_group.get("title") or query_album or "Unknown album"),
                        artist=first_known_artist(artist_credit_phrase(release_group), query_artist, fallback="Unknown artist") or "Unknown artist",
                        year=str(date_year(release.get("date")) or "Unknown"),
                        trackCount=_musicbrainz_track_count(release),
                        coverUrl=mb_cover_url,
                        releaseType=str(release_group.get("primary-type") or "").lower(),
                        artworkWidth=500 if mb_cover_url else None,
                        artworkHeight=500 if mb_cover_url else None,
                    )
                )

    return BatchEditFindReleaseResponseSchema(
        albumId=album_id,
        queryArtist=query_artist,
        queryAlbum=query_album,
        candidates=candidates,
    )


def find_batch_edit_artwork(album_id: str, request: BatchEditFindArtworkRequestSchema) -> BatchEditFindArtworkResponseSchema:
    editor = _build_editor_state(album_id)
    query_artist = first_known_artist(request.artist, editor.album.albumArtist, editor.album.releaseArtist, fallback="") or ""
    query_album = (request.album or editor.album.albumTitle or "").strip()
    current_track_count = len(editor.tracks)
    options: list[BatchEditArtworkOptionSchema] = []

    for item in search_album_candidates(query_artist, query_album):
        album_id_value = item.get("id")
        if album_id_value is None:
            continue
        cover_url, cover_width, cover_height = _deezer_cover_metadata(item)
        if not cover_url:
            continue
        options.append(
            BatchEditArtworkOptionSchema(
                id=f"deezer:{album_id_value}",
                provider="deezer",
                coverUrl=cover_url,
                width=cover_width,
                height=cover_height,
                releaseTitle=str(item.get("title") or query_album or ""),
            )
        )
        break

    mb_match = search_release_group(query_artist, query_album, expected_track_count=current_track_count)
    if mb_match:
        release_group = mb_match[0]
        releases = release_group.get("release-list") or []
        for release in releases[:8]:
            release_id = str(release.get("id") or "")
            if not release_id:
                continue
            details = get_release_details(release_id)
            cover_url = cover_art_url(details)
            if not cover_url:
                continue
            options.append(
                BatchEditArtworkOptionSchema(
                    id=f"musicbrainz:{release_id}",
                    provider="musicbrainz",
                    coverUrl=cover_url,
                    width=500,
                    height=500,
                    releaseTitle=str(release.get("title") or release_group.get("title") or query_album or ""),
                )
            )
            break

    return BatchEditFindArtworkResponseSchema(
        albumId=album_id,
        queryArtist=query_artist,
        queryAlbum=query_album,
        options=options,
    )


def apply_batch_edit_release(album_id: str, request: BatchEditApplyReleaseRequestSchema) -> BatchEditApplyReleaseResponseSchema:
    editor = _build_editor_state(album_id)
    album_draft, track_drafts, artwork_draft, candidate = _candidate_to_drafts(
        editor,
        request.provider,
        request.providerReleaseId,
    )
    return BatchEditApplyReleaseResponseSchema(
        albumId=album_id,
        candidate=candidate,
        album=album_draft,
        tracks=track_drafts,
        artwork=artwork_draft,
        diff=_build_release_diff(editor, album_draft, track_drafts, artwork_draft),
    )


def bulk_update_batch_edit_albums(request: BatchEditBulkUpdateRequestSchema) -> BatchEditBulkUpdateResponseSchema:
    updated: list[str] = []
    for album_id in request.albumIds:
        editor = _build_editor_state(album_id)
        album_draft = BatchEditAlbumDraftSchema(
            albumTitle=editor.album.albumTitle,
            albumArtist=request.albumArtist if request.albumArtist is not None else editor.album.albumArtist,
            releaseArtist=editor.album.releaseArtist,
            year=request.year if request.year is not None else editor.album.year,
            genre=request.genre if request.genre is not None else editor.album.genre,
            releaseType=request.releaseType if request.releaseType is not None else editor.album.releaseType,
            label=editor.album.label,
            catalogNumber=editor.album.catalogNumber,
            copyright=editor.album.copyright,
            comment=request.comment if request.comment is not None else editor.album.comment,
        )
        _apply_album_save(
            album_id,
            album_draft,
            editor.tracks,
            BatchEditArtworkDraftSchema(mode="keep"),
        )
        updated.append(album_id)
    return BatchEditBulkUpdateResponseSchema(saved=True, albumIds=updated)


def _build_editor_state(album_id: str) -> BatchEditEditorStateSchema:
    album_path = _resolve_album_path(album_id)
    track_paths = _album_track_paths(album_path)
    track_rows = _build_track_rows(track_paths)
    first_track = read_tags(str(track_paths[0])) if track_paths else None
    album_title = str(first_track.get("album") or Path(album_path).name) if first_track else Path(album_path).name
    album_artist = first_known_artist(
        (first_track or {}).get("albumartist"),
        (first_track or {}).get("artist"),
        fallback="Unknown artist",
    ) or "Unknown artist"
    release_artist = _release_artist_value(track_rows, first_track)
    artwork_state = _artwork_state(track_paths, album_id)
    return BatchEditEditorStateSchema(
        album=BatchEditAlbumDraftSchema(
            albumTitle=album_title,
            albumArtist=album_artist,
            releaseArtist=release_artist,
            year=str(_track_year(first_track) or ""),
            genre=str(first_track.get("genre") or "") if first_track else "",
            releaseType=str(first_track.get("releasetype") or "") if first_track else "",
            label=str(first_track.get("label") or "") if first_track else "",
            catalogNumber=str(first_track.get("catalognumber") or "") if first_track else "",
            copyright=str(first_track.get("copyright") or "") if first_track else "",
            comment=str(first_track.get("comment") or "") if first_track else "",
        ),
        tracks=track_rows,
        artwork=artwork_state,
    )


def _build_track_rows(track_paths: list[Path]) -> list[BatchEditTrackSchema]:
    rows: list[BatchEditTrackSchema] = []
    for index, track_path in enumerate(track_paths, start=1):
        tags = read_tags(str(track_path)) or {}
        artist = first_known_artist(tags.get("trackartist"), tags.get("artist"), fallback="Unknown artist") or "Unknown artist"
        album_artist = first_known_artist(tags.get("albumartist"), tags.get("artist"), fallback="Unknown artist") or "Unknown artist"
        rows.append(
            BatchEditTrackSchema(
                id=_encode_path(str(track_path)),
                path=str(track_path),
                index=index,
                title=str(tags.get("title") or track_path.stem or f"Track {index}"),
                artist=artist,
                albumArtist=album_artist,
                discNumber=str(tags.get("discnumber") or ""),
                trackNumber=str(tags.get("tracknumber") or index),
                genre=str(tags.get("genre") or ""),
                comment=str(tags.get("comment") or ""),
                duration=_format_duration(tags.get("duration_seconds")),
                issues=_track_issues(tags),
            )
        )
    return rows


def _apply_album_save(
    album_id: str,
    album_draft: BatchEditAlbumDraftSchema,
    track_drafts: list[BatchEditTrackSchema],
    artwork: BatchEditArtworkDraftSchema,
) -> None:
    settings_state = get_library_settings_state()
    if not settings_state.isAvailable:
        raise HTTPException(status_code=400, detail=settings_state.error or "Library is not available.")

    album_path = _resolve_album_path(album_id)
    track_paths = _album_track_paths(album_path)
    if not track_paths:
        raise HTTPException(status_code=404, detail="Album not found")

    original_tracks = [read_tags(str(track_path)) or {"path": str(track_path)} for track_path in track_paths]
    track_drafts_by_id = {draft.id: draft for draft in track_drafts}
    merged_tracks: list[dict] = []

    for index, track_path in enumerate(track_paths, start=1):
        current = dict(original_tracks[index - 1])
        current["path"] = str(track_path)
        draft = track_drafts_by_id.get(_encode_path(str(track_path)))
        merged = _merge_track_state(current, album_draft, draft, index)
        merged_tracks.append(merged)

    if artwork.mode == "fetch_provider" and artwork.coverUrl:
        for merged in merged_tracks:
            merged["cover"] = artwork.coverUrl

    for merged in merged_tracks:
        write_metadata_tags(
            merged["path"],
            merged,
            metadata_preservation_settings=settings_state.metadataPreservation.model_dump(),
        )

        if artwork.mode == "remove":
            remove_cover_art(merged["path"])
        elif artwork.mode == "upload":
            picture_bytes, mime_type = _decode_uploaded_artwork(artwork)
            if picture_bytes:
                write_cover_art_bytes(merged["path"], picture_bytes, mime_type or "image/jpeg")

    _write_batch_edit_summary(settings_state.libraryRoot, album_id, album_path, original_tracks, merged_tracks)


def _merge_track_state(current: dict, album_draft: BatchEditAlbumDraftSchema, track_draft: BatchEditTrackSchema | None, index: int) -> dict:
    merged = dict(current)
    merged["album"] = album_draft.albumTitle or merged.get("album") or ""
    merged["albumartist"] = album_draft.albumArtist or merged.get("albumartist") or ""
    merged["artist"] = album_draft.releaseArtist or merged.get("trackartist") or merged.get("artist") or ""
    merged["genre"] = album_draft.genre or merged.get("genre") or ""
    merged["date"] = album_draft.year or merged.get("date") or ""
    if album_draft.year and len(album_draft.year) == 4:
        merged["release_date_iso"] = album_draft.year
    merged["releasetype"] = album_draft.releaseType or merged.get("releasetype") or ""
    merged["label"] = album_draft.label or ""
    merged["catalognumber"] = album_draft.catalogNumber or ""
    merged["copyright"] = album_draft.copyright or ""
    merged["comment"] = album_draft.comment or ""
    merged["tracknumber"] = str(current.get("tracknumber") or index)
    if track_draft:
        merged["title"] = track_draft.title or merged.get("title") or ""
        merged["artist"] = track_draft.artist or merged.get("trackartist") or merged.get("artist") or ""
        merged["albumartist"] = track_draft.albumArtist or merged.get("albumartist") or ""
        merged["discnumber"] = track_draft.discNumber or merged.get("discnumber") or ""
        merged["tracknumber"] = track_draft.trackNumber or merged.get("tracknumber") or ""
        merged["genre"] = track_draft.genre or merged.get("genre") or ""
        merged["comment"] = track_draft.comment or merged.get("comment") or ""
    return merged


def _write_batch_edit_summary(root_path: str, album_id: str, album_path: str, original_tracks: list[dict], merged_tracks: list[dict]) -> None:
    runs_dir = Path(root_path).expanduser() / ".musorg" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    first_before = dict(original_tracks[0]) if original_tracks else {}
    first_after = dict(merged_tracks[0]) if merged_tracks else {}
    before_snapshot = metadata_snapshot(first_before, fallback_album_artist=first_before.get("albumartist"), track_count=len(original_tracks))
    after_snapshot = metadata_snapshot(first_after, fallback_album_artist=first_after.get("albumartist"), track_count=len(merged_tracks))
    override = {
        "albumTitle": first_after.get("album"),
        "albumArtist": first_after.get("albumartist"),
        "year": first_after.get("date"),
        "genre": first_after.get("genre"),
    }
    metadata_intelligence = build_metadata_intelligence(
        before=before_snapshot,
        after=after_snapshot,
        resolved={"path": "batch-edit-manual"},
        override=override,
        group_tracks=merged_tracks,
    )
    summary = {
        "run_id": f"batch-edit-{uuid.uuid4().hex[:8]}",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "root_path": root_path,
        "dry_run": False,
        "output_root": None,
        "manifest_path": None,
        "counts": {
            "files_scanned": len(merged_tracks),
            "tracks_ready": len(merged_tracks),
            "albums_grouped": 1,
            "changed_albums": 1,
            "skipped_items": 0,
            "duplicates": 0,
            "unresolved_matches": 0,
            "warnings": 0,
            "errors": 0,
        },
        "profiling": {
            "stage_timings": [],
            "metrics": {},
        },
        "changed_albums": [
            {
                "album_id": album_id,
                "source_dir": album_path,
                "track_count": len(merged_tracks),
                "before": {
                    "source_dir": album_path,
                    **before_snapshot,
                },
                "after": {
                    "source_dir": album_path,
                    **after_snapshot,
                },
                "output_dir": None,
                "metadata_intelligence": metadata_intelligence,
            }
        ],
        "skipped_items": [],
        "duplicates": [],
        "unresolved_matches": [],
        "warnings": [],
        "errors": [],
    }
    summary_name = f"batch-edit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}.json"
    (runs_dir / summary_name).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _candidate_to_drafts(
    editor: BatchEditEditorStateSchema,
    provider: str,
    provider_release_id: str,
) -> tuple[BatchEditAlbumDraftSchema, list[BatchEditTrackSchema], BatchEditArtworkDraftSchema, BatchEditCandidateSchema]:
    if provider == "deezer":
        album_data = deezer_get_album(int(provider_release_id))
        if not album_data:
            raise HTTPException(status_code=404, detail="Release not found")
        candidate = BatchEditCandidateSchema(
            id=f"deezer:{provider_release_id}",
            provider="deezer",
            providerReleaseId=provider_release_id,
            title=str(album_data.get("title") or editor.album.albumTitle),
            artist=first_known_artist(((album_data.get("artist") or {}).get("name")), editor.album.albumArtist, fallback="Unknown artist") or "Unknown artist",
            year="Unknown",
            trackCount=int(album_data.get("nb_tracks") or 0),
            coverUrl=_deezer_cover_metadata(album_data)[0],
            releaseType=str(album_data.get("record_type") or ""),
            artworkWidth=_deezer_cover_metadata(album_data)[1],
            artworkHeight=_deezer_cover_metadata(album_data)[2],
        )
        provider_tracks = format_deezer_tracks(album_data)
        album_draft = BatchEditAlbumDraftSchema(
            albumTitle=candidate.title,
            albumArtist=candidate.artist,
            releaseArtist=candidate.artist,
            year="",
            genre=str(deezer_genre_value(album_data) or ""),
            releaseType=candidate.releaseType,
            label=str(((album_data.get("label") or {}).get("name")) or album_data.get("label") or ""),
            catalogNumber="",
            copyright="",
            comment=editor.album.comment,
        )
    else:
        release = get_release_details(provider_release_id)
        if not release:
            raise HTTPException(status_code=404, detail="Release not found")
        provider_tracks = format_release_tracks(release)
        mb_cover_url = cover_art_url(release) or ""
        candidate = BatchEditCandidateSchema(
            id=f"musicbrainz:{provider_release_id}",
            provider="musicbrainz",
            providerReleaseId=provider_release_id,
            title=str(release.get("title") or editor.album.albumTitle),
            artist=first_known_artist(artist_credit_phrase(release), editor.album.albumArtist, fallback="Unknown artist") or "Unknown artist",
            year=str(date_year(release.get("date")) or "Unknown"),
            trackCount=len(provider_tracks),
            coverUrl=mb_cover_url,
            releaseType="album",
            artworkWidth=500 if mb_cover_url else None,
            artworkHeight=500 if mb_cover_url else None,
        )
        album_draft = BatchEditAlbumDraftSchema(
            albumTitle=candidate.title,
            albumArtist=candidate.artist,
            releaseArtist=candidate.artist,
            year="" if candidate.year == "Unknown" else candidate.year,
            genre=editor.album.genre,
            releaseType=candidate.releaseType,
            label=editor.album.label,
            catalogNumber=editor.album.catalogNumber,
            copyright=editor.album.copyright,
            comment=editor.album.comment,
        )

    track_drafts: list[BatchEditTrackSchema] = []
    for index, local_track in enumerate(editor.tracks):
        provider_track = provider_tracks[index] if index < len(provider_tracks) else {}
        track_drafts.append(
            BatchEditTrackSchema(
                id=local_track.id,
                path=local_track.path,
                index=local_track.index,
                title=str(provider_track.get("title") or local_track.title),
                artist=str(provider_track.get("artist") or candidate.artist or local_track.artist),
                albumArtist=candidate.artist or local_track.albumArtist,
                discNumber=str(provider_track.get("discnumber") or local_track.discNumber),
                trackNumber=str(provider_track.get("tracknumber") or local_track.trackNumber),
                genre=album_draft.genre or local_track.genre,
                comment=local_track.comment,
                duration=local_track.duration,
                issues=local_track.issues,
            )
        )

    artwork = BatchEditArtworkDraftSchema(
        mode="fetch_provider" if candidate.coverUrl else "keep",
        coverUrl=candidate.coverUrl or None,
    )
    return album_draft, track_drafts, artwork, candidate


def _build_release_diff(
    editor: BatchEditEditorStateSchema,
    album_draft: BatchEditAlbumDraftSchema,
    track_drafts: list[BatchEditTrackSchema],
    artwork: BatchEditArtworkDraftSchema,
) -> list[MetadataDiffFieldSchema]:
    rows: list[MetadataDiffFieldSchema] = []
    if editor.album.albumTitle != album_draft.albumTitle:
        rows.append(MetadataDiffFieldSchema(id="album", label="Album", before=editor.album.albumTitle, after=album_draft.albumTitle, origin="manual_override"))
    if editor.album.releaseArtist != album_draft.releaseArtist:
        rows.append(MetadataDiffFieldSchema(id="artist", label="Artist", before=editor.album.releaseArtist or "—", after=album_draft.releaseArtist or "—", origin="manual_override"))
    if editor.album.albumArtist != album_draft.albumArtist:
        rows.append(MetadataDiffFieldSchema(id="albumartist", label="Album Artist", before=editor.album.albumArtist, after=album_draft.albumArtist, origin="manual_override"))
    if editor.album.year != album_draft.year:
        rows.append(MetadataDiffFieldSchema(id="date", label="Year", before=editor.album.year or "—", after=album_draft.year or "—", origin="manual_override"))
    if editor.album.genre != album_draft.genre:
        rows.append(MetadataDiffFieldSchema(id="genre", label="Genre", before=editor.album.genre or "—", after=album_draft.genre or "—", origin="manual_override"))
    if artwork.mode == "fetch_provider" and artwork.coverUrl:
        rows.append(MetadataDiffFieldSchema(id="cover", label="Cover", before=editor.artwork.source or "Local artwork", after="Provider artwork", origin="manual_override"))
    current_track_count = len(editor.tracks)
    new_track_count = len(track_drafts)
    changed_tracks = sum(
        1
        for current, next_track in zip(editor.tracks, track_drafts)
        if current.title != next_track.title or current.artist != next_track.artist or current.trackNumber != next_track.trackNumber
    )
    if changed_tracks or current_track_count != new_track_count:
        after_text = f"{new_track_count} tracks"
        if changed_tracks:
            after_text = f"{after_text} ({changed_tracks} rows updated)"
        rows.append(MetadataDiffFieldSchema(id="tracks", label="Tracks", before=f"{current_track_count} tracks", after=after_text, origin="manual_override"))
    return rows


def _artwork_state(track_paths: list[Path], album_id: str):
    has_artwork = False
    for track_path in track_paths:
        tags = read_tags(str(track_path)) or {}
        if tags.get("has_cover_art"):
            has_artwork = True
            break
    return {
        "hasArtwork": has_artwork,
        "coverUrl": f"/albums/{album_id}/cover" if has_artwork else "",
        "source": "embedded" if has_artwork else None,
    }


def _track_issues(tags: dict) -> list[AlbumIssueSchema]:
    issues: list[AlbumIssueSchema] = []
    if not tags.get("title") or str(tags.get("title") or "").strip() in {"", "Unknown"}:
        issues.append(AlbumIssueSchema(id="missing-title", label="Missing title", severity="warning"))
    if not tags.get("tracknumber") or str(tags.get("tracknumber") or "").strip() in {"", "0"}:
        issues.append(AlbumIssueSchema(id="missing-track", label="Missing track number", severity="warning"))
    if not first_known_artist(tags.get("trackartist"), tags.get("artist")):
        issues.append(AlbumIssueSchema(id="missing-artist", label="Missing artist", severity="warning"))
    return issues


def _release_artist_value(track_rows: list[BatchEditTrackSchema], first_track: dict | None) -> str:
    unique_artists = {row.artist for row in track_rows if known_artist(row.artist)}
    if len(unique_artists) == 1:
        return next(iter(unique_artists))
    if first_track:
        return first_known_artist(first_track.get("trackartist"), first_track.get("artist"), fallback="") or ""
    return ""


def _track_year(track: dict | None) -> str:
    if not track:
        return ""
    value = str(track.get("date") or "").strip()
    if len(value) >= 4 and value[:4].isdigit():
        return value[:4]
    return value if len(value) == 4 else ""


def _decode_uploaded_artwork(artwork: BatchEditArtworkDraftSchema) -> tuple[bytes | None, str | None]:
    if not artwork.imageBase64:
        return None, artwork.mimeType
    raw = artwork.imageBase64
    if "," in raw and raw.startswith("data:"):
        prefix, raw = raw.split(",", 1)
        if ";base64" in prefix and not artwork.mimeType:
            artwork.mimeType = prefix.split(":", 1)[1].split(";", 1)[0]
    try:
        return base64.b64decode(raw), artwork.mimeType
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid artwork payload")


def _format_duration(value: object) -> str:
    try:
        total_seconds = int(float(value or 0))
    except (TypeError, ValueError):
        return "--:--"
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _musicbrainz_track_count(release: dict) -> int:
    total = 0
    for medium in release.get("medium-list", []) or release.get("media", []) or []:
        total += len(medium.get("track-list", []) or medium.get("tracks", []) or [])
    return total


def _deezer_cover_metadata(item: dict) -> tuple[str, int | None, int | None]:
    candidates = (
        ("cover_xl", 1000),
        ("cover_big", 500),
        ("cover_medium", 250),
        ("cover_small", 56),
        ("cover", None),
    )
    for key, size in candidates:
        value = str(item.get(key) or "").strip()
        if value:
            return value, size, size
    return "", None, None


def _album_track_paths(album_path: str) -> list[Path]:
    folder = Path(album_path).expanduser().resolve()
    files = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS
    ]
    files.sort(key=_track_sort_key)
    return files


def _track_sort_key(path: Path):
    tags = read_tags(str(path)) or {}
    try:
        disc = int(str(tags.get("discnumber") or "0").split("/", maxsplit=1)[0] or 0)
    except (TypeError, ValueError):
        disc = 0
    try:
        track = int(str(tags.get("tracknumber") or "0").split("/", maxsplit=1)[0] or 0)
    except (TypeError, ValueError):
        track = 0
    return (disc, track, path.name.lower())


def _resolve_album_path(album_id: str) -> str:
    settings_state = get_library_settings_state()
    if not settings_state.isAvailable:
        raise HTTPException(status_code=404, detail="Library is not available")
    root = Path(settings_state.libraryRoot).expanduser().resolve()
    folder = Path(_decode_path(album_id)).expanduser().resolve()
    if not folder.exists() or not folder.is_dir() or not folder.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Album not found")
    # Once an album is tidied up, batch editing should operate on the processed
    # output (until the user deletes it). The resolver returns the output folder
    # for completed albums and falls back to the source otherwise.
    resolution = resolve_album_runtime_state(str(root), str(folder))
    resolved = Path(resolution.resolved_folder_path).expanduser().resolve()
    if resolution.resolved_mode == "output" and resolved.exists() and resolved.is_dir():
        return str(resolved)
    return str(folder)


def _encode_path(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_path(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii")).decode("utf-8")
