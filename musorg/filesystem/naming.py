import os
import re
import unicodedata
from dataclasses import dataclass

from musorg.metadata.normalizer import (
    canonical_artist_name,
    primary_artist,
    strip_feature_suffix,
)


SINGLES_ALBUM_TITLE = "Singles"
_FOUR_DIGIT_YEAR_RE = re.compile(r"^\d{4}$")
_DISPLAY_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_CUSTOM_ALBUM_PATTERN = ["artist", "folder_break", "year", "album"]
DEFAULT_FILENAME_COMPATIBILITY = "preserve_original"


@dataclass(frozen=True)
class OutputDestination:
    album_root: str
    file_path: str
    folder_segments: list[str]
    disc_folder: str | None
    filename: str


def normalize_filesystem_text(value: str | None) -> str:
    if value is None:
        return ""

    return unicodedata.normalize("NFC", str(value))


def normalize_filesystem_path(path: str | None) -> str:
    normalized = normalize_filesystem_text(path)
    if not normalized:
        return ""

    return os.path.normpath(normalized)


def filesystem_path_key(path: str | None) -> str:
    normalized_path = normalize_filesystem_path(path)
    if not normalized_path:
        return ""

    return os.path.normcase(normalized_path)


def normalize_lookup_text(value: str | None) -> str:
    if not value:
        return ""

    decomposed = unicodedata.normalize("NFKD", value)
    chars = []
    for char in decomposed.lower():
        if unicodedata.combining(char):
            continue
        chars.append(char if char.isalnum() else " ")

    return " ".join("".join(chars).split())


def filesystem_safe_name(value: str) -> str:
    return filesystem_safe_name_for_mode(value, DEFAULT_FILENAME_COMPATIBILITY)


def normalize_filename_compatibility_settings(value: object | None) -> str:
    if value in {"preserve_original", "cross_platform_safe"}:
        return str(value)
    return DEFAULT_FILENAME_COMPATIBILITY


def filename_compatibility_settings_to_api(value: object | None) -> str:
    return normalize_filename_compatibility_settings(value)


def filesystem_safe_name_for_mode(value: str, compatibility_mode: str | None = None) -> str:
    if not value:
        return "Unknown"

    compatibility = normalize_filename_compatibility_settings(compatibility_mode)
    stripped = normalize_filesystem_text(value).strip()
    stem, extension = os.path.splitext(stripped)
    if compatibility == "cross_platform_safe":
        stem = _cross_platform_safe_text(stem)

    translated = (
        stem
        .replace("/", "／" if compatibility == "preserve_original" else "_")
        .replace("\\", "＼" if compatibility == "preserve_original" else "_")
        .replace(":", "." if compatibility == "preserve_original" else "_")
    )
    translated = re.sub(r"\s*([／＼])\s*", r"\1", translated)
    translated = re.sub(r"\s*\.\s*", ". ", translated)
    translated = re.sub(r'["*?<>|]+', "_", translated)
    translated = translated.replace("\0", "")
    translated = re.sub(r"\s+", " ", translated).strip()
    translated = re.sub(r"_+", "_", translated)
    safe_stem = translated or "Unknown"
    return normalize_filesystem_text(f"{safe_stem}{extension}")


def _cross_platform_safe_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    chars: list[str] = []
    for char in decomposed:
        if unicodedata.combining(char):
            continue
        chars.append(char)
    return "".join(chars)


def extract_year(value: str | None) -> str:
    if not value:
        return "0000"

    cleaned = value.strip()
    if _FOUR_DIGIT_YEAR_RE.match(cleaned):
        return cleaned

    if _DISPLAY_DATE_RE.match(cleaned):
        return cleaned[-4:]

    if _ISO_DATE_RE.match(cleaned):
        return cleaned[:4]

    return cleaned[-4:] if len(cleaned) >= 4 else "0000"


_DUPLICATE_LEADING_YEAR_RE = re.compile(r"^(\d{4})(\s*[-–—_.]\s*)\1((?:[\s\-–—_.].*)?)$")


def collapse_duplicate_leading_year(segment: str) -> str:
    """Collapse an immediately repeated leading 4-digit year in a folder segment.

    Prevents "2024 - 2024 - Album" when the album title already begins with the
    release year. Only triggers when the exact same year appears twice in a row
    at the very start, so titles like "1984" or "1989 (2014)" are left untouched.
    """
    match = _DUPLICATE_LEADING_YEAR_RE.match(segment.strip())
    if not match:
        return segment
    return f"{match.group(1)}{match.group(3)}".strip()


def preferred_folder_artist(album_artist: str | None, track_artist: str | None) -> str:
    if album_artist:
        return canonical_artist_name(primary_artist(album_artist)) or primary_artist(album_artist)

    resolved_artist = primary_artist(track_artist or "Unknown")
    return canonical_artist_name(resolved_artist) or resolved_artist


def resolved_track_title(track: dict) -> str:
    title = track.get("title")
    if title and title.lower() != "unknown":
        return strip_feature_suffix(title)

    filename_only = os.path.splitext(os.path.basename(track["path"]))[0]
    parts = filename_only.split(" ", 1)
    if parts and parts[0].replace(".", "").isdigit() and len(parts) > 1:
        return parts[1]

    return filename_only


def resolved_track_number(track: dict) -> int:
    track_number = track.get("tracknumber", 0)
    if track_number and track_number != 0:
        return track_number

    filename_only = os.path.splitext(os.path.basename(track["path"]))[0]
    parts = filename_only.split(" ", 1)
    if parts and parts[0].replace(".", "").isdigit():
        return int(parts[0].replace(".", ""))

    return 0


def is_single_release(track: dict) -> bool:
    return normalize_lookup_text(track.get("releasetype")) == "single"


def single_release_group_key(track: dict) -> tuple[str, str, str]:
    return (
        normalize_lookup_text(track.get("albumartist") or track.get("artist") or ""),
        normalize_lookup_text(track.get("album") or ""),
        (track.get("release_date_iso") or track.get("date") or "").strip(),
    )


def is_standalone_single(track: dict, group_size: int) -> bool:
    normalized_release_type = normalize_lookup_text(track.get("releasetype"))

    if normalized_release_type == "ep":
        return False

    if is_single_release(track):
        release_track_count = int(track.get("release_track_count") or 0)
        known_track_count = release_track_count or group_size
        if known_track_count <= 3:
            return True
        return False

    if group_size != 1:
        return False

    album = normalize_lookup_text(track.get("album") or "")
    title = normalize_lookup_text(resolved_track_title(track))
    return bool(album and title and album == title)


def parse_sort_date_value(track: dict) -> tuple[int, int, int]:
    release_date_iso = (track.get("release_date_iso") or "").strip()
    if _ISO_DATE_RE.match(release_date_iso):
        year, month, day = release_date_iso.split("-")
        return int(year), int(month), int(day)

    display_date = (track.get("date") or "").strip()
    if _DISPLAY_DATE_RE.match(display_date):
        day, month, year = display_date.split("-")
        return int(year), int(month), int(day)

    if _FOUR_DIGIT_YEAR_RE.match(display_date):
        return int(display_date), 1, 1

    return 0, 1, 1


def single_track_identity(track: dict) -> tuple[str, str, str, int]:
    return (
        normalize_lookup_text(track.get("albumartist") or track.get("artist") or ""),
        normalize_lookup_text(resolved_track_title(track)),
        (track.get("release_date_iso") or track.get("date") or "").strip(),
        int(track.get("singleoriginaltracknumber") or resolved_track_number(track) or 0),
    )


def album_folder_title(folder_name: str) -> str:
    folder_name = normalize_filesystem_text(folder_name)
    if " - " not in folder_name:
        if folder_name.endswith(")") and " (" in folder_name:
            title, _year = folder_name.rsplit(" (", 1)
            return title
        return folder_name

    _year, title = folder_name.split(" - ", 1)
    return title


def default_output_format_settings() -> dict[str, object]:
    return {
        "album_folder_preset": "artist_year_album",
        "disc_handling": "keep_together",
        "file_naming": "track_title",
        "separator_style": "dot",
        "custom_album_pattern": list(DEFAULT_CUSTOM_ALBUM_PATTERN),
        "custom_advanced_template": None,
    }


def normalize_output_format_settings(settings: dict | None) -> dict[str, object]:
    merged = dict(default_output_format_settings())
    if not isinstance(settings, dict):
        return merged

    def _pick(*keys: str):
        for key in keys:
            if key in settings and settings[key] not in (None, ""):
                return settings[key]
        return None

    album_folder_preset = _pick("album_folder_preset", "albumFolderPreset")
    if album_folder_preset in {"artist_year_album", "artist_album_year", "artist_album", "genre_artist_album", "custom"}:
        merged["album_folder_preset"] = album_folder_preset

    disc_handling = _pick("disc_handling", "discHandling")
    if disc_handling in {"keep_together", "flatten", "prefix_disc"}:
        merged["disc_handling"] = disc_handling

    file_naming = _pick("file_naming", "fileNaming")
    if file_naming in {"track_title", "artist_title", "track_artist_title", "title_only"}:
        merged["file_naming"] = file_naming

    separator_style = _pick("separator_style", "separatorStyle")
    if separator_style in {"hyphen", "dot", "space", "minimal"}:
        merged["separator_style"] = separator_style

    custom_album_pattern = _pick("custom_album_pattern", "customAlbumPattern")
    if isinstance(custom_album_pattern, list) and custom_album_pattern:
        merged["custom_album_pattern"] = [str(item) for item in custom_album_pattern if str(item).strip()]

    custom_advanced_template = _pick("custom_advanced_template", "customAdvancedTemplate")
    if custom_advanced_template is not None:
        merged["custom_advanced_template"] = str(custom_advanced_template)

    return merged


def output_format_settings_to_api(settings: dict | None) -> dict[str, object]:
    normalized = normalize_output_format_settings(settings)
    return {
        "albumFolderPreset": normalized["album_folder_preset"],
        "discHandling": normalized["disc_handling"],
        "fileNaming": normalized["file_naming"],
        "separatorStyle": normalized["separator_style"],
        "customAlbumPattern": list(normalized["custom_album_pattern"]),
        "customAdvancedTemplate": normalized["custom_advanced_template"],
    }


def format_output_destination(track: dict, root_output: str, settings: dict | None = None) -> OutputDestination:
    normalized = normalize_output_format_settings(settings)
    compatibility = normalize_filename_compatibility_settings(track.get("_filename_compatibility"))
    folder_segments = _album_folder_segments(track, normalized)
    album_root = normalize_filesystem_path(
        os.path.join(root_output, *[filesystem_safe_name_for_mode(segment, compatibility) for segment in folder_segments])
    )
    max_disc = _album_max_discnumber(track)
    disc_number = _disc_number(track)
    disc_folder = None
    if normalized["disc_handling"] == "keep_together" and max_disc > 1:
        disc_folder = f"CD{disc_number}"

    filename = _formatted_track_filename(track, normalized, max_disc=max_disc)
    path_parts = [album_root]
    if disc_folder:
        path_parts.append(filesystem_safe_name_for_mode(disc_folder, compatibility))
    path_parts.append(filesystem_safe_name_for_mode(filename, compatibility))
    file_path = normalize_filesystem_path(os.path.join(*path_parts))
    return OutputDestination(
        album_root=album_root,
        file_path=file_path,
        folder_segments=folder_segments,
        disc_folder=disc_folder,
        filename=filename,
    )


def build_output_preview_tree(album_tracks: list[dict], settings: dict | None = None, *, has_artwork: bool = False) -> dict[str, object]:
    normalized = normalize_output_format_settings(settings)
    if not album_tracks:
        return {"tree": [], "warnings": [], "albumRootLabel": ""}
    compatibility = normalize_filename_compatibility_settings(album_tracks[0].get("_filename_compatibility"))

    ordered_tracks = sorted(
        album_tracks,
        key=lambda track: (
            _disc_number(track),
            resolved_track_number(track),
            normalize_lookup_text(resolved_track_title(track)),
        ),
    )
    sample = ordered_tracks[0]
    folder_segments = _album_folder_segments(sample, normalized)
    display_folder_segments = [filesystem_safe_name_for_mode(label, compatibility) for label in folder_segments]
    album_root_label = " / ".join(display_folder_segments)
    tree: list[dict[str, object]] = []
    warnings = _preview_warnings(ordered_tracks, normalized)

    for depth, label in enumerate(display_folder_segments):
        tree.append({"kind": "folder", "label": label, "depth": depth})

    max_disc = max((_disc_number(track) for track in ordered_tracks), default=1)
    disc_folders_added: set[str] = set()
    for track in ordered_tracks:
        destination = format_output_destination(
            dict(track, _album_max_discnumber=max_disc),
            "/preview",
            normalized,
        )
        if destination.disc_folder and destination.disc_folder not in disc_folders_added:
            tree.append({"kind": "folder", "label": destination.disc_folder, "depth": len(folder_segments)})
            disc_folders_added.add(destination.disc_folder)
        tree.append({
            "kind": "file",
            "label": filesystem_safe_name_for_mode(destination.filename, compatibility),
            "depth": len(folder_segments) + (1 if destination.disc_folder else 0),
        })

    if has_artwork:
        tree.append({"kind": "file", "label": "Cover.jpg", "depth": len(folder_segments)})

    return {
        "tree": tree,
        "warnings": warnings,
        "albumRootLabel": album_root_label,
    }


def _album_folder_segments(track: dict, settings: dict[str, object]) -> list[str]:
    artist = preferred_folder_artist(track.get("albumartist"), track.get("artist") or "Unknown")
    album = str(track.get("album") or "Unknown")
    year = extract_year(str(track.get("release_date_iso") or track.get("date") or ""))
    genre = str(track.get("genre") or "Unknown").strip() or "Unknown"
    preset = settings["album_folder_preset"]

    if preset == "artist_album_year":
        return [artist, f"{album} ({year})" if year != "0000" else album]
    if preset == "artist_album":
        return [artist, album]
    if preset == "genre_artist_album":
        return [genre, artist, album]
    if preset == "custom":
        return _custom_album_segments(track, settings)
    return [artist, collapse_duplicate_leading_year(f"{year} - {album}")]


def _custom_album_segments(track: dict, settings: dict[str, object]) -> list[str]:
    pattern = settings.get("custom_album_pattern") or DEFAULT_CUSTOM_ALBUM_PATTERN
    segments: list[list[str]] = [[]]
    for item in pattern:
        token = str(item).strip()
        if not token:
            continue
        if token == "folder_break":
            if segments[-1]:
                segments.append([])
            continue
        value = _custom_token_value(track, token)
        if value:
            segments[-1].append(value)
    compact = [collapse_duplicate_leading_year(" - ".join(part).strip()) for part in segments if part]
    return compact or _album_folder_segments(track, {**settings, "album_folder_preset": "artist_year_album"})


def _custom_token_value(track: dict, token: str) -> str:
    if token == "artist":
        return preferred_folder_artist(track.get("albumartist"), track.get("artist") or "Unknown")
    if token == "album":
        return str(track.get("album") or "Unknown")
    if token == "year":
        return extract_year(str(track.get("release_date_iso") or track.get("date") or ""))
    if token == "genre":
        return str(track.get("genre") or "Unknown").strip() or "Unknown"
    if token == "disc":
        return str(_disc_number(track))
    if token == "track_number":
        return str(resolved_track_number(track)).zfill(2)
    if token == "title":
        return resolved_track_title(track)
    return ""


def _formatted_track_filename(track: dict, settings: dict[str, object], *, max_disc: int) -> str:
    separator = _file_separator(str(settings["separator_style"]))
    track_number = str(resolved_track_number(track)).zfill(2) if resolved_track_number(track) else "00"
    title = resolved_track_title(track)
    artist = str(track.get("artist") or preferred_folder_artist(track.get("albumartist"), track.get("artist") or "Unknown"))
    parts: list[str]
    file_naming = settings["file_naming"]
    if file_naming == "artist_title":
        parts = [artist, title]
    elif file_naming == "track_artist_title":
        parts = [track_number, artist, title]
    elif file_naming == "title_only":
        parts = [title]
    else:
        parts = [track_number, title]

    if settings["disc_handling"] == "prefix_disc" and max_disc > 1:
        parts[0] = f"{_disc_number(track)}-{track_number}" if parts else f"{_disc_number(track)}-{track_number}"

    return f"{separator.join(parts)}.flac"


def _file_separator(style: str) -> str:
    if style == "hyphen":
        return " - "
    if style == "space":
        return " "
    if style == "minimal":
        return " "
    return ". "


def _preview_warnings(album_tracks: list[dict], settings: dict[str, object]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if settings["disc_handling"] != "flatten":
        return warnings

    seen_track_numbers: set[str] = set()
    duplicates: set[str] = set()
    for track in album_tracks:
        track_number = str(resolved_track_number(track)).zfill(2)
        if track_number in seen_track_numbers:
            duplicates.add(track_number)
        seen_track_numbers.add(track_number)

    if duplicates:
        warnings.append({
            "id": "ambiguous_flattened_order",
            "title": "Flattening can blur disc order",
            "message": f"Track numbers {', '.join(sorted(duplicates))} repeat across discs and may look ambiguous in one folder.",
        })
    return warnings


def _disc_number(track: dict) -> int:
    try:
        return max(1, int(track.get("discnumber") or 1))
    except (TypeError, ValueError):
        return 1


def _album_max_discnumber(track: dict) -> int:
    try:
        return max(_disc_number(track), int(track.get("_album_max_discnumber") or track.get("max_discnumber") or _disc_number(track)))
    except (TypeError, ValueError):
        return _disc_number(track)
