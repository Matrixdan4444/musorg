from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re

from musorg.core.cover_art import load_album_cover_bytes
from musorg.filesystem.scanner import SUPPORTED_FORMATS
from musorg.metadata.parser import read_tags
from musorg.utils.artist_text import first_known_artist, known_artist


_PLACEHOLDER_ARTIST = "Placeholder Artist"


@dataclass(frozen=True)
class AlbumPreview:
    album_title: str
    artist_name: str
    track_count: int
    folder_path: str
    status: str
    issues: tuple[str, ...] = ()
    release_year: str = ""


@dataclass(frozen=True)
class TrackPreview:
    track_number: str
    track_title: str
    duration_text: str
    status: str
    artist_name: str = ""
    issue_count: int = 0


@dataclass(frozen=True)
class AlbumDetail:
    album_title: str
    artist_name: str
    folder_path: str
    status: str
    tracks: list[TrackPreview]
    album_artist: str = ""
    release_year: str = ""
    genre: str = ""
    disc_number: str = ""
    issues: tuple[str, ...] = ()


def scan_album_previews(folder_path: str) -> list[AlbumPreview]:
    root = Path(folder_path).expanduser()
    if not root.exists() or not root.is_dir():
        return []

    previews: list[AlbumPreview] = []
    seen_paths: set[Path] = set()

    for current_path, dirnames, filenames in root.walk():
        dirnames[:] = [
            entry_name
            for entry_name in dirnames
            if not entry_name.endswith("_organized")
            and not entry_name.startswith(".")
            and entry_name != ".musorg"
        ]
        if any(part.startswith(".") for part in current_path.relative_to(root).parts):
            continue
        audio_files = sorted(
            current_path / file_name
            for file_name in filenames
            if Path(file_name).suffix.lower() in SUPPORTED_FORMATS
        )
        if not audio_files or current_path in seen_paths:
            continue
        seen_paths.add(current_path)
        previews.append(_build_album_preview(root, current_path, audio_files))

    previews.sort(key=lambda item: (_sort_artist(item.artist_name), item.album_title.lower(), item.folder_path.lower()))
    return previews


def load_album_detail(folder_path: str, root_path: str | None = None) -> AlbumDetail:
    folder = Path(folder_path).expanduser()
    root = Path(root_path).expanduser() if root_path else folder.parent
    if not folder.exists() or not folder.is_dir():
        fallback_title = folder.name or "Unknown Album"
        fallback_artist = _sanitize_artist(folder.parent.name) if folder.parent != folder else "Unknown artist"
        return AlbumDetail(
            album_title=fallback_title,
            artist_name=fallback_artist or "Unknown artist",
            folder_path=str(folder),
            status="Needs Fix",
            tracks=[],
            album_artist=fallback_artist or "Unknown artist",
            release_year="",
            genre="",
            disc_number="",
            issues=("missing_track_numbers",),
        )
    try:
        flac_paths = sorted(
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS
        )
    except OSError:
        fallback_title = folder.name or "Unknown Album"
        fallback_artist = _sanitize_artist(folder.parent.name) if folder.parent != folder else "Unknown artist"
        return AlbumDetail(
            album_title=fallback_title,
            artist_name=fallback_artist or "Unknown artist",
            folder_path=str(folder),
            status="Needs Fix",
            tracks=[],
            album_artist=fallback_artist or "Unknown artist",
            release_year="",
            genre="",
            disc_number="",
            issues=("missing_track_numbers",),
        )
    tags_by_path = _read_tags_map(flac_paths)
    preview = _build_album_preview(root, folder, flac_paths, tags_by_path)
    tracks = [
        _build_track_preview(file_path, index + 1, tags_by_path.get(str(file_path)))
        for index, file_path in enumerate(flac_paths)
    ]
    tracks.sort(key=lambda item: (_track_sort_key(item.track_number), item.track_title.lower()))
    metadata = _album_metadata(flac_paths, tags_by_path)
    return AlbumDetail(
        album_title=preview.album_title,
        artist_name=preview.artist_name,
        folder_path=preview.folder_path,
        status=preview.status,
        tracks=tracks,
        album_artist=metadata["album_artist"],
        release_year=metadata["release_year"],
        genre=metadata["genre"],
        disc_number=metadata["disc_number"],
        issues=preview.issues,
    )


def simulate_fixed_album_preview(preview: AlbumPreview) -> AlbumPreview:
    artist_name = preview.artist_name
    if "unknown_artist" in preview.issues and artist_name == "Unknown artist":
        artist_name = _PLACEHOLDER_ARTIST
    return replace(preview, artist_name=artist_name, status="Ready", issues=())


def simulate_fixed_album_detail(detail: AlbumDetail) -> AlbumDetail:
    artist_name = detail.artist_name
    if "unknown_artist" in detail.issues and artist_name == "Unknown artist":
        artist_name = _PLACEHOLDER_ARTIST
    fixed_tracks = [replace(track, status="OK") for track in detail.tracks]
    return replace(detail, artist_name=artist_name, status="Ready", tracks=fixed_tracks, issues=())


def issue_labels(issues: tuple[str, ...]) -> list[str]:
    labels = {
        "missing_cover": "Missing cover",
        "unknown_artist": "Unknown artist",
        "missing_release_date": "Missing release date",
        "missing_track_numbers": "Missing track numbers",
        "album_artist_inconsistency": "Album artist mismatch",
    }
    return [labels[issue] for issue in issues if issue in labels]


def _read_tags_map(flac_paths: list[Path]) -> dict[str, dict | None]:
    """Read tags for each file exactly once, keyed by string path.

    Preview building is a read-only view over a stable folder snapshot, so the
    same tags are reused across album-, track-, and issue-level computations
    instead of reopening each file multiple times.
    """
    return {str(path): read_tags(str(path)) for path in flac_paths}


def _album_title_from_tags(tags_by_path: dict[str, dict | None], fallback: str) -> str:
    """Prefer the album tag (most common across the folder) over the folder name.

    The folder is often named "Year - Album" or "Artist - Album", so the embedded
    album tag is the truthful title to show. Falls back to the folder name when no
    usable album tag is present.
    """
    counts: dict[str, int] = {}
    for tags in tags_by_path.values():
        if not tags:
            continue
        value = str(tags.get("album") or "").strip()
        if not value or value == "Unknown":
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return fallback
    return max(counts, key=lambda name: (counts[name], name))


def _album_release_year(tags_by_path: dict[str, dict | None]) -> str:
    """First usable release year across the folder (same logic as the detail)."""
    for tags in tags_by_path.values():
        if not tags:
            continue
        year = _release_year_from_tags(tags)
        if year:
            return year
    return ""


def _build_album_preview(
    root: Path,
    folder: Path,
    flac_paths: list[Path],
    tags_by_path: dict[str, dict | None] | None = None,
) -> AlbumPreview:
    if tags_by_path is None:
        tags_by_path = _read_tags_map(flac_paths)
    album_title = _album_title_from_tags(tags_by_path, folder.name or "Unknown Album")
    release_year = _album_release_year(tags_by_path)
    relative_parts = folder.relative_to(root).parts if folder.is_relative_to(root) else folder.parts
    raw_artist_name = relative_parts[-2] if len(relative_parts) >= 2 else "Unknown artist"
    folder_artist = _sanitize_artist(raw_artist_name)
    tag_artist = _album_primary_artist(flac_paths, tags_by_path)
    artist_name = first_known_artist(folder_artist, fallback="Unknown artist") or "Unknown artist"
    if known_artist(artist_name) is None and tag_artist:
        artist_name = tag_artist
    issues = _album_issues(folder, flac_paths, artist_name, tags_by_path)
    return AlbumPreview(
        album_title=album_title,
        artist_name=artist_name or "Unknown artist",
        track_count=len(flac_paths),
        folder_path=str(folder),
        status="Ready" if not issues else "Needs Fix",
        issues=issues,
        release_year=release_year,
    )


def _album_issues(
    folder: Path,
    flac_paths: list[Path],
    detected_artist: str,
    tags_by_path: dict[str, dict | None],
) -> tuple[str, ...]:
    issues: list[str] = []
    if not flac_paths:
        return ("missing_track_numbers",)

    album_artists: set[str] = set()
    missing_release_date = False
    missing_track_numbers = False
    unknown_artist = known_artist(detected_artist) is None

    for file_path in flac_paths:
        tags = tags_by_path.get(str(file_path))
        if not tags:
            missing_release_date = True
            missing_track_numbers = True
            unknown_artist = True
            continue

        track_artist = known_artist(tags.get("trackartist")) or known_artist(tags.get("artist"))
        album_artist = known_artist(tags.get("albumartist"))
        if not track_artist and not album_artist:
            unknown_artist = True
        if not tags.get("has_tracknumber_tag") or str(tags.get("tracknumber") or "").strip() in ("", "0"):
            missing_track_numbers = True
        if not _has_normalized_release_date(tags):
            missing_release_date = True
        artist_value = album_artist or track_artist
        if artist_value:
            album_artists.add(artist_value)

    if not _album_has_cover(folder):
        issues.append("missing_cover")
    if unknown_artist:
        issues.append("unknown_artist")
    if missing_release_date:
        issues.append("missing_release_date")
    if missing_track_numbers:
        issues.append("missing_track_numbers")
    if len(album_artists) > 1:
        issues.append("album_artist_inconsistency")
    return tuple(issues)


def _build_track_preview(file_path: Path, fallback_number: int, tags: dict | None) -> TrackPreview:
    fallback_title = _fallback_track_title(file_path.stem)
    if not tags:
        return TrackPreview(
            track_number=str(fallback_number),
            track_title=fallback_title,
            duration_text="",
            status="Missing metadata",
            artist_name="Unknown artist",
            issue_count=1,
        )

    track_number = _format_track_number(tags.get("tracknumber"), fallback_number)
    metadata_title = str(tags.get("title") or "").strip()
    title = metadata_title if metadata_title and metadata_title != "Unknown" else fallback_title
    duration_text = _format_duration(tags.get("duration_seconds"))
    artist_name = first_known_artist(tags.get("trackartist"), tags.get("artist"))
    has_missing_metadata = (
        not tags.get("has_tracknumber_tag")
        or metadata_title in ("", "Unknown")
        or not artist_name
    )
    return TrackPreview(
        track_number=track_number,
        track_title=title,
        duration_text=duration_text,
        status="Missing metadata" if has_missing_metadata else "OK",
        artist_name=artist_name or "Unknown artist",
        issue_count=1 if has_missing_metadata else 0,
    )


def _album_metadata(flac_paths: list[Path], tags_by_path: dict[str, dict | None]) -> dict[str, str]:
    album_artist = ""
    release_year = ""
    genre = ""
    max_disc = 0

    for file_path in flac_paths:
        tags = tags_by_path.get(str(file_path))
        if not tags:
            continue

        if not album_artist:
            album_artist = first_known_artist(tags.get("albumartist"), tags.get("trackartist"), tags.get("artist"), fallback="") or ""

        if not release_year:
            release_year = _release_year_from_tags(tags)

        if not genre:
            genre = str(tags.get("genre") or "").strip()

        disc_text = str(tags.get("discnumber") or "").strip().split("/", maxsplit=1)[0]
        if disc_text.isdigit():
            max_disc = max(max_disc, int(disc_text))

    return {
        "album_artist": album_artist or "Unknown artist",
        "release_year": release_year,
        "genre": genre,
        "disc_number": str(max_disc) if max_disc else "",
    }


def _album_primary_artist(flac_paths: list[Path], tags_by_path: dict[str, dict | None]) -> str | None:
    for file_path in flac_paths:
        tags = tags_by_path.get(str(file_path))
        if not tags:
            continue
        artist = first_known_artist(tags.get("albumartist"), tags.get("trackartist"), tags.get("artist"))
        if artist:
            return artist
    return None


def _release_year_from_tags(tags: dict) -> str:
    release_date_iso = str(tags.get("release_date_iso") or "").strip()
    if re.match(r"^\d{4}", release_date_iso):
        return release_date_iso[:4]

    date = str(tags.get("date") or "").strip()
    if re.match(r"^\d{4}$", date):
        return date
    if re.match(r"^\d{2}-\d{2}-\d{4}$", date):
        return date[-4:]
    return ""


def _has_normalized_release_date(tags: dict) -> bool:
    release_date_iso = str(tags.get("release_date_iso") or "").strip()
    date = str(tags.get("date") or "").strip()
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", release_date_iso) or re.match(r"^\d{4}$", date))


def _album_has_cover(folder: Path) -> bool:
    return load_album_cover_bytes(str(folder)) is not None


def _format_track_number(value: object, fallback_number: int) -> str:
    text = str(value or "").strip()
    if not text or text == "0":
        return str(fallback_number)
    text = text.split("/", maxsplit=1)[0].strip()
    return text or str(fallback_number)


def _format_duration(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        total_seconds = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _fallback_track_title(stem: str) -> str:
    cleaned = re.sub(r"^\d+\s*[-._ ]\s*", "", stem).strip()
    return cleaned or stem or "Unknown Track"


def _track_sort_key(value: str) -> tuple[int, str]:
    if value.isdigit():
        return (0, f"{int(value):04d}")
    return (1, value)


def _sort_artist(artist_name: str) -> str:
    if artist_name == "Unknown artist":
        return "~unknown"
    return artist_name.lower()


def _sanitize_artist(value: str) -> str:
    if not value:
        return "Unknown artist"
    value = value.strip()
    if re.match(r"^\d{8}T\d{6}Z-[a-f0-9]+$", value):
        return "Unknown artist"
    return value
