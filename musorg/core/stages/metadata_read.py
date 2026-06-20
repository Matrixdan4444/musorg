from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from musorg.api.services.workspace_runtime import runtime_album_payload, source_album_id_for_tracks
from musorg.core.events import publish_runtime_event
from musorg.core.metadata_intelligence import build_metadata_intelligence, metadata_snapshot
from musorg.core.runtime_state import is_developer_mode
from musorg.metadata.normalizer import (
    canonical_artist_name,
    normalized_release_dates,
    normalize_artist_aliases,
    normalize_lookup_text,
    normalize_track,
    primary_artist,
    release_type_hint_from_album,
    strip_feature_suffix,
    strip_version_suffixes,
)
from musorg.metadata.cue import cue_track_tag_dicts
from musorg.metadata.parser import read_tags
from musorg.services.deezer import (
    deezer_page_release_date,
    deezer_resolution_metadata,
    get_album_data,
    iso_to_display_date as deezer_iso_to_display_date,
    normalize_deezer_resolution_result,
)
from musorg.services.album_match import (
    LookupInput,
    evidence_confidence,
    provider_metadata_evidence,
    resolution_failure,
    resolution_success,
    russian_transliteration_variant,
    select_preferred_metadata_provider,
)
from musorg.services.musicbrainz import fetch_metadata, fetch_original_release_date
from musorg.utils.debug import log, warning
import re
import os

from musorg.filesystem.naming import filesystem_path_key

MIN_EMBEDDED_COVER_DIMENSION = 1000
METADATA_FETCH_MAX_WORKERS = 6

ALBUM_OVERRIDE_FALSEY = {"", "auto", "none"}


def known_album_value(value: str | None) -> bool:
    return bool(value and value != "Unknown")


def contains_non_ascii_letter(value: str | None) -> bool:
    if not value:
        return False

    return any(char.isalpha() and not char.isascii() for char in value)


def contains_ascii_letter(value: str | None) -> bool:
    if not value:
        return False

    return any(char.isalpha() and char.isascii() for char in value)


def should_use_canonical_album_title(local_title: str | None, canonical_title: str | None) -> bool:
    if not known_album_value(canonical_title):
        return False

    if not known_album_value(local_title):
        return True

    if normalize_lookup_text(local_title) == normalize_lookup_text(canonical_title):
        return local_title.strip() != canonical_title.strip()

    return (
        contains_ascii_letter(local_title)
        and not contains_non_ascii_letter(local_title)
        and contains_non_ascii_letter(canonical_title)
    )


def titles_match_for_cleanup(local_title: str | None, online_title: str | None) -> bool:
    if not local_title or not online_title:
        return False

    cleaned_local_title = strip_feature_suffix(local_title).rstrip(". ")
    return normalize_lookup_text(cleaned_local_title) == normalize_lookup_text(online_title)


def should_preserve_local_track_metadata(track: dict) -> bool:
    return False


def clean_album_name(name: str | None) -> str | None:
    if not name:
        return name

    return strip_version_suffixes(name)


def override_album_lookup(artist: str, album: str) -> tuple[str, str]:
    cleaned_album = clean_album_name(album)
    return artist, cleaned_album


def album_lookup_artist(track: dict) -> str:
    lookup_artist, _album = override_album_lookup(
        primary_artist(track.get("artist")),
        track.get("album"),
    )
    return lookup_artist


def album_lookup_key(artist: str, album: str) -> tuple[str, str]:
    return artist.lower(), album.lower()


def split_artist_names(value: str | None) -> list[str]:
    if not value or value == "Unknown":
        return []

    parts = re.split(r"\s*(?:,|&|/|\\| feat\. | ft\. )\s*", value, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def join_artist_names(names: list[str]) -> str:
    return ", ".join(names)


def canonicalize_artist_credit(value: str | None) -> str | None:
    if not value or value == "Unknown":
        return value

    names = split_artist_names(value)
    if not names:
        return canonical_artist_name(value) or value

    normalized_names = []
    seen = set()
    for name in names:
        canonical = canonical_artist_name(name) or name
        key = artist_identity_key(canonical)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized_names.append(canonical)

    if not normalized_names:
        return canonical_artist_name(value) or value

    return join_artist_names(normalized_names)


def first_artist_name(value: str | None) -> str | None:
    names = split_artist_names(value)
    if names:
        return canonical_artist_name(names[0])

    if value and value != "Unknown":
        return canonical_artist_name(value)

    return None


def strip_artist_parenthetical_alias(value: str | None) -> str | None:
    if not value:
        return value

    stripped = re.sub(r"\s*[\(\[][^\)\]]+[\)\]]\s*", " ", value)
    stripped = " ".join(stripped.split())
    return stripped or value


def lookup_artist_credit(value: str | None) -> str | None:
    names = split_artist_names(value)
    if not names:
        return canonical_artist_name(strip_artist_parenthetical_alias(value))

    canonical_names = []
    seen = set()
    for name in names:
        cleaned_name = strip_artist_parenthetical_alias(name)
        canonical = canonical_artist_name(cleaned_name) or cleaned_name or name
        key = normalize_lookup_text(canonical)
        if not key or key in seen:
            continue
        seen.add(key)
        canonical_names.append(canonical)

    if not canonical_names:
        return canonical_artist_name(strip_artist_parenthetical_alias(value))

    if len(canonical_names) == 1:
        return canonical_names[0]

    return " & ".join(canonical_names)


def artist_identity_key(value: str | None) -> str:
    canonical = canonical_artist_name(value) or value or ""
    return normalize_lookup_text(canonical)


def merged_track_artist(
    track_artist: str | None,
    online_artist: str | None,
    album_artist: str | None,
    preserve_existing_credit: bool = False,
) -> str | None:
    album_names = split_artist_names(album_artist)
    track_names = split_artist_names(track_artist)
    online_names = split_artist_names(online_artist)

    canonical_album_names = [canonical_artist_name(name) or name for name in album_names]
    canonical_track_names = [canonical_artist_name(name) or name for name in track_names]
    canonical_online_names = [canonical_artist_name(name) or name for name in online_names]

    merged = []
    seen = set()

    def add_names(names: list[str]) -> None:
        for name in names:
            key = normalize_lookup_text(name)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(name)

    album_name_keys = {artist_identity_key(name) for name in canonical_album_names if artist_identity_key(name)}
    track_name_keys = {artist_identity_key(name) for name in canonical_track_names if artist_identity_key(name)}
    online_name_keys = {artist_identity_key(name) for name in canonical_online_names if artist_identity_key(name)}

    # If local per-track artist is just an alias/spelling variant of the album artist,
    # ignore it and trust the online track credit for featured artists.
    if canonical_online_names and track_name_keys and track_name_keys.issubset(album_name_keys):
        track_name_keys = set()
        canonical_track_names = []

    # If local per-track artist is a different standalone artist than the online credit,
    # prefer the online credit instead of merging garbage tags like "백사, 104".
    if (
        canonical_online_names
        and canonical_track_names
        and len(track_name_keys) == 1
        and len(online_name_keys) >= 1
        and not track_name_keys.issubset(album_name_keys)
        and not track_name_keys.intersection(online_name_keys)
    ):
        canonical_track_names = []

    # If the album is credited to multiple main artists, keep that full credit on tracks.
    if len(canonical_album_names) > 1:
        add_names(canonical_album_names)

    if preserve_existing_credit and online_name_keys.issubset(track_name_keys | album_name_keys):
        canonical_online_names = []

    add_names(canonical_track_names)
    add_names(canonical_online_names)

    if not merged:
        return None

    return join_artist_names(merged)


def apply_collaboration_artist_fallback(track: dict) -> None:
    album_artist = track.get("albumartist")
    track_artist = track.get("artist")

    album_names = split_artist_names(album_artist)
    if len(album_names) <= 1:
        return

    artist_names = split_artist_names(track_artist)
    album_name_keys = {normalize_lookup_text(name) for name in album_names}
    artist_name_keys = {normalize_lookup_text(name) for name in artist_names}

    # If track artist contains only a subset of the album's main artists,
    # restore the full main-artist credit from the album.
    if artist_name_keys and artist_name_keys.issubset(album_name_keys):
        track["artist"] = join_artist_names(album_names)


def normalize_track_release_dates(track: dict) -> None:
    date, release_date_iso = normalized_release_dates(
        track.get("date", "0000"),
        track.get("release_date_iso", ""),
    )
    track["date"] = date
    track["release_date_iso"] = release_date_iso


def normalize_artist_fields(track: dict) -> None:
    albumartist_value = track.get("albumartist")
    if albumartist_value:
        track["albumartist"] = canonicalize_artist_credit(
            normalize_artist_aliases(albumartist_value)
        )


def track_album_lookup_key(track: dict) -> tuple[str, str]:
    lookup_artist, lookup_album = override_album_lookup(
        album_lookup_artist(track),
        track.get("album"),
    )
    return album_lookup_key(lookup_artist, lookup_album)


def is_singles_bucket_track(track: dict) -> bool:
    album = normalize_lookup_text(clean_album_name(track.get("album")) or "")
    if album != "singles":
        return False

    source_dir = os.path.basename(os.path.dirname(track.get("path", "")))
    return normalize_lookup_text(source_dir) == "singles"


def singles_lookup_title(track: dict) -> str:
    title = strip_feature_suffix(track.get("title") or "").strip()
    return title or (track.get("title") or "Unknown")


def has_sufficient_embedded_cover(track: dict) -> bool:
    try:
        width = int(track.get("cover_width") or 0)
        height = int(track.get("cover_height") or 0)
    except (TypeError, ValueError):
        return False

    return width >= MIN_EMBEDDED_COVER_DIMENSION and height >= MIN_EMBEDDED_COVER_DIMENSION


def source_album_group_key(track: dict) -> tuple[str, str]:
    if is_singles_bucket_track(track):
        album = f"release:{normalize_lookup_text(singles_lookup_title(track))}"
    else:
        album = clean_album_name(track.get("album")) or "Unknown"
    source_dir = os.path.dirname(track.get("path", ""))
    return filesystem_path_key(source_dir), normalize_lookup_text(album)


def apply_staged_album_override(track: dict, override: dict | None) -> None:
    if not override:
        return

    overwrite_existing = bool(override.get("overwriteExistingTags"))

    def assign_text(field: str, override_key: str, default_unknown: str = "Unknown") -> None:
        value = str(override.get(override_key) or "").strip()
        if not value:
            return
        existing = str(track.get(field) or "").strip()
        if overwrite_existing or not existing or existing == default_unknown:
            track[field] = value

    assign_text("album", "albumTitle")
    assign_text("albumartist", "albumArtist")
    assign_text("genre", "genre")

    year = str(override.get("year") or "").strip()
    if year and (overwrite_existing or not str(track.get("date") or "").strip() or str(track.get("date")) == "Unknown"):
        track["date"] = year
        if re.match(r"^\d{4}$", year):
            track["release_date_iso"] = year

    disc = str(override.get("disc") or "").strip()
    if disc and (overwrite_existing or not str(track.get("discnumber") or "").strip()):
        track["discnumber"] = disc

    disc_total = str(override.get("discTotal") or "").strip()
    if disc_total and (overwrite_existing or not str(track.get("disctotal") or "").strip()):
        track["disctotal"] = disc_total

    if str(override.get("compilation") or "").strip() in {"true", "false"}:
        track["compilation"] = str(override.get("compilation")).strip()
    if str(override.get("explicit") or "").strip() in {"true", "false"}:
        track["explicit"] = str(override.get("explicit")).strip()
    if str(override.get("metadataProvider") or "").strip():
        track["_metadata_provider_override"] = str(override.get("metadataProvider")).strip()
    if str(override.get("yearSource") or "").strip():
        track["_year_source_override"] = str(override.get("yearSource")).strip()
    if str(override.get("coverHandlingMode") or "").strip():
        track["_cover_handling_mode"] = str(override.get("coverHandlingMode")).strip()
    if str(override.get("capitalizationMode") or "").strip():
        track["_capitalization_mode"] = str(override.get("capitalizationMode")).strip()
    if override.get("normalizeFeaturingArtists") is not None:
        track["_normalize_featuring_artists"] = bool(override.get("normalizeFeaturingArtists"))
    if override.get("overwriteExistingTags") is not None:
        track["_overwrite_existing_tags"] = bool(override.get("overwriteExistingTags"))


def album_report_snapshot(track: dict, fallback_album_artist: str | None = None) -> dict:
    return {
        "source_dir": os.path.dirname(track.get("path", "")),
        "albumartist": track.get("albumartist") or fallback_album_artist,
        "album": track.get("album"),
        "date": track.get("release_date_iso") or track.get("date"),
        "releasetype": track.get("releasetype"),
    }


def natural_sort_key(value: str) -> list:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def source_track_sort_key(track: dict) -> tuple:
    return (
        int(track.get("discnumber") or 0),
        int(track.get("tracknumber") or 0),
        natural_sort_key(os.path.basename(track.get("path", ""))),
    )


def source_album_fallback_artist(group_tracks: list[dict]) -> str | None:
    candidates = {}

    for track in group_tracks:
        for value in (track.get("albumartist"), track.get("artist")):
            if not known_album_value(value):
                continue

            primary_name = primary_artist(value)
            canonical_name = canonical_artist_name(primary_name) or primary_name
            if not known_album_value(canonical_name):
                continue

            key = normalize_lookup_text(canonical_name)
            if not key:
                continue

            candidates.setdefault(key, {"artist": canonical_name, "count": 0})
            candidates[key]["count"] += 1

    if not candidates:
        return None

    best = max(
        candidates.values(),
        key=lambda item: (item["count"], normalize_lookup_text(item["artist"])),
    )
    return best["artist"]


def pick_lookup_artist(tracks: list[dict]) -> str | None:
    candidates = {}

    for track in tracks:
        for artist in (track.get("albumartist"), track.get("artist")):
            artist_name = lookup_artist_credit(artist)
            if not known_album_value(artist_name):
                continue

            key = normalize_lookup_text(artist_name)
            if not key:
                continue

            candidates.setdefault(key, {"artist": artist_name, "count": 0})
            candidates[key]["count"] += 1
            break

    if not candidates:
        return None

    best = max(candidates.values(), key=lambda item: item["count"])
    return best["artist"]


def album_override_instructions(group_tracks: list[dict]) -> dict:
    for track in group_tracks:
        instructions = {
            "metadataProvider": track.get("_metadata_provider_override"),
            "yearSource": track.get("_year_source_override"),
            "coverHandlingMode": track.get("_cover_handling_mode"),
        }
        if any(value for value in instructions.values()):
            return instructions
    return {}


def collect_source_album_keys(tracks: list[dict]) -> dict[tuple[str, str], tuple[str, str, int, list[str], str | None, dict]]:
    grouped_tracks = {}

    for track in tracks:
        album = clean_album_name(track.get("album"))
        if not known_album_value(album):
            continue

        group_key = source_album_group_key(track)
        grouped_tracks.setdefault(group_key, []).append(track)

    album_keys = {}

    for group_key, group_tracks in grouped_tracks.items():
        if len(group_tracks) < 1:
            continue

        artist = pick_lookup_artist(group_tracks)
        if is_singles_bucket_track(group_tracks[0]):
            album = singles_lookup_title(group_tracks[0])
            track_count = 1
            ordered_titles = [album]
            preferred_release_type = None
        else:
            album = clean_album_name(group_tracks[0].get("album"))
            track_count = len(group_tracks)
            ordered_titles = [
                track.get("title") or ""
                for track in sorted(group_tracks, key=source_track_sort_key)
            ]
            preferred_release_type = None
            for track in group_tracks:
                hint = (track.get("_source_release_type_hint") or "").strip().lower()
                if hint:
                    preferred_release_type = hint
                    break
        if not (known_album_value(artist) and known_album_value(album)):
            continue

        lookup_artist, lookup_album = override_album_lookup(artist, album)

        album_keys[group_key] = (
            lookup_artist,
            lookup_album,
            track_count,
            ordered_titles,
            preferred_release_type,
            album_override_instructions(group_tracks),
        )

    return album_keys


def metadata_worker_count(album_count: int) -> int:
    return max(1, min(METADATA_FETCH_MAX_WORKERS, album_count))


def log_developer_timing(label: str, duration_seconds: float) -> None:
    if not is_developer_mode():
        return

    log("Metadata", f"[DEV MODE] ⏱️ {label}: {duration_seconds:.3f}s", "🧪")


def timed_lookup(label: str, callback):
    started_at = perf_counter()
    result = callback()
    log_developer_timing(label, perf_counter() - started_at)
    return result


def log_developer_metadata_summary(artist: str, album: str, path: str, duration_seconds: float) -> None:
    if not is_developer_mode():
        return
    log("Metadata", f"[DEV MODE] {artist} - {album}: {path} in {duration_seconds:.3f}s", "🧪")


def log_developer_resolution_reuse(artist: str, album: str) -> None:
    if not is_developer_mode():
        return
    log("Metadata", f"[DEV MODE] Reusing in-run resolved metadata for album {artist} - {album}", "🧪")
    log("Metadata", f"[DEV MODE] Skipping duplicate Deezer resolution for {artist} - {album}", "🧪")
    log("Metadata", f"[DEV MODE] Skipping duplicate MusicBrainz lookup for {artist} - {album}", "🧪")


def contains_only_non_ascii_letters(value: str | None) -> bool:
    if not value:
        return False

    saw_letter = False
    for char in value:
        if not char.isalpha():
            continue
        saw_letter = True
        if char.isascii():
            return False
    return saw_letter


def transliterated_deezer_artist_candidates(artist: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        cleaned = " ".join(str(value or "").split()).strip()
        if not known_album_value(cleaned):
            return
        key = normalize_lookup_text(cleaned)
        if not key or key in seen:
            return
        seen.add(key)
        candidates.append(cleaned)

    split_names = split_artist_names(artist)
    if split_names:
        transliterated_split_names = []
        for name in split_names:
            transliterated = russian_transliteration_variant(name) if contains_only_non_ascii_letters(name) else None
            transliterated_split_names.append(transliterated or name)
            if transliterated:
                add_candidate(transliterated)

        if any(transliterated != original for transliterated, original in zip(transliterated_split_names, split_names)):
            add_candidate(" & ".join(transliterated_split_names))
        return candidates

    if contains_only_non_ascii_letters(artist):
        add_candidate(russian_transliteration_variant(artist))

    return candidates


def deezer_artist_candidates(artist: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        cleaned = " ".join(str(value or "").split()).strip()
        if not known_album_value(cleaned):
            return
        key = normalize_lookup_text(cleaned)
        if not key or key in seen:
            return
        seen.add(key)
        candidates.append(cleaned)

    add_candidate(artist)
    add_candidate(normalize_artist_aliases(artist))
    add_candidate(strip_artist_parenthetical_alias(artist))

    split_names = split_artist_names(artist)
    if split_names and len(split_names) == 1:
        add_candidate(split_names[0])
    for name in split_names:
        add_candidate(name)
        add_candidate(canonical_artist_name(name) or name)

    add_candidate(primary_artist(artist))

    for name in transliterated_deezer_artist_candidates(artist):
        add_candidate(name)

    return candidates or [artist]


def deezer_artist_search_plan(artist: str) -> list[dict[str, object]]:
    split_names = split_artist_names(artist)
    collaboration_names = split_names if len(split_names) > 1 else []
    collaboration_candidates = []
    seen: set[str] = set()

    for name in collaboration_names:
        for candidate in (name, canonical_artist_name(name) or name):
            key = normalize_lookup_text(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            collaboration_candidates.append(candidate)

    exact_single_candidates = []
    for candidate in (
        artist,
        normalize_artist_aliases(artist),
        strip_artist_parenthetical_alias(artist),
        primary_artist(artist),
    ):
        cleaned = " ".join(str(candidate or "").split()).strip()
        key = normalize_lookup_text(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        exact_single_candidates.append(cleaned)

    transliterated_candidates = transliterated_deezer_artist_candidates(artist)

    phases: list[dict[str, object]] = []
    if collaboration_candidates:
        phases.append({
            "artists": [artist],
            "artist_query_mode": "exact",
            "include_album_only_queries": False,
            "include_track_title_fallback": False,
        })
        phases.append({
            "artists": collaboration_candidates,
            "artist_query_mode": "exact",
            "include_album_only_queries": False,
            "include_track_title_fallback": False,
        })
        phases.append({
            "artists": collaboration_candidates,
            "artist_query_mode": "expanded",
            "include_album_only_queries": False,
            "include_track_title_fallback": False,
        })
    elif exact_single_candidates:
        phases.append({
            "artists": exact_single_candidates,
            "artist_query_mode": "expanded",
            "include_album_only_queries": True,
            "include_track_title_fallback": True,
        })

    if collaboration_candidates and transliterated_candidates:
        phases.append({
            "artists": transliterated_candidates,
            "artist_query_mode": "expanded",
            "include_album_only_queries": False,
            "include_track_title_fallback": False,
        })

    if collaboration_candidates:
        phases.append({
            "artists": [artist],
            "artist_query_mode": "expanded",
            "include_album_only_queries": False,
            "include_track_title_fallback": False,
        })

    if collaboration_candidates:
        phases.append({
            "artists": [artist],
            "artist_query_mode": "exact",
            "include_album_only_queries": True,
            "include_track_title_fallback": True,
        })
    return phases


def canonical_lookup_signature(
    payload: tuple[str, str, int, list[str], str | None, dict],
) -> tuple[str, str, int, tuple[str, ...], str, str]:
    artist, album, track_count, track_titles, preferred_release_type, instructions = unpack_album_metadata_payload(payload)
    return (
        artist,
        album,
        track_count,
        tuple(track_titles),
        (preferred_release_type or "").strip().lower(),
        str(instructions.get("metadataProvider") or "").strip().lower(),
    )


def unpack_album_metadata_payload(
    payload: tuple[str, str, int, list[str], str | None] | tuple[str, str, int, list[str], str | None, dict],
) -> tuple[str, str, int, list[str], str | None, dict]:
    if len(payload) == 5:
        artist, album, track_count, track_titles, preferred_release_type = payload
        return artist, album, track_count, track_titles, preferred_release_type, {}
    artist, album, track_count, track_titles, preferred_release_type, instructions = payload
    return artist, album, track_count, track_titles, preferred_release_type, instructions


def deezer_failure_reason_label(reason: str | None) -> str:
    labels = {
        "no_candidates": "no candidates",
        "no_acceptable_candidate": "no acceptable candidate",
        "search_unavailable": "search unavailable",
        "album_details_unavailable": "album details unavailable",
        "invalid_payload": "invalid payload",
        "partial_payload": "partial payload",
        "track_count_mismatch": "track count mismatch",
        "validation_rejected": "validation rejected",
        "album_details_mismatch": "album details mismatch",
        "unknown": "terminal Deezer failure",
    }
    return labels.get(reason or "unknown", reason or "terminal Deezer failure")


_DEEZER_FAILURE_REASON_PRIORITY = {
    "track_count_mismatch": 4,
    "no_acceptable_candidate": 3,
    "no_candidates": 2,
    "search_unavailable": 1,
}


def select_preferred_deezer_failure(results: list[dict | None]) -> dict | None:
    preferred = None
    preferred_rank = -1

    for result in results:
        normalized = normalize_deezer_resolution_result(result)
        if normalized.get("success"):
            return normalized

        rank = _DEEZER_FAILURE_REASON_PRIORITY.get(str(normalized.get("reason") or ""), 0)
        if rank >= preferred_rank:
            preferred = normalized
            preferred_rank = rank

    return preferred


def warn_deezer_resolution_failure(
    artist: str,
    album: str,
    result: dict | None,
) -> None:
    reason = str((normalize_deezer_resolution_result(result)).get("reason") or "unknown")
    if reason == "no_acceptable_candidate":
        warning("Deezer", f"No acceptable album match for {artist} - {album}, falling back to MusicBrainz")
        return
    if reason == "no_candidates":
        warning("Deezer", f"No album candidates found for {artist} - {album}, falling back to MusicBrainz")
        return
    if reason == "search_unavailable":
        warning("Deezer", f"Album search unavailable for {artist} - {album}, falling back to MusicBrainz")
        return
    if reason == "track_count_mismatch":
        warning("Deezer", f"Deezer rejected release for {artist} - {album} due to track count mismatch, falling back to MusicBrainz")
        return

    warning("Deezer", f"Deezer fallback for {artist} - {album} due to {deezer_failure_reason_label(reason)}, falling back to MusicBrainz")


def resolve_deezer_match(
    artist: str,
    album: str,
    track_count: int,
    track_titles: list[str],
    preferred_release_type: str | None,
    warn_on_miss: bool = True,
    run_report=None,
) -> dict | None:
    deezer_result = None
    failed_results: list[dict | None] = []
    seen_candidates = set()
    for phase in deezer_artist_search_plan(artist):
        phase_artists = phase.get("artists") or []
        artist_query_mode = str(phase.get("artist_query_mode") or "expanded")
        include_album_only_queries = bool(phase.get("include_album_only_queries"))
        include_track_title_fallback = bool(phase.get("include_track_title_fallback"))
        for deezer_artist in phase_artists:
            if not known_album_value(deezer_artist):
                continue

            candidate_key = (
                normalize_lookup_text(deezer_artist),
                artist_query_mode,
                include_album_only_queries,
                include_track_title_fallback,
            )
            if not candidate_key[0] or candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)

            def lookup():
                return get_album_data(
                    deezer_artist,
                    album,
                    expected_track_count=track_count,
                    expected_titles=track_titles,
                    preferred_release_type=preferred_release_type,
                    warn_on_miss=False,
                    artist_query_mode=artist_query_mode,
                    include_album_only_queries=include_album_only_queries,
                    include_track_title_fallback=include_track_title_fallback,
                )

            if run_report:
                with run_report.measure("metadata_deezer"):
                    deezer_result = normalize_deezer_resolution_result(timed_lookup("Deezer lookup", lookup))
            else:
                deezer_result = normalize_deezer_resolution_result(timed_lookup("Deezer lookup", lookup))

            deezer_match = deezer_resolution_metadata(deezer_result)
            if deezer_match:
                return deezer_result

            failed_results.append(deezer_result)
            if is_developer_mode():
                log(
                    "Metadata",
                    (
                        f"[DEV MODE] Deezer phase failed for {artist} - {album}: "
                        f"artist={deezer_artist}, mode={artist_query_mode}, "
                        f"album_only={include_album_only_queries}, track_fallback={include_track_title_fallback}, "
                        f"reason={deezer_failure_reason_label((deezer_result or {}).get('reason'))}"
                    ),
                    "🧪",
                )

    preferred_failure = select_preferred_deezer_failure(failed_results) or deezer_result
    if warn_on_miss and preferred_failure:
        warn_deezer_resolution_failure(artist, album, preferred_failure)
    return preferred_failure


def metadata_provider_for_resolution(musicbrainz_match: dict | None, deezer_result: dict | None) -> str | None:
    winner = None
    if isinstance(deezer_result, dict):
        winner = str(deezer_result.get("winner") or "").strip().lower() or None
    if winner in {"deezer", "musicbrainz"}:
        return winner
    deezer_match = deezer_resolution_metadata(deezer_result)
    if deezer_match and deezer_album_metadata_complete(deezer_match):
        return "deezer"
    if musicbrainz_match:
        return "musicbrainz"
    return None


def fetch_musicbrainz_metadata_result(
    artist: str,
    album: str,
    track_count: int,
    track_titles: list[str],
    preferred_release_type: str | None,
) -> dict:
    metadata = fetch_metadata(
        artist,
        album,
        expected_track_count=track_count,
        expected_titles=track_titles,
        preferred_release_type=preferred_release_type,
    )
    if not metadata:
        return resolution_failure("musicbrainz", "no_candidates")

    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=track_count,
        expected_titles=tuple(track_titles),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    evidence = provider_metadata_evidence("musicbrainz", metadata, lookup)
    return resolution_success("musicbrainz", metadata, confidence=evidence_confidence(evidence), evidence=evidence)


# Below this track-title-sequence score a candidate's tracks clearly do not
# correspond to the source (e.g. a remix album that only shares the track
# count), so the match is rejected rather than overwriting good source titles.
DEEZER_TITLE_MATCH_REJECT_SCORE = 55
_GENERIC_TITLE_RE = re.compile(r"^\s*(?:track|audio\s*track|untitled)?\s*\d*\s*$", re.IGNORECASE)


def _source_titles_are_informative(titles) -> bool:
    """True when the source has enough real track titles to compare against.

    Poorly-tagged albums (numbers / "Track 01" / blanks) have nothing useful to
    compare, so for those we must NOT reject a match for low title similarity.
    """
    if not titles:
        return False
    meaningful = 0
    for title in titles:
        text = str(title or "").strip()
        if not text or text.lower() in {"unknown", "untitled"}:
            continue
        if _GENERIC_TITLE_RE.match(text):
            continue
        if any(char.isalpha() for char in text):
            meaningful += 1
    return meaningful >= max(1, len(titles) // 2)


def resolve_album_metadata(
    payload: tuple[str, str, int, list[str], str | None, dict],
    total_albums: int,
    index: int,
    run_report=None,
    on_fallback=None,
) -> dict:
    artist, album, track_count, track_titles, preferred_release_type, instructions = unpack_album_metadata_payload(payload)
    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=track_count,
        expected_titles=tuple(track_titles),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    album_started_at = perf_counter()
    deezer_phase_started_at = perf_counter()
    log("Metadata", f"Matching album metadata {index}/{total_albums}: {artist} — {album}", "🧠")
    if is_developer_mode():
        log("Metadata", f"[DEV MODE] Re-running release validation for {artist} - {album}", "🧪")

    metadata_provider = str(instructions.get("metadataProvider") or "auto").strip().lower()
    deezer_result = None
    if metadata_provider != "musicbrainz":
        artist_candidates = deezer_artist_candidates(artist)
        if is_developer_mode() and artist_candidates:
            log("Metadata", f"[DEV MODE] Deezer artist candidates for {artist} - {album}: {', '.join(artist_candidates)}", "🧪")
        deezer_result = resolve_deezer_match(
            artist,
            album,
            track_count,
            track_titles,
            preferred_release_type,
            warn_on_miss=True,
            run_report=run_report,
        )
    deezer_phase_duration = perf_counter() - deezer_phase_started_at
    deezer_match = deezer_resolution_metadata(deezer_result)
    deezer_evidence = provider_metadata_evidence("deezer", deezer_match, lookup)
    deezer_confidence = evidence_confidence(deezer_evidence)

    # Reject a candidate whose track titles do not correspond to the source
    # (only the track count happened to match, e.g. a remix album). Applying it
    # would overwrite real source titles with unrelated ones. Only reject when
    # the source actually has informative titles to compare against.
    if (
        deezer_match
        and deezer_evidence is not None
        and _source_titles_are_informative(track_titles)
        and deezer_evidence.track_title_sequence_score < DEEZER_TITLE_MATCH_REJECT_SCORE
    ):
        if is_developer_mode():
            log(
                "Metadata",
                f"[DEV MODE] Rejecting Deezer match for {artist} - {album}: track titles do not "
                f"align (seq={deezer_evidence.track_title_sequence_score:.0f})",
                "🧪",
            )
        deezer_result = None
        deezer_match = None
        deezer_evidence = None
        deezer_confidence = None

    validation_started_at = perf_counter()
    deezer_complete = deezer_album_metadata_complete(deezer_match)
    validation_duration = perf_counter() - validation_started_at
    log_developer_timing("Metadata validation", validation_duration)

    if deezer_complete and metadata_provider != "musicbrainz" and deezer_confidence != "low":
        musicbrainz_date_match = None
        musicbrainz_phase_started_at = perf_counter()
        if metadata_provider != "deezer":
            def musicbrainz_date_lookup():
                return fetch_original_release_date(
                    artist,
                    album,
                    expected_track_count=track_count,
                    expected_titles=track_titles,
                    preferred_release_type=preferred_release_type,
                    run_report=run_report,
                )

            if run_report:
                with run_report.measure("metadata_musicbrainz_date"):
                    musicbrainz_date_match = timed_lookup("MusicBrainz date lookup", musicbrainz_date_lookup)
            else:
                musicbrainz_date_match = timed_lookup("MusicBrainz date lookup", musicbrainz_date_lookup)
        musicbrainz_phase_duration = perf_counter() - musicbrainz_phase_started_at

        if not musicbrainz_date_match and metadata_provider != "deezer":
            if run_report:
                with run_report.measure("metadata_deezer_page_date"):
                    page_date_iso = deezer_page_release_date(deezer_match.get("album_id"))
            else:
                page_date_iso = deezer_page_release_date(deezer_match.get("album_id"))
            if page_date_iso:
                deezer_match = {
                    **deezer_match,
                    "date": deezer_iso_to_display_date(page_date_iso),
                    "date_iso": page_date_iso,
                    "date_source": "deezer_page",
                }
                if isinstance(deezer_result, dict):
                    deezer_result = {**deezer_result, "metadata": deezer_match}

        path = "deezer-fast-path"
        if metadata_provider == "deezer":
            path = "deezer-forced"
        if is_developer_mode():
            log("Metadata", f"[DEV MODE] Deezer accepted early, skipping MusicBrainz for {artist} - {album}", "🧪")
            log_developer_timing("Deezer phase", deezer_phase_duration)
            log_developer_timing("MusicBrainz fallback phase", musicbrainz_phase_duration)
            log_developer_timing("Album metadata total", perf_counter() - album_started_at)
        log_developer_metadata_summary(artist, album, path, perf_counter() - album_started_at)
        return {
            "musicbrainz": musicbrainz_date_match,
            "deezer": deezer_match,
            "deezer_result": deezer_result,
            "winner": "deezer",
            "path": path,
            "timings": {
                "deezer_phase": deezer_phase_duration,
                "musicbrainz_fallback_phase": musicbrainz_phase_duration,
                "album_total": perf_counter() - album_started_at,
            },
        }

    if is_developer_mode():
        if deezer_match:
            log("Metadata", f"[DEV MODE] Deezer incomplete, falling back to MusicBrainz for {artist} - {album}", "🧪")
        else:
            deezer_reason = deezer_failure_reason_label((deezer_result or {}).get("reason"))
            log("Metadata", f"[DEV MODE] Deezer: Falling back to MusicBrainz due to {deezer_reason} for {artist} - {album}", "🧪")

    if metadata_provider != "deezer" and on_fallback and deezer_result is not None:
        on_fallback({
            "artist": artist,
            "album": album,
            "from": "deezer",
            "to": "musicbrainz",
            "reason": str((deezer_result or {}).get("reason") or "unknown"),
            "path": "deezer-then-musicbrainz" if deezer_match else "musicbrainz-fallback",
            "progress": "matching",
        })

    def musicbrainz_lookup():
        return fetch_musicbrainz_metadata_result(
            artist,
            album,
            track_count,
            track_titles,
            preferred_release_type,
        )

    musicbrainz_match = None
    musicbrainz_result = None
    musicbrainz_phase_started_at = perf_counter()
    if metadata_provider != "deezer":
        if run_report:
            with run_report.measure("metadata_musicbrainz"):
                musicbrainz_result = timed_lookup("MusicBrainz lookup", musicbrainz_lookup)
        else:
            musicbrainz_result = timed_lookup("MusicBrainz lookup", musicbrainz_lookup)
    musicbrainz_phase_duration = perf_counter() - musicbrainz_phase_started_at
    if isinstance(musicbrainz_result, dict):
        musicbrainz_match = musicbrainz_result.get("metadata") if musicbrainz_result.get("success") else None

    album_total_duration = perf_counter() - album_started_at
    if is_developer_mode():
        log_developer_timing("Deezer phase", deezer_phase_duration)
        log_developer_timing("MusicBrainz fallback phase", musicbrainz_phase_duration)
        log_developer_timing("Album metadata total", album_total_duration)

    path = "deezer-then-musicbrainz" if deezer_match else "musicbrainz-fallback"
    if metadata_provider == "musicbrainz":
        path = "musicbrainz-forced"
    elif metadata_provider == "deezer":
        path = "deezer-forced"
    winner = select_preferred_metadata_provider(deezer_match, musicbrainz_match, lookup)
    if metadata_provider == "musicbrainz" and musicbrainz_match:
        winner = "musicbrainz"
    elif metadata_provider == "deezer" and deezer_match:
        winner = "deezer"
    log_developer_metadata_summary(artist, album, path, album_total_duration)
    return {
        "musicbrainz": musicbrainz_match,
        "deezer": deezer_match,
        "deezer_result": deezer_result,
        "musicbrainz_result": musicbrainz_result,
        "winner": winner,
        "path": path,
        "timings": {
            "deezer_phase": deezer_phase_duration,
            "musicbrainz_fallback_phase": musicbrainz_phase_duration,
            "album_total": album_total_duration,
        },
    }


def fetch_single_album_metadata(
    key: tuple[str, str],
    payload: tuple[str, str, int, list[str], str | None, dict],
    total_albums: int,
    index: int,
    run_report=None,
    on_fallback=None,
) -> tuple[tuple[str, str], dict | None, dict | None]:
    resolved = resolve_album_metadata(
        payload,
        total_albums,
        index,
        run_report=run_report,
        on_fallback=on_fallback,
    )
    return key, resolved["musicbrainz"], resolved["deezer"]


def fetch_album_metadata(
    album_keys: dict[tuple[str, str], tuple[str, str, int, list[str], str | None, dict]],
    run_report=None,
    on_resolved=None,
    on_fallback=None,
) -> tuple[dict, dict, dict]:
    musicbrainz_data = {}
    deezer_data = {}
    resolved_by_signature = {}

    log("Metadata", f"Matching album metadata... checking {len(album_keys)} albums online", "🧠")
    group_keys_by_signature = {}
    payload_by_signature = {}
    first_group_key_by_signature = {}

    for group_key, payload in album_keys.items():
        signature = canonical_lookup_signature(payload)
        if signature not in payload_by_signature:
            payload_by_signature[signature] = payload
            first_group_key_by_signature[signature] = group_key
        else:
            artist, album, _track_count, _track_titles, _preferred_release_type, _instructions = unpack_album_metadata_payload(payload)
            log_developer_resolution_reuse(artist, album)
        group_keys_by_signature.setdefault(signature, []).append(group_key)

    ordered_signatures = list(payload_by_signature.items())
    total_albums = len(ordered_signatures)
    if not ordered_signatures:
        return musicbrainz_data, deezer_data, resolved_by_signature

    def assign_signature_result(signature, resolved):
        resolved_by_signature[signature] = resolved
        for group_key in group_keys_by_signature[signature]:
            musicbrainz_data[group_key] = resolved["musicbrainz"]
            deezer_data[group_key] = resolved["deezer"]

    if len(ordered_signatures) == 1:
        signature, payload = ordered_signatures[0]
        resolved = resolve_album_metadata(
            payload,
            total_albums,
            1,
            run_report=run_report,
            on_fallback=(
                (
                    lambda fallback_payload, group_key=first_group_key_by_signature[signature]:
                    on_fallback(group_key, fallback_payload)
                )
                if on_fallback else None
            ),
        )
        assign_signature_result(signature, resolved)
        if on_resolved:
            on_resolved(first_group_key_by_signature[signature], resolved["musicbrainz"], resolved["deezer"], resolved)
        return musicbrainz_data, deezer_data, resolved_by_signature

    with ThreadPoolExecutor(max_workers=metadata_worker_count(len(ordered_signatures))) as executor:
        future_to_signature = {
            executor.submit(
                resolve_album_metadata,
                payload,
                total_albums,
                index,
                run_report,
                (
                    lambda fallback_payload, group_key=first_group_key_by_signature[signature]:
                    on_fallback(group_key, fallback_payload)
                ) if on_fallback else None,
            ): signature
            for index, (_signature, payload) in enumerate(ordered_signatures, start=1)
            for signature, payload in [(_signature, payload)]
        }

        for future in as_completed(future_to_signature):
            signature = future_to_signature[future]
            try:
                resolved = future.result()
            except Exception as exc:
                # A single album failing (corrupt file, network error) must not
                # abort the whole batch — record it as an unresolved album.
                artist, album, *_rest = unpack_album_metadata_payload(payload_by_signature[signature])
                warning("Metadata", f"Failed to resolve metadata for {artist} — {album}: {exc}")
                resolved = {
                    "musicbrainz": None,
                    "deezer": None,
                    "deezer_result": None,
                    "musicbrainz_result": None,
                    "winner": None,
                    "path": None,
                    "timings": {
                        "deezer_phase": 0.0,
                        "musicbrainz_fallback_phase": 0.0,
                        "album_total": 0.0,
                    },
                }
            assign_signature_result(signature, resolved)
            if on_resolved:
                resolved = resolved_by_signature[signature]
                on_resolved(
                    first_group_key_by_signature[signature],
                    resolved["musicbrainz"],
                    resolved["deezer"],
                    resolved,
                )

    return musicbrainz_data, deezer_data, resolved_by_signature


def apply_capitalization_mode(value: str, mode: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return text
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title_case":
        return text.title()
    if mode == "sentence_case":
        return text[:1].upper() + text[1:].lower()
    return text


def apply_post_metadata_album_override(track: dict, override: dict | None) -> None:
    if not override:
        return

    overwrite_existing = bool(override.get("overwriteExistingTags"))

    def assign_text(field: str, override_key: str, unknown_values: tuple[str, ...] = ("", "Unknown")) -> None:
        value = str(override.get(override_key) or "").strip()
        if not value:
            return
        existing = str(track.get(field) or "").strip()
        if overwrite_existing or existing in unknown_values:
            track[field] = value

    assign_text("album", "albumTitle")
    assign_text("albumartist", "albumArtist", ("", "Unknown", "Unknown artist"))
    assign_text("genre", "genre")

    year = str(override.get("year") or "").strip()
    year_source = str(override.get("yearSource") or "auto").strip().lower()
    if year and (overwrite_existing or not str(track.get("date") or "").strip() or year_source == "local_tags"):
        track["date"] = year
        if re.match(r"^\d{4}$", year):
            track["release_date_iso"] = year
    elif year_source == "musicbrainz" and str(track.get("release_date_iso") or "").strip():
        iso = str(track.get("release_date_iso") or "").strip()
        track["date"] = iso[:4] if re.match(r"^\d{4}", iso) else track.get("date", "")
    elif year_source == "deezer" and str(track.get("date") or "").strip():
        date = str(track.get("date") or "").strip()
        track["release_date_iso"] = date if re.match(r"^\d{4}$", date) else str(track.get("release_date_iso") or "")

    disc = str(override.get("disc") or "").strip()
    if disc and (overwrite_existing or not str(track.get("discnumber") or "").strip()):
        track["discnumber"] = disc
    disc_total = str(override.get("discTotal") or "").strip()
    if disc_total and (overwrite_existing or not str(track.get("disctotal") or "").strip()):
        track["disctotal"] = disc_total

    if str(override.get("compilation") or "").strip() in {"true", "false"}:
        track["compilation"] = str(override.get("compilation")).strip()
    if str(override.get("explicit") or "").strip() in {"true", "false"}:
        track["explicit"] = str(override.get("explicit")).strip()

    if bool(override.get("normalizeFeaturingArtists")):
        for key in ("artist", "albumartist", "album", "title"):
            if track.get(key):
                track[key] = strip_feature_suffix(track.get(key))

    capitalization_mode = str(override.get("capitalizationMode") or "").strip().lower()
    if capitalization_mode and capitalization_mode not in ALBUM_OVERRIDE_FALSEY:
        for key in ("album", "albumartist", "genre", "title"):
            if track.get(key):
                track[key] = apply_capitalization_mode(str(track.get(key)), capitalization_mode)

    cover_mode = str(override.get("coverHandlingMode") or "").strip().lower()
    if cover_mode == "remove":
        track["cover"] = ""


def apply_post_metadata_provider_overrides(
    track: dict,
    override: dict | None,
    musicbrainz_data: dict | None,
    deezer_data: dict | None,
) -> None:
    if not override:
        return

    year_source = str(override.get("yearSource") or "auto").strip().lower()
    if year_source == "musicbrainz" and musicbrainz_data:
        mb_iso = str(musicbrainz_data.get("date_iso") or "").strip()
        mb_date = str(musicbrainz_data.get("date") or "").strip()
        if mb_iso:
            track["release_date_iso"] = mb_iso
            if re.match(r"^\d{4}", mb_iso):
                track["date"] = mb_iso[:4]
        elif mb_date:
            track["date"] = mb_date
    elif year_source == "deezer" and deezer_data:
        deezer_iso = str(deezer_data.get("date_iso") or "").strip()
        deezer_date = str(deezer_data.get("date") or "").strip()
        if deezer_iso:
            track["release_date_iso"] = deezer_iso
            if re.match(r"^\d{4}", deezer_iso):
                track["date"] = deezer_iso[:4]
        elif deezer_date:
            track["date"] = deezer_date

    cover_mode = str(override.get("coverHandlingMode") or "").strip().lower()
    if cover_mode == "force_deezer" and deezer_data and deezer_data.get("cover"):
        track["cover"] = deezer_data["cover"]
    elif cover_mode == "force_musicbrainz" and musicbrainz_data and musicbrainz_data.get("cover"):
        track["cover"] = musicbrainz_data["cover"]


def apply_musicbrainz_date(track: dict, musicbrainz_data: dict | None) -> None:
    if not musicbrainz_data:
        return

    mb_date = musicbrainz_data.get("date")
    if mb_date:
        track["date"] = mb_date

    mb_date_iso = musicbrainz_data.get("date_iso")
    if mb_date_iso:
        track["release_date_iso"] = mb_date_iso


def apply_musicbrainz_canonical_album_title(track: dict, musicbrainz_data: dict | None) -> None:
    if not musicbrainz_data:
        return

    mb_album = musicbrainz_data.get("album")
    if should_use_canonical_album_title(track.get("album"), mb_album):
        track["album"] = mb_album


def has_full_release_date(track: dict) -> bool:
    release_date_iso = (track.get("release_date_iso") or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", release_date_iso):
        return True

    display_date = (track.get("date") or "").strip()
    return bool(re.match(r"^\d{2}-\d{2}-\d{4}$", display_date))


def apply_musicbrainz_album_metadata(track: dict, musicbrainz_data: dict | None) -> None:
    if not musicbrainz_data:
        return

    mb_albumartist = musicbrainz_data.get("albumartist")
    if mb_albumartist:
        track["albumartist"] = mb_albumartist

    mb_release_type = musicbrainz_data.get("releasetype")
    if mb_release_type:
        track["releasetype"] = mb_release_type

    mb_cover = musicbrainz_data.get("cover")
    if mb_cover and not track.get("cover") and not has_sufficient_embedded_cover(track):
        track["cover"] = mb_cover


def apply_release_track_count(
    track: dict,
    musicbrainz_data: dict | None,
    deezer_data: dict | None,
) -> None:
    for metadata in (deezer_data, musicbrainz_data):
        if not metadata:
            continue

        tracks = metadata.get("tracks", [])
        if tracks:
            track["release_track_count"] = len(tracks)
            return


def deezer_track_metadata_matches(deezer_data: dict | None) -> bool:
    if not deezer_data:
        return False

    deezer_tracks = deezer_data.get("tracks", [])
    expected_track_count = deezer_data.get("expected_track_count")
    return bool(deezer_tracks and expected_track_count and len(deezer_tracks) == expected_track_count)


def deezer_album_metadata_complete(deezer_data: dict | None) -> bool:
    if not deezer_data:
        return False

    return bool(
        deezer_data.get("albumartist")
        and deezer_data.get("releasetype")
        and deezer_track_metadata_matches(deezer_data)
    )


def pick_deezer_track_metadata(
    track: dict,
    deezer_data: dict | None,
    source_position: int | None = None,
) -> dict | None:
    if not deezer_data:
        return None

    deezer_tracks = deezer_data.get("tracks", [])
    if not deezer_tracks or "tracknumber" not in track:
        return None

    expected_track_count = deezer_data.get("expected_track_count")
    track_count_matches = not expected_track_count or len(deezer_tracks) == expected_track_count

    indexed_track = None
    if track_count_matches:
        idx = (source_position - 1) if source_position else track.get("tracknumber") - 1
        indexed_track = deezer_tracks[idx] if 0 <= idx < len(deezer_tracks) else None

    local_title = track.get("title")
    if indexed_track and titles_match_for_cleanup(local_title, indexed_track.get("title")):
        return indexed_track

    title_matches = [
        deezer_track
        for deezer_track in deezer_tracks
        if titles_match_for_cleanup(local_title, deezer_track.get("title"))
    ]

    if len(title_matches) == 1:
        return title_matches[0]

    if len(title_matches) > 1:
        local_tracknumber = track.get("tracknumber")
        for deezer_track in title_matches:
            if deezer_track.get("tracknumber") == local_tracknumber:
                return deezer_track
        return title_matches[0]

    return indexed_track if track_count_matches else None


def apply_musicbrainz_track_metadata(
    track: dict,
    musicbrainz_data: dict | None,
    source_position: int | None = None,
) -> None:
    if not musicbrainz_data:
        return

    musicbrainz_tracks = musicbrainz_data.get("tracks", [])
    if not musicbrainz_tracks or "tracknumber" not in track:
        return

    expected_track_count = musicbrainz_data.get("expected_track_count")
    if expected_track_count and len(musicbrainz_tracks) != expected_track_count:
        return

    idx = (source_position - 1) if source_position else track.get("tracknumber") - 1
    if not 0 <= idx < len(musicbrainz_tracks):
        return

    musicbrainz_track = musicbrainz_tracks[idx]

    if musicbrainz_track.get("title"):
        track["title"] = musicbrainz_track["title"]

    if musicbrainz_track.get("artist"):
        track["artist"] = musicbrainz_track["artist"]

    if musicbrainz_track.get("tracknumber"):
        track["tracknumber"] = musicbrainz_track["tracknumber"]
        track["singleoriginaltracknumber"] = musicbrainz_track["tracknumber"]

    if musicbrainz_track.get("discnumber"):
        track["discnumber"] = musicbrainz_track["discnumber"]


def apply_transliterated_track_title_fallback(track: dict, musicbrainz_data: dict | None) -> None:
    if not musicbrainz_data or not musicbrainz_data.get("use_canonical_album_title"):
        return

    if contains_non_ascii_letter(track.get("title")):
        return

    transliterated_title = russian_transliteration_variant(track.get("title") or "")
    if transliterated_title:
        track["title"] = transliterated_title


def apply_deezer_metadata(
    track: dict,
    deezer_data: dict | None,
    source_position: int | None = None,
    preserve_track_title: bool = False,
    preserve_track_artist: bool = False,
    preserve_album_metadata: bool = False,
    preserve_release_type: bool = False,
) -> None:
    if not deezer_data:
        return

    # A confirmed Deezer album match should win for album-level attribution.
    # This prevents stray local or MusicBrainz per-track credits from splitting
    # one album across multiple artist folders.
    if deezer_data.get("albumartist") and not preserve_album_metadata:
        track["albumartist"] = deezer_data["albumartist"]

    deezer_album = deezer_data.get("album")
    if deezer_album and (
        is_singles_bucket_track(track)
        or should_use_canonical_album_title(track.get("album"), deezer_album)
    ):
        track["album"] = deezer_album

    if deezer_data.get("genre"):
        track["genre"] = str(deezer_data["genre"])

    if deezer_data.get("releasetype") and not preserve_album_metadata and not preserve_release_type:
        track["releasetype"] = deezer_data["releasetype"]

    if deezer_data.get("cover") and not has_sufficient_embedded_cover(track):
        track["cover"] = deezer_data["cover"]

    if not has_full_release_date(track):
        if deezer_data.get("date"):
            track["date"] = deezer_data["date"]
        if deezer_data.get("date_iso"):
            track["release_date_iso"] = deezer_data["date_iso"]

    if should_preserve_local_track_metadata(track):
        return

    deezer_track = pick_deezer_track_metadata(
        track,
        deezer_data,
        source_position=source_position,
    )
    if not deezer_track:
        max_discnumber = deezer_data.get("max_discnumber")
        try:
            local_discnumber = int(track.get("discnumber") or 0)
        except (TypeError, ValueError):
            local_discnumber = 0
        if max_discnumber and local_discnumber > max_discnumber:
            track["discnumber"] = max_discnumber
        return

    deezer_tracks = deezer_data.get("tracks", [])
    expected_track_count = deezer_data.get("expected_track_count")
    exact_track_count_match = bool(expected_track_count and len(deezer_tracks) == expected_track_count)
    indexed_deezer_track = None
    if exact_track_count_match:
        idx = (source_position - 1) if source_position else track.get("tracknumber") - 1
        if 0 <= idx < len(deezer_tracks):
            indexed_deezer_track = deezer_tracks[idx]

    if (
        not preserve_track_title
        and deezer_track.get("title")
        and (
            deezer_track is indexed_deezer_track
            or titles_match_for_cleanup(track.get("title"), deezer_track.get("title"))
        )
    ):
        track["title"] = deezer_track["title"]

    merged_artist = merged_track_artist(
        track.get("artist"),
        deezer_track.get("artist"),
        track.get("albumartist"),
        preserve_existing_credit=preserve_track_artist,
    )

    if merged_artist:
        track["artist"] = merged_artist

    if deezer_track.get("tracknumber"):
        track["tracknumber"] = deezer_track["tracknumber"]
        track["singleoriginaltracknumber"] = deezer_track["tracknumber"]

    if deezer_track.get("discnumber"):
        track["discnumber"] = deezer_track["discnumber"]


def fill_missing_albumartist(track: dict, original_artist: str | None) -> None:
    albumartist = track.get("albumartist")
    if albumartist and albumartist != "Unknown":
        return

    artist_val = original_artist or track.get("artist") or "Unknown"
    track["albumartist"] = primary_artist(artist_val)


def cue_album_track_tags(image_path, sheet):
    """One read_tags-shaped dict per cue track for an image+cue album."""
    base = read_tags(image_path)
    return cue_track_tag_dicts(image_path, sheet, base_tags=base)


def metadata_stage(context):
    tracks = []
    run_report = getattr(context, "run_report", None)
    staged_album_overrides = getattr(context, "staged_album_overrides", {}) or {}

    log("Metadata", "Reading file tags...", "🏷️")

    for file in context.files:
        tags = read_tags(file)
        if tags:
            source_album = tags.get("album")
            track = normalize_track(tags)
            override_key = filesystem_path_key(os.path.dirname(track.get("path", "")))
            apply_staged_album_override(track, staged_album_overrides.get(override_key))
            track["_source_album"] = source_album
            track["_source_release_type_hint"] = release_type_hint_from_album(source_album)
            tracks.append(track)
        elif run_report:
            run_report.record_skipped_item(file, "Unreadable or unsupported audio metadata")

    # Expand "image + cue" albums: one image file becomes N per-track entries.
    for image_path, sheet in getattr(context, "cue_albums", []):
        for tags in cue_album_track_tags(image_path, sheet):
            source_album = tags.get("album")
            track = normalize_track(tags)
            override_key = filesystem_path_key(os.path.dirname(track.get("path", "")))
            apply_staged_album_override(track, staged_album_overrides.get(override_key))
            track["_source_album"] = source_album
            track["_source_release_type_hint"] = release_type_hint_from_album(source_album)
            tracks.append(track)

    grouped_tracks = {}
    for track in tracks:
        grouped_tracks.setdefault(source_album_group_key(track), []).append(track)

    fallback_album_artists = {
        key: source_album_fallback_artist(group_tracks)
        for key, group_tracks in grouped_tracks.items()
    }
    source_positions = {}
    source_album_snapshots = {
        key: album_report_snapshot(group_tracks[0], fallback_album_artists.get(key))
        for key, group_tracks in grouped_tracks.items()
        if group_tracks
    }
    source_intelligence_snapshots = {
        key: metadata_snapshot(
            group_tracks[0],
            fallback_album_artist=fallback_album_artists.get(key),
            track_count=len(group_tracks),
        )
        for key, group_tracks in grouped_tracks.items()
        if group_tracks
    }

    for group_tracks in grouped_tracks.values():
        for index, track in enumerate(sorted(group_tracks, key=source_track_sort_key), start=1):
            source_positions[id(track)] = index

    musicbrainz_by_album: dict = {}
    deezer_by_album: dict = {}
    resolved_album_metadata: dict = {}
    album_keys = collect_source_album_keys(tracks)

    if album_keys:
        publish_runtime_event(context, {
            "severity": "info",
            "source": "Metadata",
            "type": "matching_phase_started",
            "stage": "metadata_stage",
            "message": f"Matching phase started for {len(album_keys)} albums",
            "payload": {
                "totalAlbums": len(album_keys),
            },
        })

    for key, group_tracks in grouped_tracks.items():
        album_id = source_album_id_for_tracks(group_tracks)
        if not album_id:
            continue
        sample_track = group_tracks[0]
        publish_runtime_event(context, {
            "severity": "info",
            "source": "Metadata",
            "type": "album_processing_started",
            "stage": "metadata_stage",
            "albumId": album_id,
            "message": f"Matching metadata for {sample_track.get('albumartist') or sample_track.get('artist') or 'Unknown'} — {sample_track.get('album') or 'Unknown'}",
            "payload": {
                "progress": "matching",
            },
        })

    def apply_group_resolution(
        key: tuple[str, str],
        musicbrainz_data: dict | None,
        deezer_data: dict | None,
    ) -> None:
        group_tracks = grouped_tracks.get(key, [])
        resolved = resolved_album_metadata.get(key, {})
        provider_winner = str(resolved.get("winner") or "").strip().lower() or None
        if not group_tracks:
            return

        for track in group_tracks:
            artist = track.get("artist")
            album = track.get("album")
            fallback_album_artist = fallback_album_artists.get(key) or artist

            if not (known_album_value(artist) and known_album_value(album)):
                fill_missing_albumartist(track, fallback_album_artist)
                continue

            apply_musicbrainz_date(track, musicbrainz_data)
            apply_musicbrainz_canonical_album_title(track, musicbrainz_data)
            apply_musicbrainz_album_metadata(track, musicbrainz_data)
            apply_release_track_count(track, musicbrainz_data, deezer_data)
            musicbrainz_tracks_match = False
            if musicbrainz_data:
                musicbrainz_tracks = musicbrainz_data.get("tracks", [])
                expected_track_count = musicbrainz_data.get("expected_track_count")
                musicbrainz_tracks_match = bool(
                    musicbrainz_tracks
                    and expected_track_count
                    and len(musicbrainz_tracks) == expected_track_count
                )

            deezer_complete = deezer_album_metadata_complete(deezer_data)
            prefer_deezer = provider_winner != "musicbrainz" and deezer_complete
            preserve_release_type = bool(musicbrainz_data and musicbrainz_data.get("releasetype"))

            if prefer_deezer:
                if musicbrainz_data and musicbrainz_data.get("use_canonical_album_title"):
                    apply_musicbrainz_track_metadata(
                        track,
                        musicbrainz_data,
                        source_position=source_positions.get(id(track)),
                    )
                    apply_transliterated_track_title_fallback(track, musicbrainz_data)
                apply_deezer_metadata(
                    track,
                    deezer_data,
                    source_position=source_positions.get(id(track)),
                    preserve_track_title=bool(musicbrainz_data and musicbrainz_data.get("use_canonical_album_title")),
                    preserve_track_artist=musicbrainz_tracks_match,
                    preserve_album_metadata=bool(musicbrainz_data and musicbrainz_data.get("use_canonical_album_title")),
                    preserve_release_type=preserve_release_type,
                )
            else:
                apply_musicbrainz_track_metadata(
                    track,
                    musicbrainz_data,
                    source_position=source_positions.get(id(track)),
                )
                apply_transliterated_track_title_fallback(track, musicbrainz_data)
                apply_deezer_metadata(
                    track,
                    deezer_data,
                    source_position=source_positions.get(id(track)),
                    preserve_track_artist=musicbrainz_tracks_match,
                    preserve_album_metadata=True,
                    preserve_release_type=preserve_release_type,
                )
            apply_collaboration_artist_fallback(track)
            override_key = filesystem_path_key(os.path.dirname(track.get("path", "")))
            override = staged_album_overrides.get(override_key)
            apply_post_metadata_provider_overrides(track, override, musicbrainz_data, deezer_data)
            apply_post_metadata_album_override(track, override)
            normalize_track_release_dates(track)
            normalize_artist_fields(track)
            fill_missing_albumartist(track, fallback_album_artist)
            track["_metadata_provider"] = provider_winner or metadata_provider_for_resolution(musicbrainz_data, resolved.get("deezer_result"))
            if not track.get("singleoriginaltracknumber"):
                track["singleoriginaltracknumber"] = track.get("tracknumber", 0)

    def emit_group_resolution_events(
        key: tuple[str, str],
        musicbrainz_data: dict | None,
        deezer_data: dict | None,
    ) -> None:
        group_tracks = grouped_tracks.get(key, [])
        if not group_tracks:
            return

        deezer_complete = deezer_album_metadata_complete(deezer_data)
        provider = "deezer" if deezer_complete else ("musicbrainz" if musicbrainz_data else None)
        payload = runtime_album_payload(
            group_tracks,
            processing_state="matching",
            provider=provider,
            complete=False,
        )
        if not payload:
            return
        if deezer_data:
            publish_runtime_event(context, {
                "severity": "success",
                "source": "Metadata",
                "type": "metadata_match",
                "stage": "metadata_stage",
                "albumId": payload["albumId"],
                "message": f"Found a metadata match for {payload['albumPatch']['title']}",
                "payload": payload,
            })
        if musicbrainz_data and not deezer_complete:
            publish_runtime_event(context, {
                "severity": "info",
                "source": "Metadata",
                "type": "fallback_triggered",
                "stage": "metadata_stage",
                "albumId": payload["albumId"],
                "message": f"Falling back to MusicBrainz for {payload['albumPatch']['title']}",
                "payload": payload,
            })
        if not provider or payload["issueCounts"]["warning"] > 0:
            publish_runtime_event(context, {
                "severity": "warning",
                "source": "Metadata",
                "type": "issue_detected",
                "stage": "metadata_stage",
                "albumId": payload["albumId"],
                "message": f"Metadata still needs review for {payload['albumPatch']['title']}",
                "payload": payload,
            })
        publish_runtime_event(context, {
            "severity": "success" if provider else "warning",
            "source": "Metadata",
            "type": "metadata_resolved",
            "stage": "metadata_stage",
            "albumId": payload["albumId"],
            "message": f"Cleaned metadata for {payload['albumPatch']['title']}",
            "payload": payload,
        })

    def emit_provider_fallback_event(signature: tuple[str, str], fallback_payload: dict) -> None:
        group_tracks = grouped_tracks.get(signature, [])
        if not group_tracks:
            return
        runtime_payload = runtime_album_payload(
            group_tracks,
            processing_state="matching",
            provider="musicbrainz",
            complete=False,
        )
        if not runtime_payload:
            return
        publish_runtime_event(context, {
            "severity": "info",
            "source": "Metadata",
            "type": "provider_fallback",
            "stage": "metadata_stage",
            "albumId": runtime_payload["albumId"],
            "message": f"Falling back to MusicBrainz for {runtime_payload['albumPatch']['title']}",
            "payload": {
                **runtime_payload,
                "progress": "matching",
                "provider": {
                    "from": str(fallback_payload.get("from") or "deezer"),
                    "to": str(fallback_payload.get("to") or "musicbrainz"),
                    "reason": str(fallback_payload.get("reason") or "unknown"),
                    "path": str(fallback_payload.get("path") or "musicbrainz-fallback"),
                },
            },
        })

    def on_album_resolved(
        key: tuple[str, str],
        musicbrainz_data: dict | None,
        deezer_data: dict | None,
        resolved: dict,
    ) -> None:
        group_tracks = grouped_tracks.get(key, [])
        if not group_tracks:
            return
        musicbrainz_by_album[key] = musicbrainz_data
        deezer_by_album[key] = deezer_data
        resolved_album_metadata[key] = resolved
        apply_group_resolution(key, musicbrainz_data, deezer_data)
        before_intelligence = source_intelligence_snapshots.get(key)
        after_intelligence = metadata_snapshot(
            group_tracks[0],
            fallback_album_artist=fallback_album_artists.get(key),
            track_count=len(group_tracks),
        )
        override_key = filesystem_path_key(os.path.dirname(group_tracks[0].get("path", "")))
        intelligence = build_metadata_intelligence(
            before=before_intelligence or {},
            after=after_intelligence,
            resolved=resolved,
            override=staged_album_overrides.get(override_key),
            group_tracks=group_tracks,
        )
        for track in group_tracks:
            track["_metadata_intelligence"] = intelligence
        emit_group_resolution_events(key, musicbrainz_data, deezer_data)

    if run_report:
        with run_report.measure("metadata_fetch"):
            fetched_album_metadata = fetch_album_metadata(
                album_keys,
                run_report=run_report,
                on_resolved=on_album_resolved,
                on_fallback=emit_provider_fallback_event,
            )
    else:
        fetched_album_metadata = fetch_album_metadata(
            album_keys,
            on_resolved=on_album_resolved,
            on_fallback=emit_provider_fallback_event,
        )

    if len(fetched_album_metadata) == 3:
        fetched_musicbrainz_by_album, fetched_deezer_by_album, fetched_resolved_album_metadata = fetched_album_metadata
        for key in set(fetched_musicbrainz_by_album) | set(fetched_deezer_by_album):
            if key in musicbrainz_by_album or key not in grouped_tracks:
                continue
            musicbrainz_data = fetched_musicbrainz_by_album.get(key)
            deezer_data = fetched_deezer_by_album.get(key)
            resolved = fetched_resolved_album_metadata.get(key) or {
                "musicbrainz": musicbrainz_data,
                "deezer": deezer_data,
            }
            on_album_resolved(key, musicbrainz_data, deezer_data, resolved)
    elif len(fetched_album_metadata) == 2:
        fetched_musicbrainz_by_album, fetched_deezer_by_album = fetched_album_metadata
        for key in set(fetched_musicbrainz_by_album) | set(fetched_deezer_by_album):
            if key in musicbrainz_by_album or key not in grouped_tracks:
                continue
            musicbrainz_data = fetched_musicbrainz_by_album.get(key)
            deezer_data = fetched_deezer_by_album.get(key)
            on_album_resolved(key, musicbrainz_data, deezer_data, {
                "musicbrainz": musicbrainz_data,
                "deezer": deezer_data,
            })

    if album_keys:
        publish_runtime_event(context, {
            "severity": "info",
            "source": "Metadata",
            "type": "matching_phase_completed",
            "stage": "metadata_stage",
            "message": f"Matching phase completed for {len(resolved_album_metadata)} albums",
            "payload": {
                "resolvedAlbums": len(resolved_album_metadata),
                "totalAlbums": len(album_keys),
            },
        })
    context.resolved_album_metadata = resolved_album_metadata

    if run_report:
        for key, (artist, album, track_count, _track_titles, preferred_release_type, _instructions) in album_keys.items():
            if musicbrainz_by_album.get(key) or deezer_by_album.get(key):
                continue
            run_report.record_unresolved_match(
                artist=artist,
                album=album,
                source_dir=key[0],
                track_count=track_count,
                preferred_release_type=preferred_release_type,
            )

    if run_report:
        for key, group_tracks in grouped_tracks.items():
            if not group_tracks:
                continue
            before = source_album_snapshots.get(key)
            after = album_report_snapshot(group_tracks[0], fallback_album_artists.get(key))
            if before:
                run_report.record_changed_album(
                    key=key,
                    before=before,
                    after=after,
                    track_count=len(group_tracks),
                    album_id=source_album_id_for_tracks(group_tracks),
                    metadata_intelligence=group_tracks[0].get("_metadata_intelligence"),
                )

    context.tracks = tracks
    log("Metadata", f"Cleaned metadata for {len(tracks)} tracks", "🧹")

    return context
