from __future__ import annotations

import base64
import os
import re

from musorg.core.issue_counts import summarize_actionable_issue_items
from musorg.core.metadata_intelligence import augment_metadata_intelligence, metadata_intelligence_issues


def encode_album_id(folder_path: str) -> str:
    return base64.urlsafe_b64encode(folder_path.encode("utf-8")).decode("ascii").rstrip("=")


def source_album_id_for_tracks(album_tracks: list[dict]) -> str | None:
    if not album_tracks:
        return None
    folder_path = source_album_folder(album_tracks[0])
    if not folder_path:
        return None
    return encode_album_id(folder_path)


def source_album_folder(track: dict) -> str:
    return str(os.path.dirname(str(track.get("path") or ""))).strip()


def runtime_album_payload(
    album_tracks: list[dict],
    *,
    processing_state: str,
    output_path: str | None = None,
    provider: str | None = None,
    complete: bool = False,
) -> dict | None:
    if not album_tracks:
        return None

    album_id = source_album_id_for_tracks(album_tracks)
    if not album_id:
        return None

    sample = album_tracks[0]
    track_rows = runtime_tracks_patch(album_tracks)
    metadata_intelligence = augment_metadata_intelligence(
        sample.get("_metadata_intelligence"),
        output_path=output_path,
        complete=complete,
    )
    issue_counts = runtime_issue_counts(track_rows, metadata_intelligence=metadata_intelligence, complete=complete)
    album_patch = {
        "id": album_id,
        "title": runtime_display_title(sample),
        "artist": runtime_artist(sample),
        "year": runtime_year(sample),
        "trackCount": len(album_tracks),
        "coverUrl": runtime_cover_url(sample, album_id),
        "issueCounts": issue_counts,
        "status": "ready" if complete or (issue_counts["danger"] == 0 and issue_counts["warning"] == 0) else "issues",
        "processingState": processing_state,
        "outputPath": output_path,
        "provider": provider,
        "releaseType": str(sample.get("releasetype") or ""),
        "confidenceLevel": ((metadata_intelligence or {}).get("confidence") or {}).get("level"),
        "lowConfidence": runtime_low_confidence(metadata_intelligence),
        "metadataIntelligence": metadata_intelligence,
    }
    inspector_patch = runtime_inspector_patch(album_tracks, album_id, processing_state, metadata_intelligence=metadata_intelligence)
    return {
        "albumId": album_id,
        "processedAlbum": album_patch,
        "albumPatch": album_patch,
        "inspectorPatch": inspector_patch,
        "tracksPatch": track_rows,
        "outputPath": output_path,
        "provider": provider,
        "progress": processing_state,
        "issueCounts": issue_counts,
        "coverUrl": album_patch["coverUrl"],
        "metadataIntelligence": metadata_intelligence,
    }


def runtime_tracks_patch(album_tracks: list[dict]) -> list[dict]:
    folder_path = source_album_folder(album_tracks[0]) if album_tracks else ""
    ordered_tracks = sorted(
        album_tracks,
        key=lambda track: (
            int(track.get("discnumber") or 0),
            int(track.get("tracknumber") or 0),
            str(track.get("title") or "").lower(),
        ),
    )
    rows = []
    fallback_artist = runtime_artist(album_tracks[0]) if album_tracks else "Unknown artist"
    for index, track in enumerate(ordered_tracks, start=1):
        rows.append({
            "id": f"{folder_path}:{index}",
            "checked": True,
            "index": index,
            "title": str(track.get("title") or f"Track {index}"),
            "artist": str(track.get("artist") or fallback_artist or "Unknown artist"),
            "duration": runtime_duration(track),
            "issues": runtime_track_issues(track),
        })
    return rows


def runtime_inspector_patch(
    album_tracks: list[dict],
    album_id: str,
    processing_state: str,
    *,
    metadata_intelligence: dict | None = None,
) -> dict:
    sample = album_tracks[0]
    issue_counts = runtime_issue_counts(
        runtime_tracks_patch(album_tracks),
        metadata_intelligence=metadata_intelligence,
        complete=processing_state == "completed",
    )
    issues = runtime_album_issues(
        issue_counts,
        track_rows=runtime_tracks_patch(album_tracks),
        metadata_intelligence=metadata_intelligence,
    )
    return {
        "id": album_id,
        "coverUrl": runtime_cover_url(sample, album_id),
        "title": runtime_display_title(sample),
        "artist": runtime_artist(sample),
        "year": runtime_year(sample),
        "albumArtist": str(sample.get("albumartist") or sample.get("artist") or "Unknown artist"),
        "genre": str(sample.get("genre") or "Unknown"),
        "disc": str(sample.get("discnumber") or "1"),
        "metrics": [
            {"id": "info", "label": "Info", "value": "i", "severity": "neutral"},
            {"id": "danger", "label": "Issues", "value": str(issue_counts["danger"]), "severity": "danger"},
            {"id": "warning", "label": "Metadata", "value": str(issue_counts["warning"]), "severity": "warning"},
            {"id": "success", "label": "Ready", "value": str(issue_counts["success"]), "severity": "success"},
        ],
        "issues": issues,
        "processingState": processing_state,
        "provider": str(sample.get("_metadata_provider") or sample.get("provider") or ""),
        "confidenceLevel": ((metadata_intelligence or {}).get("confidence") or {}).get("level"),
        "lowConfidence": runtime_low_confidence(metadata_intelligence),
        "metadataIntelligence": metadata_intelligence,
    }


def runtime_issue_counts(track_rows: list[dict], *, metadata_intelligence: dict | None = None, complete: bool) -> dict:
    suspicious_issues = metadata_intelligence_issues(metadata_intelligence)
    if complete:
        return summarize_actionable_issue_items(suspicious_issues)
    row_issues = (
        {"severity": "warning"}
        for row in track_rows
        if row.get("issues")
    )
    merged_issues = [*suspicious_issues, *row_issues]
    return summarize_actionable_issue_items(merged_issues)


def runtime_album_issues(
    issue_counts: dict,
    *,
    track_rows: list[dict],
    metadata_intelligence: dict | None = None,
) -> list[dict]:
    issues = []
    if any(row.get("issues") for row in track_rows):
        issues.append({
            "id": "missing-metadata",
            "label": "Missing metadata",
            "severity": "warning",
        })
    for issue in metadata_intelligence_issues(metadata_intelligence):
        issues.append(issue)
    return issues


def runtime_track_issues(track: dict) -> list[dict]:
    if str(track.get("title") or "").strip() and str(track.get("artist") or "").strip():
        return []
    return [{
        "id": "missing-metadata",
        "label": "Missing metadata",
        "severity": "warning",
    }]


def runtime_cover_url(track: dict, album_id: str) -> str:
    cover = str(track.get("cover") or "").strip()
    return cover or f"/albums/{album_id}/cover"


def runtime_artist(track: dict) -> str:
    return str(track.get("albumartist") or track.get("artist") or "Unknown artist")


def runtime_year(track: dict) -> str:
    release_date_iso = str(track.get("release_date_iso") or "").strip()
    if re.match(r"^\d{4}", release_date_iso):
        return release_date_iso[:4]
    date = str(track.get("date") or "").strip()
    if re.match(r"^\d{4}$", date):
        return date
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return date[:4]
    return "Unknown"


def runtime_display_title(track: dict) -> str:
    year = runtime_year(track)
    album = str(track.get("album") or "Unknown album")
    if year != "Unknown":
        prefix = f"{year} - "
        while album.startswith(prefix):
            album = album[len(prefix):]
    return album


def runtime_low_confidence(metadata_intelligence: dict | None) -> bool:
    if not metadata_intelligence:
        return False
    confidence = (metadata_intelligence.get("confidence") or {}) if isinstance(metadata_intelligence, dict) else {}
    level = str(confidence.get("level") or "").strip()
    return level in {"low", "suspicious"}


def runtime_duration(track: dict) -> str:
    seconds = track.get("duration_seconds")
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "--:--"
    minutes = total // 60
    remainder = total % 60
    return f"{minutes}:{remainder:02d}"
