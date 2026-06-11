from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from musorg.core.stages.grouping import build_album_groups
from musorg.core.stages.metadata_read import source_album_group_key
from musorg.filesystem.scanner import scan_files
from musorg.metadata.normalizer import normalize_lookup_text
from musorg.metadata.parser import read_tags

_ISSUE_WEIGHTS = {
    "unreadable_flac": 15,
    "duplicate_albums": 8,
    "duplicate_tracks": 5,
    "mixed_albumartist": 10,
    "missing_cover_art": 6,
    "missing_date": 4,
    "missing_releasetime": 3,
    "missing_tracknumber": 2,
}
_DUPLICATE_TRACK_DURATION_TOLERANCE_SECONDS = 2.0


@dataclass
class TrackAuditIssue:
    path: str
    albumartist: str
    album: str
    title: str


@dataclass
class AlbumAuditIssue:
    source_dir: str
    album: str
    albumartist: str
    track_count: int
    paths: list[str]


@dataclass
class MixedAlbumArtistIssue:
    source_dir: str
    album: str
    albumartists: list[str]
    track_count: int
    paths: list[str]


@dataclass
class DuplicateAlbumIssue:
    albumartist: str
    album: str
    source_dirs: list[str]
    track_counts: list[int]
    musicbrainz_release_ids: list[str]
    match_signals: list[str]
    paths: list[str]


@dataclass
class DuplicateTrackIssue:
    artist: str
    title: str
    durations_seconds: list[float | None]
    musicbrainz_track_ids: list[str]
    match_signals: list[str]
    paths: list[str]


@dataclass
class AuditReport:
    root_path: str
    files_scanned: int
    readable_tracks: int
    grouped_album_count: int
    source_album_count: int
    unreadable_flac: list[str]
    missing_date: list[TrackAuditIssue]
    missing_releasetime: list[TrackAuditIssue]
    missing_tracknumber: list[TrackAuditIssue]
    missing_cover_art: list[AlbumAuditIssue]
    mixed_albumartist: list[MixedAlbumArtistIssue]
    duplicate_albums: list[DuplicateAlbumIssue]
    duplicate_tracks: list[DuplicateTrackIssue]

    @property
    def albums_checked(self) -> int:
        return self.source_album_count

    @property
    def issue_count(self) -> int:
        return sum(self.issue_counts().values())

    @property
    def health_score(self) -> int:
        penalty = sum(
            self.issue_counts()[name] * _ISSUE_WEIGHTS[name]
            for name in _ISSUE_WEIGHTS
        )
        return max(0, 100 - penalty)

    def issue_counts(self) -> dict[str, int]:
        return {
            "unreadable_flac": len(self.unreadable_flac),
            "missing_date": len(self.missing_date),
            "missing_releasetime": len(self.missing_releasetime),
            "missing_tracknumber": len(self.missing_tracknumber),
            "missing_cover_art": len(self.missing_cover_art),
            "mixed_albumartist": len(self.mixed_albumartist),
            "duplicate_albums": len(self.duplicate_albums),
            "duplicate_tracks": len(self.duplicate_tracks),
        }

    def counts(self) -> dict[str, int]:
        return {
            "files_scanned": self.files_scanned,
            "readable_tracks": self.readable_tracks,
            "grouped_album_count": self.grouped_album_count,
            "source_album_count": self.source_album_count,
            "albums_checked": self.albums_checked,
            "health_score": self.health_score,
            **self.issue_counts(),
        }

    def to_dict(self) -> dict:
        return {
            "library_path": self.root_path,
            "files_scanned": self.files_scanned,
            "readable_tracks": self.readable_tracks,
            "albums_checked": self.albums_checked,
            "issue_counts": self.issue_counts(),
            "health_score": self.health_score,
            "detailed_findings": {
                "unreadable_flac": list(self.unreadable_flac),
                "missing_date": [asdict(item) for item in self.missing_date],
                "missing_releasetime": [asdict(item) for item in self.missing_releasetime],
                "missing_tracknumber": [asdict(item) for item in self.missing_tracknumber],
                "missing_cover_art": [asdict(item) for item in self.missing_cover_art],
                "mixed_albumartist": [asdict(item) for item in self.mixed_albumartist],
                "duplicate_albums": [asdict(item) for item in self.duplicate_albums],
                "duplicate_tracks": [asdict(item) for item in self.duplicate_tracks],
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def health_score_breakdown() -> dict[str, int]:
    return dict(_ISSUE_WEIGHTS)


def _format_track_issue(issue: TrackAuditIssue) -> str:
    return f"- {issue.path}: {issue.albumartist} - {issue.album} - {issue.title}"


def _format_album_issue(issue: AlbumAuditIssue) -> str:
    return f"- {issue.source_dir}: {issue.albumartist} - {issue.album} ({issue.track_count} tracks)"


def _format_mixed_albumartist_issue(issue: MixedAlbumArtistIssue) -> str:
    return f"- {issue.source_dir}: {issue.album} [{', '.join(issue.albumartists)}]"


def _format_duplicate_album_issue(issue: DuplicateAlbumIssue) -> str:
    return (
        f"- {issue.albumartist} - {issue.album}: "
        f"{len(issue.source_dirs)} copies across {', '.join(issue.source_dirs)} "
        f"[signals: {', '.join(issue.match_signals)}]"
    )


def _format_duplicate_track_issue(issue: DuplicateTrackIssue) -> str:
    return (
        f"- {issue.artist} - {issue.title}: "
        f"{len(issue.paths)} copies across {', '.join(issue.paths)} "
        f"[signals: {', '.join(issue.match_signals)}]"
    )


def format_audit_summary(report: AuditReport, verbose: bool = False) -> str:
    counts = report.counts()
    lines = [
        f"Audit summary for {report.root_path}",
        f"Files scanned: {counts['files_scanned']}",
        f"Readable tracks: {counts['readable_tracks']}",
        f"Albums checked: {counts['source_album_count']}",
        f"Health score: {report.health_score}/100",
        "",
        "Findings:",
        f"- Missing DATE: {counts['missing_date']}",
        f"- Missing RELEASETIME: {counts['missing_releasetime']}",
        f"- Missing TRACKNUMBER: {counts['missing_tracknumber']}",
        f"- Missing cover art: {counts['missing_cover_art']}",
        f"- Mixed ALBUMARTIST: {counts['mixed_albumartist']}",
        f"- Duplicate albums: {counts['duplicate_albums']}",
        f"- Duplicate tracks: {counts['duplicate_tracks']}",
        f"- Broken/unreadable FLAC: {counts['unreadable_flac']}",
    ]

    if verbose:
        issue_sections = [
            ("Tracks missing DATE:", [_format_track_issue(issue) for issue in report.missing_date]),
            ("Tracks missing RELEASETIME:", [_format_track_issue(issue) for issue in report.missing_releasetime]),
            ("Tracks missing TRACKNUMBER:", [_format_track_issue(issue) for issue in report.missing_tracknumber]),
            ("Broken/unreadable FLAC files:", [f"- {path}" for path in report.unreadable_flac]),
            ("Albums with mixed ALBUMARTIST:", [_format_mixed_albumartist_issue(issue) for issue in report.mixed_albumartist]),
            ("Albums missing cover art:", [_format_album_issue(issue) for issue in report.missing_cover_art]),
            ("Duplicate albums:", [_format_duplicate_album_issue(issue) for issue in report.duplicate_albums]),
            ("Duplicate tracks:", [_format_duplicate_track_issue(issue) for issue in report.duplicate_tracks]),
        ]
        for heading, entries in issue_sections:
            if not entries:
                continue
            lines.extend(["", heading, *entries])
        return "\n".join(lines)

    if report.unreadable_flac:
        lines.extend(["", "Broken/unreadable FLAC files:"])
        lines.extend(f"- {path}" for path in report.unreadable_flac)

    if report.mixed_albumartist:
        lines.extend(["", "Albums with mixed ALBUMARTIST:"])
        lines.extend(
            f"- {issue.source_dir}: {', '.join(issue.albumartists)}"
            for issue in report.mixed_albumartist
        )

    if report.missing_cover_art:
        lines.extend(["", "Albums missing cover art:"])
        lines.extend(
            f"- {issue.source_dir}: {issue.albumartist} - {issue.album}"
            for issue in report.missing_cover_art
        )

    if report.duplicate_albums:
        lines.extend(["", "Duplicate albums:"])
        lines.extend(
            f"- {issue.albumartist} - {issue.album}: {len(issue.source_dirs)} copies"
            for issue in report.duplicate_albums
        )

    if report.duplicate_tracks:
        lines.extend(["", "Duplicate tracks:"])
        lines.extend(
            f"- {issue.artist} - {issue.title}: {len(issue.paths)} copies"
            for issue in report.duplicate_tracks
        )

    return "\n".join(lines)


def _track_issue(track: dict) -> TrackAuditIssue:
    return TrackAuditIssue(
        path=track.get("path", ""),
        albumartist=track.get("albumartist", "Unknown"),
        album=track.get("album", "Unknown"),
        title=track.get("title", "Unknown"),
    )


def _album_issue(group_tracks: list[dict]) -> AlbumAuditIssue:
    first_track = group_tracks[0]
    return AlbumAuditIssue(
        source_dir=str(Path(first_track.get("path", "")).parent),
        album=first_track.get("album", "Unknown"),
        albumartist=first_track.get("albumartist", "Unknown"),
        track_count=len(group_tracks),
        paths=sorted(track.get("path", "") for track in group_tracks),
    )


def _mixed_albumartist_issue(group_tracks: list[dict]) -> MixedAlbumArtistIssue:
    first_track = group_tracks[0]
    albumartists = []
    seen_keys = set()

    for track in group_tracks:
        albumartist = (track.get("albumartist") or "Unknown").strip() or "Unknown"
        normalized = normalize_lookup_text(albumartist)
        if normalized in seen_keys:
            continue
        seen_keys.add(normalized)
        albumartists.append(albumartist)

    return MixedAlbumArtistIssue(
        source_dir=str(Path(first_track.get("path", "")).parent),
        album=first_track.get("album", "Unknown"),
        albumartists=albumartists,
        track_count=len(group_tracks),
        paths=sorted(track.get("path", "") for track in group_tracks),
    )


def _group_tracks_by_source_album(tracks: list[dict]) -> dict[tuple[str, str], list[dict]]:
    grouped_tracks = {}
    for track in tracks:
        grouped_tracks.setdefault(source_album_group_key(track), []).append(track)
    return grouped_tracks


def _normalized_track_identity(track: dict) -> tuple[str, str]:
    artist = normalize_lookup_text(track.get("artist") or "Unknown")
    title = normalize_lookup_text(track.get("title") or "Unknown")
    return artist, title


def _track_musicbrainz_id(track: dict) -> str:
    return str(track.get("musicbrainz_track_id") or "").strip()


def _track_duration_seconds(track: dict) -> float | None:
    value = track.get("duration_seconds")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_album_identity(group_tracks: list[dict]) -> tuple[str, str]:
    first_track = group_tracks[0]
    albumartist = normalize_lookup_text(first_track.get("albumartist") or first_track.get("artist") or "Unknown")
    album = normalize_lookup_text(first_track.get("album") or "Unknown")
    return albumartist, album


def _group_musicbrainz_release_ids(group_tracks: list[dict]) -> set[str]:
    return {
        str(track.get("musicbrainz_release_id") or "").strip()
        for track in group_tracks
        if str(track.get("musicbrainz_release_id") or "").strip()
    }


def _duplicate_album_issue(source_album_groups: list[list[dict]], match_signals: set[str]) -> DuplicateAlbumIssue:
    first_track = source_album_groups[0][0]
    source_dirs = sorted(str(Path(group_tracks[0].get("path", "")).parent) for group_tracks in source_album_groups)
    musicbrainz_release_ids = sorted({
        release_id
        for group_tracks in source_album_groups
        for release_id in _group_musicbrainz_release_ids(group_tracks)
    })
    track_counts = [len(group_tracks) for group_tracks in source_album_groups]
    paths = sorted(
        track.get("path", "")
        for group_tracks in source_album_groups
        for track in group_tracks
    )
    return DuplicateAlbumIssue(
        albumartist=first_track.get("albumartist") or first_track.get("artist") or "Unknown",
        album=first_track.get("album", "Unknown"),
        source_dirs=source_dirs,
        track_counts=track_counts,
        musicbrainz_release_ids=musicbrainz_release_ids,
        match_signals=sorted(match_signals),
        paths=paths,
    )


def detect_duplicate_albums(source_album_groups: dict[tuple[str, str], list[dict]]) -> list[DuplicateAlbumIssue]:
    candidate_groups = list(source_album_groups.values())
    duplicates = []
    consumed_group_ids = set()

    release_id_buckets = {}
    identity_buckets = {}

    for group_tracks in candidate_groups:
        group_id = id(group_tracks)
        release_ids = _group_musicbrainz_release_ids(group_tracks)
        for release_id in release_ids:
            release_id_buckets.setdefault(release_id, []).append(group_tracks)

        identity_buckets.setdefault(_normalized_album_identity(group_tracks), []).append(group_tracks)

    for release_id, grouped_tracks in release_id_buckets.items():
        if len(grouped_tracks) < 2:
            continue
        duplicates.append(_duplicate_album_issue(grouped_tracks, {"musicbrainz_release_id"}))
        consumed_group_ids.update(id(group_tracks) for group_tracks in grouped_tracks)

    for grouped_tracks in identity_buckets.values():
        unresolved_groups = [group_tracks for group_tracks in grouped_tracks if id(group_tracks) not in consumed_group_ids]
        if len(unresolved_groups) < 2:
            continue

        track_counts = {len(group_tracks) for group_tracks in unresolved_groups}
        signals = {"normalized_artist_album"}
        if len(track_counts) == 1:
            signals.add("matching_track_count")

        duplicates.append(_duplicate_album_issue(unresolved_groups, signals))
        consumed_group_ids.update(id(group_tracks) for group_tracks in unresolved_groups)

    duplicates.sort(key=lambda issue: (normalize_lookup_text(issue.albumartist), normalize_lookup_text(issue.album), issue.source_dirs))
    return duplicates


def _duplicate_track_issue(tracks: list[dict], match_signals: set[str]) -> DuplicateTrackIssue:
    first_track = tracks[0]
    musicbrainz_track_ids = sorted({
        track_id
        for track_id in (_track_musicbrainz_id(track) for track in tracks)
        if track_id
    })
    durations_seconds = [_track_duration_seconds(track) for track in tracks]
    return DuplicateTrackIssue(
        artist=first_track.get("artist", "Unknown"),
        title=first_track.get("title", "Unknown"),
        durations_seconds=durations_seconds,
        musicbrainz_track_ids=musicbrainz_track_ids,
        match_signals=sorted(match_signals),
        paths=sorted(track.get("path", "") for track in tracks),
    )


def detect_duplicate_tracks(tracks: list[dict]) -> list[DuplicateTrackIssue]:
    identity_buckets = {}
    for track in tracks:
        identity_buckets.setdefault(_normalized_track_identity(track), []).append(track)

    duplicates = []
    for bucket_tracks in identity_buckets.values():
        if len(bucket_tracks) < 2:
            continue

        grouped_by_track_id = {}
        no_track_id = []
        for track in bucket_tracks:
            track_id = _track_musicbrainz_id(track)
            if track_id:
                grouped_by_track_id.setdefault(track_id, []).append(track)
            else:
                no_track_id.append(track)

        for grouped_tracks in grouped_by_track_id.values():
            if len(grouped_tracks) >= 2:
                duplicates.append(_duplicate_track_issue(grouped_tracks, {"musicbrainz_track_id"}))

        sorted_no_track_id = sorted(
            no_track_id,
            key=lambda track: (_track_duration_seconds(track) is None, _track_duration_seconds(track) or 0.0, track.get("path", "")),
        )
        current_group = []
        current_min = None
        current_max = None
        for track in sorted_no_track_id:
            duration = _track_duration_seconds(track)
            if duration is None:
                if len(current_group) >= 2:
                    duplicates.append(_duplicate_track_issue(current_group, {"artist_title", "duration_tolerance"}))
                current_group = [track]
                current_min = None
                current_max = None
                continue

            if not current_group:
                current_group = [track]
                current_min = duration
                current_max = duration
                continue

            if current_min is not None and current_max is not None and duration - current_min <= _DUPLICATE_TRACK_DURATION_TOLERANCE_SECONDS and max(current_max, duration) - min(current_min, duration) <= _DUPLICATE_TRACK_DURATION_TOLERANCE_SECONDS:
                current_group.append(track)
                current_min = min(current_min, duration)
                current_max = max(current_max, duration)
            else:
                if len(current_group) >= 2 and current_min is not None:
                    duplicates.append(_duplicate_track_issue(current_group, {"artist_title", "duration_tolerance"}))
                current_group = [track]
                current_min = duration
                current_max = duration

        if len(current_group) >= 2 and current_min is not None:
            duplicates.append(_duplicate_track_issue(current_group, {"artist_title", "duration_tolerance"}))

    duplicates.sort(key=lambda issue: (normalize_lookup_text(issue.artist), normalize_lookup_text(issue.title), issue.paths))
    return duplicates


def audit_library(root_path: str) -> AuditReport:
    files = scan_files(root_path)
    readable_tracks = []
    unreadable_flac = []
    missing_date = []
    missing_releasetime = []
    missing_tracknumber = []

    for file_path in files:
        tags = read_tags(file_path)
        if tags is None:
            if file_path.lower().endswith(".flac"):
                unreadable_flac.append(file_path)
            continue

        readable_tracks.append(tags)

        if not tags.get("has_date_tag"):
            missing_date.append(_track_issue(tags))
        if not tags.get("has_releasetime_tag"):
            missing_releasetime.append(_track_issue(tags))
        if not tags.get("has_tracknumber_tag"):
            missing_tracknumber.append(_track_issue(tags))

    grouped_albums = build_album_groups(readable_tracks)
    source_album_groups = _group_tracks_by_source_album(readable_tracks)
    missing_cover_art = []
    mixed_albumartist = []

    for group_tracks in source_album_groups.values():
        if not group_tracks:
            continue

        if not any(track.get("has_cover_art") for track in group_tracks):
            missing_cover_art.append(_album_issue(group_tracks))

        unique_albumartists = {
            normalize_lookup_text((track.get("albumartist") or "Unknown").strip() or "Unknown")
            for track in group_tracks
        }
        if len(unique_albumartists) > 1:
            mixed_albumartist.append(_mixed_albumartist_issue(group_tracks))

    duplicate_albums = detect_duplicate_albums(source_album_groups)
    duplicate_tracks = detect_duplicate_tracks(readable_tracks)

    return AuditReport(
        root_path=root_path,
        files_scanned=len(files),
        readable_tracks=len(readable_tracks),
        grouped_album_count=len(grouped_albums),
        source_album_count=len(source_album_groups),
        unreadable_flac=sorted(unreadable_flac),
        missing_date=missing_date,
        missing_releasetime=missing_releasetime,
        missing_tracknumber=missing_tracknumber,
        missing_cover_art=missing_cover_art,
        mixed_albumartist=mixed_albumartist,
        duplicate_albums=duplicate_albums,
        duplicate_tracks=duplicate_tracks,
    )
