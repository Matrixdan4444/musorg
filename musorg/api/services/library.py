from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, Response

from musorg.api.schemas.music import (
    AlbumActionsResponseSchema,
    AlbumDetailResponse,
    AlbumInspectorSchema,
    AlbumIssueSchema,
    AlbumListItemSchema,
    AlbumsResponse,
    InspectorMetricSchema,
    IssueCountsSchema,
    ReleaseComparisonResponseSchema,
    ReleaseIntelligenceSummarySchema,
    RelatedReleaseItemSchema,
    SmartActionSchema,
    TrackRowSchema,
    TracksResponse,
)
from musorg.api.services.settings import get_effective_library_root, get_library_settings_state
from musorg.core.cover_art import load_album_cover_bytes
from musorg.core.issue_counts import summarize_actionable_issue_items
from musorg.core.insights import InsightRegistry, build_insight_registry
from musorg.core.library_preview import AlbumDetail, AlbumPreview, TrackPreview, load_album_detail, scan_album_previews
from musorg.core.release_intelligence import ReleaseIntelligenceRegistry, build_release_intelligence_registry
from musorg.core.smart_actions import build_smart_action_registry


_ISSUE_MAP: dict[str, tuple[str, str]] = {
    "unknown_artist": ("Missing album artist", "danger"),
    "missing_track_numbers": ("Missing track number", "warning"),
    "missing_release_date": ("Missing release year", "warning"),
    "album_artist_inconsistency": ("Album artist inconsistency", "danger"),
    "missing_cover": ("Cover art could be higher resolution", "warning"),
}


@dataclass(frozen=True)
class AlbumRuntimeStateResolution:
    processing_state: str | None
    output_path: str | None
    resolved_folder_path: str
    resolved_mode: str


def get_active_library_root() -> str:
    return get_effective_library_root()


def get_album_cover_response(album_id: str) -> Response:
    return get_album_cover_response_for_root(album_id, None)


def list_albums() -> AlbumsResponse:
    settings_state = get_library_settings_state()
    library_path = settings_state.libraryRoot
    if not settings_state.isAvailable:
        return AlbumsResponse(libraryPath=library_path, albums=[])

    return list_albums_for_root(library_path, include_metadata_intelligence=False)


def list_albums_for_root(
    root_path: str,
    *,
    cover_url_builder: Callable[[str, tuple[str, ...]], str] | None = None,
    include_metadata_intelligence: bool = True,
    resolve_runtime_output: bool = True,
) -> AlbumsResponse:
    settings_state = get_library_settings_state()
    previews = scan_album_previews(root_path)
    intelligence_by_path = _latest_metadata_intelligence_by_path(root_path) if include_metadata_intelligence else {}
    release_registry = build_release_intelligence_registry(root_path, metadata_intelligence_by_path=intelligence_by_path)
    insight_registry = build_insight_registry(release_registry, intelligence_by_path)
    output_paths_by_source = _latest_output_path_by_source(root_path) if resolve_runtime_output else {}
    runtime_state_by_path = _runtime_state_by_path(
        root_path,
        tuple(str(Path(preview.folder_path).expanduser().resolve()) for preview in previews),
        latest_output_paths=output_paths_by_source,
        resolve_runtime_output=resolve_runtime_output,
    )
    action_registry = build_smart_action_registry(
        release_registry,
        insight_registry,
        metadata_intelligence_by_path=intelligence_by_path,
        runtime_state_by_path=runtime_state_by_path,
        duplicate_handling=settings_state.duplicateHandling,
    )
    return AlbumsResponse(
        libraryPath=root_path,
        albums=[
            _serialize_preview(
                preview,
                root_path=root_path,
                cover_url_builder=cover_url_builder,
                metadata_intelligence=intelligence_by_path.get(str(Path(preview.folder_path).expanduser().resolve())),
                release_intelligence=release_registry.summaries_by_path.get(str(Path(preview.folder_path).expanduser().resolve())),
                action_summary=action_registry.summaries_by_path.get(str(Path(preview.folder_path).expanduser().resolve())),
                runtime_resolution=resolve_album_runtime_state(
                    root_path,
                    preview.folder_path,
                    latest_output_paths=output_paths_by_source,
                    resolve_runtime_output=resolve_runtime_output,
                ),
            )
            for preview in previews
        ],
    )


def get_album_detail_payload(album_id: str) -> AlbumDetailResponse:
    return get_album_detail_payload_for_root(album_id, None, include_metadata_intelligence=False)


def get_album_detail_payload_for_root(
    album_id: str,
    root_path: str | None,
    *,
    cover_url_builder: Callable[[str, tuple[str, ...]], str] | None = None,
    include_metadata_intelligence: bool = True,
    resolve_runtime_output: bool = True,
) -> AlbumDetailResponse:
    settings_state = get_library_settings_state()
    lookup_root = _available_library_root() if root_path is None else _normalize_root_path(root_path)
    source_folder_path = _resolve_source_album_path(album_id, root_path)
    runtime_resolution = resolve_album_runtime_state(
        lookup_root,
        source_folder_path,
        resolve_runtime_output=resolve_runtime_output,
    )
    detail = load_album_detail(runtime_resolution.resolved_folder_path, lookup_root)
    intelligence_by_path = _latest_metadata_intelligence_by_path(lookup_root) if include_metadata_intelligence else {}
    intelligence = intelligence_by_path.get(source_folder_path) if include_metadata_intelligence else None
    release_registry = build_release_intelligence_registry(lookup_root, metadata_intelligence_by_path=intelligence_by_path)
    insight_registry = build_insight_registry(release_registry, intelligence_by_path)
    action_registry = build_smart_action_registry(
        release_registry,
        insight_registry,
        metadata_intelligence_by_path=intelligence_by_path,
        runtime_state_by_path={
            source_folder_path: {
                "processingState": runtime_resolution.processing_state or "idle",
                "outputPath": runtime_resolution.output_path,
            },
        },
        duplicate_handling=settings_state.duplicateHandling,
    )
    return AlbumDetailResponse(
        album=_serialize_detail(
            album_id,
            detail,
            cover_url_builder=cover_url_builder,
            metadata_intelligence=intelligence,
            release_intelligence=release_registry.summaries_by_path.get(source_folder_path),
            action_summary=action_registry.summaries_by_path.get(source_folder_path),
            runtime_resolution=runtime_resolution,
        ),
    )


def get_album_tracks_payload(album_id: str) -> TracksResponse:
    return get_album_tracks_payload_for_root(album_id, None)


def get_album_tracks_payload_for_root(album_id: str, root_path: str | None) -> TracksResponse:
    source_folder_path = _resolve_source_album_path(album_id, root_path)
    lookup_root = _available_library_root() if root_path is None else _normalize_root_path(root_path)
    runtime_resolution = resolve_album_runtime_state(lookup_root, source_folder_path)
    detail = load_album_detail(runtime_resolution.resolved_folder_path, lookup_root)
    return TracksResponse(tracks=_serialize_tracks(detail))


def get_album_cover_response_for_root(
    album_id: str,
    root_path: str | None,
    *,
    resolve_runtime_output: bool = True,
) -> Response:
    source_folder_path = _resolve_source_album_path(album_id, root_path)
    lookup_root = _available_library_root() if root_path is None else _normalize_root_path(root_path)
    runtime_resolution = resolve_album_runtime_state(
        lookup_root,
        source_folder_path,
        resolve_runtime_output=resolve_runtime_output,
    )
    cover_bytes = load_album_cover_bytes(runtime_resolution.resolved_folder_path)
    if not cover_bytes:
        raise HTTPException(status_code=404, detail="Cover not found")
    return Response(content=cover_bytes, media_type=_cover_mime_type(cover_bytes))


def get_related_releases_payload(album_id: str) -> ReleaseComparisonResponseSchema:
    return get_related_releases_payload_for_root(album_id, None)


def get_album_actions_payload(album_id: str) -> AlbumActionsResponseSchema:
    return get_album_actions_payload_for_root(album_id, None)


def get_related_releases_payload_for_root(
    album_id: str,
    root_path: str | None,
) -> ReleaseComparisonResponseSchema:
    lookup_root = _available_library_root() if root_path is None else _normalize_root_path(root_path)
    source_folder_path = _resolve_source_album_path(album_id, root_path)
    registry = build_release_intelligence_registry(
        lookup_root,
        metadata_intelligence_by_path=_latest_metadata_intelligence_by_path(lookup_root),
    )
    payload = registry.related_payload_by_path.get(source_folder_path)
    summary = registry.summaries_by_path.get(source_folder_path)
    if payload is None or summary is None:
        fallback_item = RelatedReleaseItemSchema(
            id=album_id,
            releaseFamilyId=None,
            releaseVariantId=None,
            title=Path(source_folder_path).name,
            artist="Unknown artist",
            year="Unknown",
            trackCount=0,
            formatSummary="Unknown",
            qualityScore=0,
            qualityRank=None,
            bestVersion=False,
            releaseVariantType="unknown",
            relationshipStatus="standalone",
            duplicateConfidence=0,
            fakeFlacStatus="none",
            reasons=[],
            releaseActions=[],
            current=True,
        )
        return ReleaseComparisonResponseSchema(
            albumId=album_id,
            releaseFamilyId=None,
            current=fallback_item,
            family=[fallback_item],
            possibleMatches=[],
        )
    return ReleaseComparisonResponseSchema(
        albumId=album_id,
        releaseFamilyId=payload.get("releaseFamilyId"),
        current=_serialize_related_release_item(album_id, payload["current"]),
        family=[_serialize_related_release_item(album_id if item.get("current") else _encode_album_id(_path_for_related_release(item, registry)), item) for item in payload["family"]],
        possibleMatches=[_serialize_related_release_item(_encode_album_id(_path_for_related_release(item, registry)), item) for item in payload.get("possibleMatches", [])],
    )


def get_album_actions_payload_for_root(
    album_id: str,
    root_path: str | None,
) -> AlbumActionsResponseSchema:
    settings_state = get_library_settings_state()
    lookup_root = _available_library_root() if root_path is None else _normalize_root_path(root_path)
    source_folder_path = _resolve_source_album_path(album_id, root_path)
    intelligence_by_path = _latest_metadata_intelligence_by_path(lookup_root)
    release_registry = build_release_intelligence_registry(
        lookup_root,
        metadata_intelligence_by_path=intelligence_by_path,
    )
    insight_registry = build_insight_registry(release_registry, intelligence_by_path)
    runtime_state_by_path = _runtime_state_by_path(lookup_root, tuple(release_registry.summaries_by_path.keys()))
    action_registry = build_smart_action_registry(
        release_registry,
        insight_registry,
        metadata_intelligence_by_path=intelligence_by_path,
        runtime_state_by_path=runtime_state_by_path,
        duplicate_handling=settings_state.duplicateHandling,
    )
    payload = action_registry.payloads_by_path.get(source_folder_path)
    if not payload:
        return AlbumActionsResponseSchema(albumId=album_id, snapshotId=action_registry.snapshot_id)
    return AlbumActionsResponseSchema(
        albumId=album_id,
        snapshotId=str(payload.get("snapshotId") or action_registry.snapshot_id),
        topAction=_serialize_smart_action(payload.get("topAction")),
        actionSummary=_serialize_smart_actions(payload.get("actionSummary")),
        actionCount=int(payload.get("actionCount") or 0),
        recommendationSummary=_clean_text(payload.get("recommendationSummary")),
        albumActions=_serialize_smart_actions(payload.get("albumActions")),
        familyActions=_serialize_smart_actions(payload.get("familyActions")),
        suppressedActions=_serialize_smart_actions(payload.get("suppressedActions")),
    )


def _load_detail(album_id: str, root_path: str | None = None) -> AlbumDetail:
    folder_path = _resolve_source_album_path(album_id, root_path)
    library_root = _available_library_root() if root_path is None else _normalize_root_path(root_path)
    return load_album_detail(folder_path, library_root)


def _available_library_root() -> str:
    settings_state = get_library_settings_state()
    if not settings_state.isAvailable:
        raise HTTPException(status_code=404, detail="Library is not available")
    return settings_state.libraryRoot


def _root_path() -> Path:
    return Path(_available_library_root()).expanduser().resolve()


def _normalize_root_path(root_path: str) -> str:
    return str(Path(root_path).expanduser().resolve())


def _resolve_source_album_path(album_id: str, root_path: str | None = None) -> str:
    root = Path(_normalize_root_path(root_path)) if root_path is not None else _root_path()
    folder = Path(_decode_album_id(album_id)).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Album not found")
    if not folder.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Album not found")
    return str(folder)


def _encode_album_id(folder_path: str) -> str:
    return base64.urlsafe_b64encode(folder_path.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_album_id(album_id: str) -> str:
    padding = "=" * (-len(album_id) % 4)
    try:
        folder_path = base64.urlsafe_b64decode(f"{album_id}{padding}".encode("ascii")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive invalid input handling
        raise HTTPException(status_code=404, detail="Album not found") from exc
    return folder_path


def _serialize_preview(
    preview: AlbumPreview,
    *,
    root_path: str,
    cover_url_builder: Callable[[str, tuple[str, ...]], str] | None = None,
    metadata_intelligence: dict | None = None,
    release_intelligence: dict | None = None,
    action_summary: dict | None = None,
    runtime_resolution: AlbumRuntimeStateResolution,
) -> AlbumListItemSchema:
    album_id = _encode_album_id(preview.folder_path)
    resolved_preview = _resolved_preview_for_list(preview, runtime_resolution, root_path)
    year = _preferred_year(resolved_preview.release_year or _year_from_title(resolved_preview.album_title))
    issue_counts = _album_status_counts(resolved_preview.issues, metadata_intelligence=metadata_intelligence)
    return AlbumListItemSchema(
        id=album_id,
        title=_display_title(resolved_preview.album_title, year),
        artist=_text_or(resolved_preview.artist_name, "Unknown artist"),
        year=year,
        trackCount=resolved_preview.track_count,
        coverUrl=_cover_url(album_id, resolved_preview.issues, cover_url_builder=cover_url_builder),
        issueCounts=issue_counts,
        status="ready" if issue_counts.danger == 0 and issue_counts.warning == 0 else "issues",
        processingState=runtime_resolution.processing_state,
        outputPath=runtime_resolution.output_path,
        provider=_provider_value(metadata_intelligence),
        confidenceLevel=_confidence_level(metadata_intelligence),
        lowConfidence=_is_low_confidence(metadata_intelligence),
        metadataIntelligence=metadata_intelligence,
        releaseIntelligence=_release_intelligence_summary(release_intelligence),
        topAction=_serialize_smart_action((action_summary or {}).get("topAction")),
        actionSummary=_serialize_smart_actions((action_summary or {}).get("actionSummary")),
        actionCount=int((action_summary or {}).get("actionCount") or 0),
    )


def _serialize_detail(
    album_id: str,
    detail: AlbumDetail,
    *,
    cover_url_builder: Callable[[str, tuple[str, ...]], str] | None = None,
    metadata_intelligence: dict | None = None,
    release_intelligence: dict | None = None,
    action_summary: dict | None = None,
    runtime_resolution: AlbumRuntimeStateResolution,
) -> AlbumInspectorSchema:
    issue_models = [_album_issue(issue_key) for issue_key in detail.issues]
    issue_models.extend(_metadata_intelligence_issues(metadata_intelligence))
    counts = summarize_actionable_issue_items(({"severity": issue.severity} for issue in issue_models))
    year = _preferred_year(detail.release_year)
    return AlbumInspectorSchema(
        id=album_id,
        coverUrl=_cover_url(album_id, detail.issues, cover_url_builder=cover_url_builder),
        title=_display_title(detail.album_title, year),
        artist=_text_or(detail.artist_name, "Unknown artist"),
        year=year,
        albumArtist=_text_or(detail.album_artist or detail.artist_name, "Unknown artist"),
        genre=_text_or(detail.genre, "Unknown"),
        disc=_text_or(detail.disc_number, "1"),
        metrics=[
            InspectorMetricSchema(id="info", label="Info", value="i", severity="neutral"),
            InspectorMetricSchema(id="danger", label="Issues", value=str(counts["danger"]), severity="danger"),
            InspectorMetricSchema(id="warning", label="Metadata", value=str(counts["warning"]), severity="warning"),
            InspectorMetricSchema(id="success", label="Ready", value=str(counts["success"]), severity="success"),
        ],
        issues=issue_models,
        processingState=runtime_resolution.processing_state,
        outputPath=runtime_resolution.output_path,
        provider=_provider_value(metadata_intelligence),
        confidenceLevel=_confidence_level(metadata_intelligence),
        lowConfidence=_is_low_confidence(metadata_intelligence),
        metadataIntelligence=metadata_intelligence,
        releaseIntelligence=_release_intelligence_summary(release_intelligence),
        topAction=_serialize_smart_action((action_summary or {}).get("topAction")),
        actionSummary=_serialize_smart_actions((action_summary or {}).get("actionSummary")),
        actionCount=int((action_summary or {}).get("actionCount") or 0),
    )


def _serialize_tracks(detail: AlbumDetail) -> list[TrackRowSchema]:
    rows: list[TrackRowSchema] = []
    fallback_artist = _text_or(detail.artist_name, "Unknown artist")
    for index, track in enumerate(detail.tracks, start=1):
        rows.append(
            TrackRowSchema(
                id=f"{detail.folder_path}:{index}",
                checked=True,
                index=index,
                title=_text_or(track.track_title, f"Track {index}"),
                artist=_text_or(track.artist_name, fallback_artist),
                duration=_text_or(track.duration_text, "--:--"),
                issues=_track_issue(track),
            )
        )
    return rows


def _track_issue(track: TrackPreview) -> list[AlbumIssueSchema]:
    if track.issue_count <= 0:
        return []
    return [
        AlbumIssueSchema(
            id="missing-metadata",
            label="Missing metadata",
            severity="warning",
        )
    ]


def _album_issue(issue_key: str) -> AlbumIssueSchema:
    label, severity = _ISSUE_MAP.get(issue_key, (issue_key.replace("_", " ").title(), "warning"))
    return AlbumIssueSchema(id=issue_key, label=label, severity=severity)  # type: ignore[arg-type]


def _album_status_counts(
    issue_keys: tuple[str, ...],
    *,
    metadata_intelligence: dict | None = None,
) -> IssueCountsSchema:
    issue_models = [_album_issue(issue_key) for issue_key in issue_keys]
    issue_models.extend(_metadata_intelligence_issues(metadata_intelligence))
    counts = summarize_actionable_issue_items(({"severity": issue.severity} for issue in issue_models))
    return IssueCountsSchema(**counts)


def _cover_url(
    album_id: str,
    issue_keys: tuple[str, ...],
    *,
    cover_url_builder: Callable[[str, tuple[str, ...]], str] | None = None,
) -> str:
    if "missing_cover" in issue_keys:
        return ""
    if cover_url_builder is not None:
        return cover_url_builder(album_id, issue_keys)
    return f"/albums/{album_id}/cover"


def resolve_album_runtime_state(
    root_path: str,
    source_folder_path: str,
    *,
    latest_output_paths: dict[str, str] | None = None,
    resolve_runtime_output: bool = True,
) -> AlbumRuntimeStateResolution:
    normalized_root = _normalize_root_path(root_path)
    normalized_source = str(Path(source_folder_path).expanduser().resolve())
    if not resolve_runtime_output:
        return AlbumRuntimeStateResolution(
            processing_state=None,
            output_path=None,
            resolved_folder_path=normalized_source,
            resolved_mode="source",
        )
    output_paths = latest_output_paths if latest_output_paths is not None else _latest_output_path_by_source(normalized_root)
    output_path = output_paths.get(normalized_source)
    if output_path and _is_valid_processed_album(output_path, normalized_root):
        return AlbumRuntimeStateResolution(
            processing_state="completed",
            output_path=output_path,
            resolved_folder_path=output_path,
            resolved_mode="output",
        )
    return AlbumRuntimeStateResolution(
        processing_state=None,
        output_path=None,
        resolved_folder_path=normalized_source,
        resolved_mode="source",
    )


def _resolved_preview_for_list(
    preview: AlbumPreview,
    runtime_resolution: AlbumRuntimeStateResolution,
    root_path: str,
) -> AlbumPreview:
    if runtime_resolution.resolved_mode != "output":
        return preview
    try:
        detail = load_album_detail(runtime_resolution.resolved_folder_path, root_path)
    except Exception:
        return preview
    return AlbumPreview(
        album_title=detail.album_title,
        artist_name=detail.artist_name,
        track_count=len(detail.tracks),
        folder_path=preview.folder_path,
        status=detail.status,
        issues=detail.issues,
        release_year=detail.release_year,
    )


def _display_title(title: str | None, year: str) -> str:
    normalized = _text_or(title, "Unknown album")
    if year != "Unknown":
        prefix = f"{year} - "
        while normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized


def _preferred_year(value: str | None) -> str:
    text = _clean_text(value)
    return text or "Unknown"


def _text_or(value: str | None, fallback: str) -> str:
    text = _clean_text(value)
    return text or fallback


def _clean_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _year_from_title(title: str) -> str:
    normalized = _clean_text(title)
    if len(normalized) >= 4 and normalized[:4].isdigit():
        return normalized[:4]
    return ""


def _cover_mime_type(cover_bytes: bytes) -> str:
    if cover_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if cover_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if cover_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if cover_bytes.startswith(b"RIFF") and b"WEBP" in cover_bytes[:16]:
        return "image/webp"
    return "image/jpeg"


def _metadata_intelligence_issues(metadata_intelligence: dict | None) -> list[AlbumIssueSchema]:
    if not metadata_intelligence:
        return []
    issues = []
    for item in metadata_intelligence.get("suspiciousMetadata") or []:
        if not isinstance(item, dict):
            continue
        issue_id = _clean_text(item.get("id"))
        if not issue_id:
            continue
        issues.append(
            AlbumIssueSchema(
                id=issue_id,
                label=_clean_text(item.get("label")) or issue_id.replace("-", " ").title(),
                severity=_clean_text(item.get("severity")) or "warning",
            )
        )
    return issues


def _provider_value(metadata_intelligence: dict | None) -> str | None:
    if not metadata_intelligence:
        return None
    provider_decisions = metadata_intelligence.get("providerDecisions") or {}
    return _clean_text(provider_decisions.get("metadataProvider"))


def _confidence_level(metadata_intelligence: dict | None) -> str | None:
    if not metadata_intelligence:
        return None
    confidence = metadata_intelligence.get("confidence") or {}
    return _clean_text(confidence.get("level"))


def _is_low_confidence(metadata_intelligence: dict | None) -> bool:
    if not metadata_intelligence:
        return False
    confidence = metadata_intelligence.get("confidence") or {}
    level = _clean_text(confidence.get("level"))
    return level in {"low", "suspicious"}


def _release_intelligence_summary(release_intelligence: dict | None) -> ReleaseIntelligenceSummarySchema | None:
    if not release_intelligence:
        return None
    return ReleaseIntelligenceSummarySchema(**release_intelligence)


def _serialize_smart_action(item: dict | None) -> SmartActionSchema | None:
    if not item:
        return None
    related_paths = item.get("affectedAlbumPaths") if isinstance(item, dict) else []
    affected_album_ids = [
        _encode_album_id(path_value)
        for path_value in related_paths
        if isinstance(path_value, str) and path_value.strip()
    ]
    normalized_item = {
        key: value
        for key, value in item.items()
        if key != "affectedAlbumPaths"
    }
    normalized_item["affectedAlbumIds"] = affected_album_ids
    return SmartActionSchema(**normalized_item)


def _serialize_smart_actions(items: list[dict] | None) -> list[SmartActionSchema]:
    if not items:
        return []
    return [serialized for item in items if (serialized := _serialize_smart_action(item))]


def _serialize_related_release_item(album_id: str, item: dict) -> RelatedReleaseItemSchema:
    safe_album_id = album_id or "unknown-release"
    normalized_item = {key: value for key, value in item.items() if key != "id"}
    return RelatedReleaseItemSchema(id=safe_album_id, **normalized_item)


def _path_for_related_release(item: dict, registry: ReleaseIntelligenceRegistry) -> str:
    release_variant_id = _clean_text(item.get("releaseVariantId"))
    for path_key, summary in registry.summaries_by_path.items():
        if _clean_text(summary.get("releaseVariantId")) == release_variant_id:
            return path_key
    return ""


def _latest_metadata_intelligence_by_path(root_path: str) -> dict[str, dict]:
    runs_dir = Path(root_path).expanduser() / ".musorg" / "runs"
    if not runs_dir.exists():
        return {}

    summaries = sorted(
        [path for path in runs_dir.iterdir() if path.is_file() and path.suffix.lower() == ".json"],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    intelligence_by_path: dict[str, dict] = {}
    for summary_path in summaries:
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for album in payload.get("changed_albums") or []:
            if not isinstance(album, dict):
                continue
            intelligence = album.get("metadata_intelligence")
            if not isinstance(intelligence, dict):
                continue
            for path_key in ("source_dir", "output_dir"):
                album_path = _clean_text(album.get(path_key))
                if not album_path:
                    continue
                normalized_path = str(Path(album_path).expanduser().resolve())
                if normalized_path not in intelligence_by_path:
                    intelligence_by_path[normalized_path] = intelligence
    return intelligence_by_path


def _latest_output_path_by_source(root_path: str) -> dict[str, str]:
    runs_dir = Path(root_path).expanduser() / ".musorg" / "runs"
    if not runs_dir.exists():
        return {}

    summaries = sorted(
        [path for path in runs_dir.iterdir() if path.is_file() and path.suffix.lower() == ".json"],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    output_by_source: dict[str, str] = {}
    for summary_path in summaries:
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for album in payload.get("changed_albums") or []:
            if not isinstance(album, dict):
                continue
            source_dir = _clean_text(album.get("source_dir"))
            output_dir = _clean_text(album.get("output_dir"))
            if not source_dir or not output_dir:
                continue
            normalized_source = str(Path(source_dir).expanduser().resolve())
            normalized_output = str(Path(output_dir).expanduser().resolve())
            if normalized_source not in output_by_source:
                output_by_source[normalized_source] = normalized_output
    return output_by_source


def _runtime_state_by_path(
    root_path: str,
    source_paths: tuple[str, ...],
    *,
    latest_output_paths: dict[str, str] | None = None,
    resolve_runtime_output: bool = True,
) -> dict[str, dict]:
    state_by_path: dict[str, dict] = {}
    output_paths = latest_output_paths if latest_output_paths is not None else _latest_output_path_by_source(root_path)
    for source_path in source_paths:
        resolution = resolve_album_runtime_state(
            root_path,
            source_path,
            latest_output_paths=output_paths,
            resolve_runtime_output=resolve_runtime_output,
        )
        state_by_path[source_path] = {
            "processingState": resolution.processing_state or "idle",
            "outputPath": resolution.output_path,
        }
    return state_by_path


def _is_valid_processed_album(output_path: str, root_path: str) -> bool:
    folder = Path(output_path).expanduser()
    if not folder.is_dir():
        return False
    try:
        detail = load_album_detail(str(folder.resolve()), root_path)
    except Exception:
        return False
    return bool(detail.tracks)
