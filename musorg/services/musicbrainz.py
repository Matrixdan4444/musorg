import re
import socket
import ssl
import time
from datetime import datetime
from urllib.request import HTTPSHandler

import certifi
import musicbrainzngs
import musicbrainzngs.musicbrainz as musicbrainz_module
from rapidfuzz import fuzz
from musicbrainzngs import compat as musicbrainz_compat

from musorg.core.runtime_state import is_developer_mode
from musorg.metadata.normalizer import (
    VERSION_WORDS,
    normalize_lookup_text_for_matching,
)
from musorg.services.album_match import (
    LookupInput,
    album_query_variants as shared_album_query_variants,
    album_title_variants as shared_album_title_variants,
    build_candidate_evidence,
    evidence_confidence,
    lookup_input_signature,
    metadata_completeness_score,
    normalize_lookup_text,
    locale_track_sequence_title_rescue,
    normalized_title_for_matching as shared_normalized_title_for_matching,
    provider_metadata_evidence,
    resolution_failure,
    resolution_success,
    russian_transliteration_variant,
    strip_soundtrack_suffix,
    title_variants as shared_title_variants,
)
from musorg.services.cache import _CACHE_MISS, cache_get, cache_set, serialize_cache_key
from musorg.utils.debug import log, error


musicbrainzngs.set_useragent("musorg", "0.1", "test@example.com")

_METADATA_CACHE = {}
_ORIGINAL_RELEASE_DATE_CACHE = {}
_DIRECT_RELEASE_GROUP_MATCH_CACHE = {}
_ARTIST_CACHE = {}
_ARTIST_RELEASE_GROUP_CACHE = {}
_FULL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ACCEPTED_PRIMARY_TYPES = {"album", "single", "ep", "compilation"}
_COVER_ART_ARCHIVE_FRONT_URL = "https://coverartarchive.org/release/{release_id}/front-500"
_METADATA_CACHE_NAMESPACE = "musicbrainz.metadata"
_ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE = "musicbrainz.original_release_date"
MUSICBRAINZ_MAX_ATTEMPTS = 4
MUSICBRAINZ_BACKOFF_BASE_SECONDS = 1.0
MUSICBRAINZ_BACKOFF_MAX_SECONDS = 10.0
MUSICBRAINZ_RETRIABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
RELEASE_OVERRIDES = {
    ("аффинаж", "русские песни послесловие"): "1cef9041-5355-4101-ab52-93e0839251ec",
}
_ORIGINAL_BUILD_OPENER = musicbrainz_compat.build_opener
_ORIGINAL_SAFE_READ = musicbrainz_module._safe_read
_MUSICBRAINZ_TLS_CONFIGURED = False
MUSICBRAINZ_REQUEST_TIMEOUT_SECONDS = 12.0
MUSICBRAINZ_SOCKET_MAX_RETRIES = 1
MUSICBRAINZ_SOCKET_RETRY_DELAY_SECONDS = 0.5
TRACK_RESCUE_RELEASE_GROUP_LIMIT = 12


class _MusicBrainzTimeoutOpener:
    def __init__(self, opener, timeout: float):
        self._opener = opener
        self._timeout = timeout

    def open(self, fullurl, data=None, timeout=None):
        effective_timeout = self._timeout if timeout is None else timeout
        return self._opener.open(fullurl, data=data, timeout=effective_timeout)

    def __getattr__(self, name):
        return getattr(self._opener, name)


def clear_musicbrainz_caches() -> None:
    _METADATA_CACHE.clear()
    _ORIGINAL_RELEASE_DATE_CACHE.clear()
    _DIRECT_RELEASE_GROUP_MATCH_CACHE.clear()
    _ARTIST_CACHE.clear()
    _ARTIST_RELEASE_GROUP_CACHE.clear()


def _build_musicbrainz_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _build_musicbrainz_opener(*handlers):
    has_https_handler = any(isinstance(handler, HTTPSHandler) for handler in handlers)
    if not has_https_handler:
        handlers = (*handlers, HTTPSHandler(context=_build_musicbrainz_ssl_context()))
    return _MusicBrainzTimeoutOpener(
        _ORIGINAL_BUILD_OPENER(*handlers),
        MUSICBRAINZ_REQUEST_TIMEOUT_SECONDS,
    )


def _safe_musicbrainz_read(opener, req, body=None, max_retries=8, retry_delay_delta=2.0):
    return _ORIGINAL_SAFE_READ(
        opener,
        req,
        body=body,
        max_retries=MUSICBRAINZ_SOCKET_MAX_RETRIES,
        retry_delay_delta=MUSICBRAINZ_SOCKET_RETRY_DELAY_SECONDS,
    )


def _configure_musicbrainz_tls() -> None:
    global _MUSICBRAINZ_TLS_CONFIGURED
    if _MUSICBRAINZ_TLS_CONFIGURED:
        return
    musicbrainz_compat.build_opener = _build_musicbrainz_opener
    musicbrainz_module._safe_read = _safe_musicbrainz_read
    _MUSICBRAINZ_TLS_CONFIGURED = True


_configure_musicbrainz_tls()


def musicbrainz_retry_delay(attempt: int, retry_after: str | None = None) -> float:
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), MUSICBRAINZ_BACKOFF_MAX_SECONDS))
        except (TypeError, ValueError):
            pass

    return min(
        MUSICBRAINZ_BACKOFF_MAX_SECONDS,
        MUSICBRAINZ_BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)),
    )


def musicbrainz_status_code(exc: Exception) -> int | None:
    for candidate in (exc, getattr(exc, "cause", None)):
        if candidate is None:
            continue

        code = getattr(candidate, "code", None)
        if isinstance(code, int):
            return code

        status = getattr(candidate, "status", None)
        if isinstance(status, int):
            return status

    return None


def musicbrainz_retry_after(exc: Exception) -> str | None:
    for candidate in (exc, getattr(exc, "cause", None)):
        headers = getattr(candidate, "headers", None)
        if headers and headers.get("Retry-After"):
            return headers.get("Retry-After")
    return None


def is_retriable_musicbrainz_error(exc: Exception) -> bool:
    if isinstance(exc, musicbrainzngs.NetworkError):
        return True

    if isinstance(exc, musicbrainzngs.ResponseError):
        status_code = musicbrainz_status_code(exc)
        return status_code in MUSICBRAINZ_RETRIABLE_STATUS_CODES

    return False


def musicbrainz_call(operation_name: str, request_callable, *args, **kwargs):
    last_error = None

    for attempt in range(1, MUSICBRAINZ_MAX_ATTEMPTS + 1):
        try:
            return request_callable(*args, **kwargs)
        except (musicbrainzngs.NetworkError, musicbrainzngs.ResponseError) as exc:
            last_error = exc
            if not is_retriable_musicbrainz_error(exc) or attempt >= MUSICBRAINZ_MAX_ATTEMPTS:
                break

            time.sleep(musicbrainz_retry_delay(attempt, musicbrainz_retry_after(exc)))
        except socket.timeout as exc:
            last_error = musicbrainzngs.NetworkError(cause=exc)
            if attempt >= MUSICBRAINZ_MAX_ATTEMPTS:
                break
            time.sleep(musicbrainz_retry_delay(attempt))
        except Exception as exc:
            last_error = exc
            break

    raise last_error


def title_variants(value: str) -> set[str]:
    return shared_title_variants(value)


def normalized_title_for_matching(value: str | None) -> str:
    return shared_normalized_title_for_matching(value)


def is_full_iso_date(value: str) -> bool:
    if not value or not _FULL_DATE_RE.match(value):
        return False

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False

    return True


def iso_to_display_date(value: str) -> str | None:
    if not is_full_iso_date(value):
        return None

    return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")


def date_year(value: str) -> str | None:
    if not value:
        return None

    if is_full_iso_date(value):
        return value[:4]

    if re.match(r"^\d{2}-\d{2}-\d{4}$", value):
        return value[-4:]

    if re.match(r"^\d{4}$", value):
        return value

    return None


def sortable_release_group_date(value: str | None) -> tuple[int, int, int]:
    if is_full_iso_date(value or ""):
        year, month, day = (int(part) for part in value.split("-"))
        return year, month, day

    return 9999, 12, 31


def release_group_type_rank(primary_type: str, expected_track_count: int | None) -> int:
    normalized = (primary_type or "").lower()

    if expected_track_count and expected_track_count > 1:
        if normalized == "album":
            return 3
        if normalized == "ep":
            return 2
        if normalized == "single":
            return 1
        return 0

    if normalized == "single":
        return 3
    if normalized == "ep":
        return 2
    if normalized == "album":
        return 1
    return 0


def release_group_preference_rank(primary_type: str, preferred_release_type: str | None) -> int:
    normalized = (primary_type or "").lower()
    preferred = (preferred_release_type or "").lower()

    if not preferred:
        return 0

    if normalized == preferred:
        return 2

    if preferred == "album" and normalized == "lp":
        return 1

    return 0


def list_value(value: dict, dashed_key: str, plain_key: str) -> list:
    return value.get(dashed_key) or value.get(plain_key) or []


def field_value(value: dict, dashed_key: str, plain_key: str):
    return value.get(dashed_key, value.get(plain_key))


def artist_credit_phrase(rg: dict) -> str | None:
    if not rg:
        return None

    phrase = rg.get("artist-credit-phrase")
    if phrase:
        return phrase

    credit = list_value(rg, "artist-credit", "artist_credit")
    parts = []

    for item in credit:
        if isinstance(item, str):
            parts.append(item)
        else:
            name = item.get("name") or item.get("artist", {}).get("name")
            joinphrase = item.get("joinphrase", "")
            if name:
                parts.append(name)
            if joinphrase:
                parts.append(joinphrase)

    return "".join(parts).strip() or None


def artist_credit_names(value: dict) -> str | None:
    credit = list_value(value, "artist-credit", "artist_credit")
    names = []
    seen = set()

    for item in credit:
        if isinstance(item, str):
            continue

        name = item.get("name") or item.get("artist", {}).get("name")
        if not name:
            continue

        key = normalize_lookup_text(name)
        if not key or key in seen:
            continue

        seen.add(key)
        names.append(name)

    if not names:
        return None

    return ", ".join(names)


def artist_score(artist_data: dict, artist: str) -> tuple:
    artist_name = artist_data.get("name", "")
    normalized_artist = normalize_lookup_text_for_matching(artist)
    normalized_name = normalize_lookup_text_for_matching(artist_name)
    alias_names = {
        normalize_lookup_text_for_matching(alias.get("alias", ""))
        for alias in artist_data.get("alias-list", [])
        if alias.get("alias")
    }

    exact_name = normalized_name == normalized_artist
    alias_match = normalized_artist in alias_names
    fuzzy = fuzz.ratio(normalized_name, normalized_artist)

    return exact_name, alias_match, fuzzy


def resolve_artist_with_status(artist: str) -> tuple[dict | None, bool]:
    normalized_artist = normalize_lookup_text(artist)
    if not normalized_artist:
        return None, True

    if normalized_artist in _ARTIST_CACHE:
        if is_developer_mode():
            log("MusicBrainz", f"[DEV MODE] Ignoring cached artist resolution for {artist}", "🧪")
        else:
            return _ARTIST_CACHE[normalized_artist], True

    try:
        result = musicbrainz_call(
            "search artists",
            musicbrainzngs.search_artists,
            artist=artist,
            limit=10,
        )
    except Exception as e:
        error("MusicBrainz", f"Artist search failed for {artist}: {e}")
        return None, False

    artists = [
        item for item in result.get("artist-list", [])
        if (item.get("type") or "").lower() != "person"
    ]
    if not artists:
        _ARTIST_CACHE[normalized_artist] = None
        return None, True

    scored = [(artist_score(item, artist), item) for item in artists]
    scored.sort(key=lambda item: item[0], reverse=True)

    (exact_name, alias_match, fuzzy), best = scored[0]
    if not (exact_name or alias_match) and fuzzy < 85:
        _ARTIST_CACHE[normalized_artist] = None
        return None, True

    _ARTIST_CACHE[normalized_artist] = best
    return best, True


def resolve_artist(artist: str) -> dict | None:
    resolved_artist, _valid = resolve_artist_with_status(artist)
    return resolved_artist


def browse_artist_release_groups_with_status(artist_id: str) -> tuple[list[dict], bool]:
    if artist_id in _ARTIST_RELEASE_GROUP_CACHE:
        if is_developer_mode():
            log("MusicBrainz", f"[DEV MODE] Ignoring cached release groups for artist {artist_id}", "🧪")
        else:
            return _ARTIST_RELEASE_GROUP_CACHE[artist_id], True

    release_groups = []
    limit = 100
    offset = 0
    valid = False

    while True:
        try:
            result = musicbrainz_call(
                "browse release groups",
                musicbrainzngs.browse_release_groups,
                artist=artist_id,
                limit=limit,
                offset=offset,
            )
            valid = True
        except Exception as e:
            error("MusicBrainz", f"Could not browse artist release groups: {e}")
            break

        batch = result.get("release-group-list", [])
        release_groups.extend(batch)

        total = result.get("release-group-count", len(release_groups))
        offset += len(batch)

        if not batch or offset >= total:
            break

    if valid:
        _ARTIST_RELEASE_GROUP_CACHE[artist_id] = release_groups
    return release_groups, valid


def browse_artist_release_groups(artist_id: str) -> list[dict]:
    release_groups, _valid = browse_artist_release_groups_with_status(artist_id)
    return release_groups


def release_group_evidence(
    rg: dict,
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
):
    rg_title = rg.get("title", "")
    rg_artist = artist_credit_phrase(rg) or ""
    primary_type = rg.get("primary-type", "").lower()
    return build_candidate_evidence(
        candidate_artists=[rg_artist] if rg_artist else [artist],
        requested_artist=artist,
        candidate_title=rg_title,
        requested_album=album,
        record_type=primary_type,
        candidate_track_count=expected_track_count,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
        completeness_score=metadata_completeness_score(
            {
                "albumartist": rg_artist,
                "album": rg_title,
                "releasetype": primary_type,
                "date_iso": rg.get("first-release-date"),
            }
        ),
    )


def release_group_score(
    rg: dict,
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> tuple:
    rg_artist = artist_credit_phrase(rg) or ""
    primary_type = rg.get("primary-type", "").lower()
    preferred_type_rank = release_group_preference_rank(primary_type, preferred_release_type)
    type_rank = release_group_type_rank(primary_type, expected_track_count)
    first_release_date = sortable_release_group_date(rg.get("first-release-date"))
    evidence = release_group_evidence(
        rg,
        artist,
        album,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    exact_artist = normalize_lookup_text_for_matching(rg_artist) == normalize_lookup_text_for_matching(artist)

    return (
        evidence.strict_title_match,
        evidence.title_match,
        evidence.artist_match,
        exact_artist,
        evidence.is_release,
        preferred_type_rank,
        type_rank,
        evidence.title_score,
        evidence.artist_score,
        evidence.track_title_sequence_score,
        evidence.completeness_score,
        -first_release_date[0],
        -first_release_date[1],
        -first_release_date[2],
    )


def pick_release_group(
    groups: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> dict | None:
    if not groups:
        return None

    album_groups = [
        group for group in groups
        if group.get("primary-type", "").lower() in _ACCEPTED_PRIMARY_TYPES
    ]
    if not album_groups:
        return None

    scored = [
        (
            release_group_score(
                group,
                artist,
                album,
                expected_track_count,
                preferred_release_type=preferred_release_type,
            ),
            group,
        )
        for group in album_groups
    ]
    scored.sort(key=lambda item: item[0], reverse=True)

    (
        exact_title,
        title_match,
        artist_match,
        _exact_artist,
        _is_album,
        _preferred_type_rank,
        _type_rank,
        title_score,
        artist_score,
        _track_title_sequence_score,
        _completeness_score,
        *_date_rank,
    ), group = scored[0]
    if not artist_match and artist_score < 60:
        return None

    if not exact_title and not title_match and title_score < 90:
        return None

    return group


def soundtrack_query_variants(album: str) -> list[tuple[str, bool]]:
    variants: list[tuple[str, bool]] = []
    seen = set()

    def add(value: str | None, used_transliteration: bool = False) -> None:
        cleaned = " ".join((value or "").split()).strip()
        if not cleaned:
            return
        key = (normalize_lookup_text(cleaned), used_transliteration)
        if not key[0] or key in seen:
            return
        seen.add(key)
        variants.append((cleaned, used_transliteration))

    raw_title = " ".join((album or "").split()).strip()
    base_title = strip_soundtrack_suffix(raw_title)
    add(raw_title, False)
    if base_title and normalize_lookup_text(base_title) != normalize_lookup_text(raw_title):
        add(base_title, False)
        add(f"{base_title} OST", False)

    for variant in shared_album_query_variants(raw_title):
        add(variant, False)
    for variant in shared_title_variants(raw_title):
        add(variant, False)
    for variant in shared_album_title_variants(raw_title):
        add(variant, False)

    for value, _used_transliteration in list(variants):
        transliterated = russian_transliteration_variant(value)
        if transliterated:
            add(transliterated, True)

    return variants


def merge_release_groups(*group_lists: list[dict]) -> list[dict]:
    merged = []
    seen_ids = set()

    for groups in group_lists:
        for group in groups:
            group_id = group.get("id")
            if not group_id or group_id in seen_ids:
                continue
            seen_ids.add(group_id)
            merged.append(group)

    return merged


def release_group_search_results_with_status(artist: str, album: str) -> tuple[list[tuple[list[dict], bool]], bool]:
    results: list[tuple[list[dict], bool]] = []
    valid = False

    for releasegroup_query, used_transliteration in soundtrack_query_variants(album):
        try:
            artist_result = musicbrainz_call(
                "search release groups",
                musicbrainzngs.search_release_groups,
                artist=artist,
                releasegroup=releasegroup_query,
                limit=25,
            )
        except Exception as e:
            error("MusicBrainz", f"Search failed for {artist} - {releasegroup_query}: {e}")
        else:
            valid = True
            results.append((artist_result.get("release-group-list", []), used_transliteration))

        try:
            title_result = musicbrainz_call(
                "search release groups",
                musicbrainzngs.search_release_groups,
                releasegroup=releasegroup_query,
                limit=25,
            )
        except Exception as e:
            error("MusicBrainz", f"Title-led search failed for {releasegroup_query}: {e}")
            continue

        valid = True
        results.append((title_result.get("release-group-list", []), used_transliteration))

    return results, valid


def release_group_search_results(artist: str, album: str) -> list[tuple[list[dict], bool]]:
    results, _valid = release_group_search_results_with_status(artist, album)
    return results


def search_release_group_with_status(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> tuple[tuple[dict, bool] | None, bool]:
    resolved_artist, artist_search_valid = resolve_artist_with_status(artist)
    browse_valid = False
    if resolved_artist and resolved_artist.get("id"):
        artist_release_groups, browse_valid = browse_artist_release_groups_with_status(resolved_artist["id"])
        if artist_release_groups:
            release_group = pick_release_group(
                artist_release_groups,
                resolved_artist.get("name") or artist,
                album,
                expected_track_count,
                preferred_release_type=preferred_release_type,
            )
            if release_group:
                if not release_group.get("artist-credit-phrase"):
                    release_group["artist-credit-phrase"] = resolved_artist.get("name")
                return (release_group, False), True

    direct_match, direct_valid = search_release_group_direct_with_status(
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    return direct_match, (artist_search_valid or browse_valid or direct_valid)


def search_release_group(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> tuple[dict, bool] | None:
    match, _valid = search_release_group_with_status(
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    return match


def search_release_group_direct_with_status(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> tuple[tuple[dict, bool] | None, bool]:
    developer_mode = is_developer_mode()
    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=expected_track_count,
        expected_titles=(),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    cache_key = lookup_input_signature(lookup)[:3] + (lookup.preferred_release_type,)
    if cache_key in _DIRECT_RELEASE_GROUP_MATCH_CACHE:
        if developer_mode:
            log("MusicBrainz", f"[DEV MODE] Ignoring cached direct release-group match for {artist} - {album}", "🧪")
        else:
            return _DIRECT_RELEASE_GROUP_MATCH_CACHE[cache_key], True

    search_results, valid = release_group_search_results_with_status(artist, album)
    for groups, used_transliteration in search_results:
        release_group = pick_release_group(
            groups,
            artist,
            album,
            expected_track_count,
            preferred_release_type=preferred_release_type,
        )
        if release_group:
            match = (release_group, used_transliteration)
            _DIRECT_RELEASE_GROUP_MATCH_CACHE[cache_key] = match
            return match, valid

    if valid:
        _DIRECT_RELEASE_GROUP_MATCH_CACHE[cache_key] = None
    return None, valid


def search_release_group_direct(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> tuple[dict, bool] | None:
    match, _valid = search_release_group_direct_with_status(
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    return match


def get_release_group_with_releases(rg_id: str) -> dict | None:
    try:
        result = musicbrainz_call(
            "get release group",
            musicbrainzngs.get_release_group_by_id,
            rg_id,
            includes=["releases"],
        )
    except Exception as e:
        error("MusicBrainz", f"Could not load releases: {e}")
        return None

    return result.get("release-group")


def browse_release_group_releases(rg_id: str) -> list[dict]:
    releases = []
    limit = 100
    offset = 0

    while True:
        try:
            result = musicbrainz_call(
                "browse releases",
                musicbrainzngs.browse_releases,
                release_group=rg_id,
                includes=["media"],
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            error("MusicBrainz", f"Could not browse all releases: {e}")
            break

        batch = result.get("release-list", [])
        releases.extend(batch)

        total = result.get("release-count", len(releases))
        offset += len(batch)

        if not batch or offset >= total:
            break

    return releases


def release_track_count(release: dict) -> int:
    track_count = field_value(release, "track-count", "track_count")
    if track_count is not None:
        try:
            return int(track_count)
        except (TypeError, ValueError):
            pass

    media = list_value(release, "medium-list", "media")
    total = 0
    for medium in media:
        medium_track_count = field_value(medium, "track-count", "track_count")
        try:
            total += int(medium_track_count)
        except (TypeError, ValueError):
            total += len(list_value(medium, "track-list", "tracks"))

    return total


def release_score(release: dict, group_title: str, expected_track_count: int | None) -> tuple:
    status = (release.get("status") or "").lower()
    official = status == "official" or not status
    format_text = normalize_lookup_text(
        " ".join(
            medium.get("format", "")
            for medium in list_value(release, "medium-list", "media")
            if medium.get("format")
        )
    )
    cd_format = "cd" in format_text
    exact_count = bool(expected_track_count and release_track_count(release) == expected_track_count)
    original_title = release_title_is_original(release, group_title)
    date = release.get("date") or ""

    return exact_count, cd_format, official, original_title, date


def pick_track_release(
    releases: list[dict],
    group_title: str,
    expected_track_count: int | None,
) -> dict | None:
    if not releases:
        return None

    candidates = releases
    if expected_track_count:
        exact_count_releases = [
            release for release in releases
            if release_track_count(release) == expected_track_count
        ]
        if exact_count_releases:
            candidates = exact_count_releases

    candidates = sorted(
        candidates,
        key=lambda release: release_score(release, group_title, expected_track_count),
        reverse=True,
    )
    return candidates[0]


def get_release_details(release_id: str) -> dict | None:
    try:
        result = musicbrainz_call(
            "get release",
            musicbrainzngs.get_release_by_id,
            release_id,
            includes=["media", "recordings", "artist-credits"],
        )
    except Exception as e:
        error("MusicBrainz", f"Could not load release tracks: {e}")
        return None

    return result.get("release")


def track_number_value(value) -> int:
    try:
        return int(str(value).split("/")[0])
    except (TypeError, ValueError):
        return 0


def format_release_tracks(release: dict | None) -> list[dict]:
    if not release:
        return []

    tracks = []
    for medium in list_value(release, "medium-list", "media"):
        disc_number = track_number_value(medium.get("position"))
        for track in list_value(medium, "track-list", "tracks"):
            recording = track.get("recording", {})
            title = recording.get("title") or track.get("title")
            artist = artist_credit_names(track) or artist_credit_names(recording)
            track_number = track_number_value(track.get("position") or track.get("number"))

            tracks.append({
                "artist": artist,
                "discnumber": disc_number,
                "title": title,
                "tracknumber": track_number or len(tracks) + 1,
            })

    return tracks


def cover_art_url(release: dict | None) -> str | None:
    if not release:
        return None

    archive = release.get("cover-art-archive") or release.get("cover_art_archive") or {}
    if not archive.get("front"):
        return None

    release_id = release.get("id")
    if not release_id:
        return None

    return _COVER_ART_ARCHIVE_FRONT_URL.format(release_id=release_id)


def normalized_title_sequence(titles: list[str] | None) -> list[str]:
    if not titles:
        return []

    return [
        normalized_title_for_matching(title)
        for title in titles
        if normalized_title_for_matching(title)
    ]


def track_title_sequence_score(expected_titles: list[str], release_details: dict | None) -> float:
    expected = normalized_title_sequence(expected_titles)
    release_titles = [
        track.get("title") or ""
        for track in format_release_tracks(release_details)
    ]
    actual = normalized_title_sequence(release_titles)

    if not expected or len(expected) != len(actual):
        return 0

    scores = [
        fuzz.ratio(expected_title, actual_title)
        for expected_title, actual_title in zip(expected, actual)
    ]
    return sum(scores) / len(scores)


def candidate_release_groups_for_track_rescue(
    groups: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None,
    preferred_release_type: str | None = None,
) -> list[dict]:
    scored_groups = []

    for release_group in groups:
        primary_type = release_group.get("primary-type", "").lower()
        if primary_type not in _ACCEPTED_PRIMARY_TYPES:
            continue
        if preferred_release_type and primary_type != preferred_release_type:
            continue

        evidence = release_group_evidence(
            release_group,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
        )
        if not (
            evidence.strict_title_match
            or evidence.title_match
            or evidence.title_score >= 90
            or evidence.artist_match
        ):
            continue

        scored_groups.append(
            (
                release_group_score(
                    release_group,
                    artist,
                    album,
                    expected_track_count,
                    preferred_release_type=preferred_release_type,
                ),
                release_group,
            )
        )

    scored_groups.sort(key=lambda item: item[0], reverse=True)
    return [group for _score, group in scored_groups[:TRACK_RESCUE_RELEASE_GROUP_LIMIT]]


def find_release_by_track_titles_with_status(
    artist: str,
    album: str,
    expected_track_count: int | None,
    expected_titles: list[str] | None,
    preferred_release_type: str | None = None,
) -> tuple[tuple[dict, dict] | None, bool]:
    if not expected_track_count or not expected_titles:
        return None, False

    best_score = 0
    best_match = None
    best_evidence = None
    candidate_groups: list[dict] = []
    search_valid = False

    resolved_artist, artist_search_valid = resolve_artist_with_status(artist)
    search_valid = search_valid or artist_search_valid
    if resolved_artist and resolved_artist.get("id"):
        browsed_groups, browse_valid = browse_artist_release_groups_with_status(resolved_artist["id"])
        search_valid = search_valid or browse_valid
        candidate_groups = merge_release_groups(
            candidate_groups,
            browsed_groups,
        )

    search_results, release_group_search_valid = release_group_search_results_with_status(artist, album)
    search_valid = search_valid or release_group_search_valid
    candidate_groups = merge_release_groups(
        candidate_groups,
        *[groups for groups, _used_transliteration in search_results],
    )

    for release_group in candidate_release_groups_for_track_rescue(
        candidate_groups,
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    ):
        primary_type = release_group.get("primary-type", "").lower()
        releases = browse_release_group_releases(release_group["id"])
        for release in releases:
            if release_track_count(release) != expected_track_count:
                continue

            release_details = get_release_details(release["id"])
            score = track_title_sequence_score(expected_titles, release_details)
            evidence = build_candidate_evidence(
                candidate_artists=[
                    artist_credit_phrase(release_group)
                    or artist_credit_phrase(release_details)
                    or artist_credit_names(release_details)
                    or artist
                ],
                requested_artist=artist,
                candidate_title=release_group.get("title") or release_details.get("title") or album,
                requested_album=album,
                record_type=primary_type,
                candidate_track_count=expected_track_count,
                expected_track_count=expected_track_count,
                preferred_release_type=preferred_release_type,
                track_title_sequence_score=score,
                completeness_score=metadata_completeness_score(
                    {
                        "albumartist": artist_credit_phrase(release_group) or artist_credit_phrase(release_details),
                        "album": release_group.get("title") or release_details.get("title"),
                        "releasetype": primary_type,
                        "date_iso": release_details.get("date"),
                        "tracks": format_release_tracks(release_details),
                    }
                ),
            )
            if score > best_score and (
                (evidence.title_match and (evidence.artist_match or score >= 96))
                or locale_track_sequence_title_rescue(evidence)
            ):
                best_score = score
                best_match = (release_group, release_details)
                best_evidence = evidence

    if best_score < 90 or not best_evidence:
        return None, search_valid

    return best_match, search_valid


def find_release_by_track_titles(
    artist: str,
    album: str,
    expected_track_count: int | None,
    expected_titles: list[str] | None,
    preferred_release_type: str | None = None,
) -> tuple[dict, dict] | None:
    match, _valid = find_release_by_track_titles_with_status(
        artist,
        album,
        expected_track_count,
        expected_titles,
        preferred_release_type=preferred_release_type,
    )
    return match


def release_title_is_original(release: dict, group_title: str) -> bool:
    release_title = normalize_lookup_text(release.get("title", ""))
    group_title = normalize_lookup_text(group_title)
    if not release_title or release_title == group_title:
        return True

    return not any(word in release_title for word in VERSION_WORDS)


def earliest_full_release_date(release_group: dict) -> str | None:
    if not release_group:
        return None

    releases = release_group.get("release-list", [])
    group_title = release_group.get("title", "")

    official_dates = []
    fallback_dates = []

    for release in releases:
        date = release.get("date")
        if not is_full_iso_date(date):
            continue

        if not release_title_is_original(release, group_title):
            continue

        fallback_dates.append(date)

        status = release.get("status", "")
        if not status or status.lower() == "official":
            official_dates.append(date)

    if official_dates:
        return min(official_dates)

    if fallback_dates:
        return min(fallback_dates)

    return None


def original_release_date(release_group: dict, search_result: dict | None = None) -> str | None:
    group_first_release_date = (
        (release_group or {}).get("first-release-date")
        or (search_result or {}).get("first-release-date")
        or ""
    )
    if is_full_iso_date(group_first_release_date):
        return group_first_release_date

    return earliest_full_release_date(release_group)


def fetch_original_release_date(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    expected_titles: list[str] | None = None,
    preferred_release_type: str | None = None,
    run_report=None,
) -> dict | None:
    developer_mode = is_developer_mode()
    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=expected_track_count,
        expected_titles=tuple(normalized_title_sequence(expected_titles)),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    key = lookup_input_signature(lookup)
    if key in _ORIGINAL_RELEASE_DATE_CACHE:
        if developer_mode:
            log("MusicBrainz", f"[DEV MODE] Ignoring cached MusicBrainz original date for {artist} - {album}", "🧪")
        else:
            if run_report:
                run_report.record_count("metadata_musicbrainz_date_cache_hit")
            return _ORIGINAL_RELEASE_DATE_CACHE[key]

    persistent_cache_key = serialize_cache_key(key)
    if developer_mode:
        log("MusicBrainz", f"[DEV MODE] Bypassing MusicBrainz original date cache read for {artist} - {album}", "🧪")
    else:
        persistent_value = cache_get(_ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE, persistent_cache_key)
        if persistent_value is not _CACHE_MISS:
            _ORIGINAL_RELEASE_DATE_CACHE[key] = persistent_value
            if run_report:
                run_report.record_count("metadata_musicbrainz_date_persistent_cache_hit")
            return persistent_value

    release_group_match = search_release_group_direct(
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    if run_report:
        if release_group_match:
            run_report.record_count("metadata_musicbrainz_date_direct_hit")
        else:
            run_report.record_count("metadata_musicbrainz_date_direct_miss")
    if not release_group_match:
        release_group_match = search_release_group(
            artist,
            album,
            expected_track_count,
            preferred_release_type=preferred_release_type,
        )
        if release_group_match and run_report:
            run_report.record_count("metadata_musicbrainz_date_artist_fallback")
    rg = release_group_match[0] if release_group_match else None

    iso_date = None
    if rg:
        iso_date = original_release_date(rg, rg)
        if not iso_date and rg.get("id"):
            release_group = get_release_group_with_releases(rg["id"]) or dict(rg)
            browsed_releases = browse_release_group_releases(rg["id"])
            if browsed_releases:
                release_group["release-list"] = browsed_releases
            iso_date = original_release_date(release_group, rg)

    if not iso_date:
        _ORIGINAL_RELEASE_DATE_CACHE[key] = None
        cache_set(_ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE, persistent_cache_key, None)
        return None

    metadata = {
        "date": iso_to_display_date(iso_date),
        "date_iso": iso_date,
        "expected_track_count": expected_track_count,
        "year": date_year(iso_date),
    }
    _ORIGINAL_RELEASE_DATE_CACHE[key] = metadata
    cache_set(_ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE, persistent_cache_key, metadata)
    return metadata


def fetch_metadata(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    expected_titles: list[str] | None = None,
    preferred_release_type: str | None = None,
    use_cache: bool = True,
) -> dict | None:
    metadata, _reason = fetch_metadata_with_reason(
        artist,
        album,
        expected_track_count=expected_track_count,
        expected_titles=expected_titles,
        preferred_release_type=preferred_release_type,
        use_cache=use_cache,
    )
    return metadata


def cache_metadata_lookup_result(
    key: tuple,
    persistent_cache_key: str,
    metadata: dict | None,
    *,
    reason: str | None,
    use_cache: bool,
) -> None:
    if not use_cache:
        return
    if metadata is not None:
        _METADATA_CACHE[key] = metadata
        cache_set(_METADATA_CACHE_NAMESPACE, persistent_cache_key, metadata)
        return
    if reason == "no_candidates":
        _METADATA_CACHE[key] = None
        cache_set(_METADATA_CACHE_NAMESPACE, persistent_cache_key, None)
        return
    _METADATA_CACHE.pop(key, None)


def fetch_metadata_with_reason(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    expected_titles: list[str] | None = None,
    preferred_release_type: str | None = None,
    use_cache: bool = True,
) -> tuple[dict | None, str | None]:
    developer_mode = is_developer_mode()
    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=expected_track_count,
        expected_titles=tuple(normalized_title_sequence(expected_titles)),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    key = lookup_input_signature(lookup)
    if use_cache and key in _METADATA_CACHE:
        if developer_mode:
            log("MusicBrainz", f"[DEV MODE] Ignoring cached MusicBrainz metadata for {artist} - {album}", "🧪")
        else:
            cached = _METADATA_CACHE[key]
            return cached, None if cached else "no_candidates"

    persistent_cache_key = serialize_cache_key(key)
    if not use_cache:
        persistent_value = _CACHE_MISS
    elif developer_mode:
        log("MusicBrainz", f"[DEV MODE] Bypassing MusicBrainz persistent cache read for {artist} - {album}", "🧪")
    else:
        persistent_value = cache_get(_METADATA_CACHE_NAMESPACE, persistent_cache_key)
        if persistent_value is not _CACHE_MISS:
            _METADATA_CACHE[key] = persistent_value
            return persistent_value, None if persistent_value else "no_candidates"

    release_override_id = RELEASE_OVERRIDES.get((key[0], normalize_lookup_text(album)))

    release_group_match, release_group_search_valid = search_release_group_with_status(
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    rg = release_group_match[0] if release_group_match else None
    matched_with_transliterated_title = bool(release_group_match and release_group_match[1])
    if not rg:
        tracklist_match, tracklist_search_valid = find_release_by_track_titles_with_status(
            artist,
            album,
            expected_track_count,
            expected_titles,
            preferred_release_type=preferred_release_type,
        )
        if tracklist_match:
            release_group, release_details = tracklist_match
            iso_date = release_details.get("date")
            metadata = {
                "album": release_group.get("title") or release_details.get("title"),
                "albumartist": artist_credit_phrase(release_group) or artist_credit_phrase(release_details),
                "cover": cover_art_url(release_details),
                "date": iso_to_display_date(iso_date) if iso_date else None,
                "date_iso": iso_date,
                "expected_track_count": expected_track_count,
                "year": date_year(iso_date),
                "releasetype": (release_group.get("primary-type") or "").lower(),
                "use_canonical_album_title": False,
                "tracks": format_release_tracks(release_details),
            }
            if metadata["date"]:
                log("MusicBrainz", f"MusicBrainz metadata matched for {artist} — {album} ({metadata['date']})", "🎼")
            if developer_mode:
                log("MusicBrainz", f"[DEV MODE] Writing fresh MusicBrainz metadata to cache for {artist} - {album}", "🧪")
            cache_metadata_lookup_result(key, persistent_cache_key, metadata, reason=None, use_cache=use_cache)
            return metadata, None

        final_reason = "likely_catalog_absence" if (release_group_search_valid or tracklist_search_valid) else "search_unavailable"
        if not release_override_id:
            cache_metadata_lookup_result(key, persistent_cache_key, None, reason=final_reason, use_cache=use_cache)
            return None, final_reason
        release_details = get_release_details(release_override_id)
        if not release_details:
            cache_metadata_lookup_result(key, persistent_cache_key, None, reason=final_reason, use_cache=use_cache)
            return None, final_reason

        iso_date = release_details.get("date")
        metadata = {
            "album": release_details.get("title"),
            "albumartist": artist_credit_phrase(release_details),
            "cover": cover_art_url(release_details),
            "date": iso_to_display_date(iso_date) if iso_date else None,
            "date_iso": iso_date,
            "expected_track_count": expected_track_count,
            "year": date_year(iso_date),
            "releasetype": "album",
            "use_canonical_album_title": False,
            "tracks": format_release_tracks(release_details),
        }
        if developer_mode:
            log("MusicBrainz", f"[DEV MODE] Writing fresh MusicBrainz metadata to cache for {artist} - {album}", "🧪")
        cache_metadata_lookup_result(key, persistent_cache_key, metadata, reason=None, use_cache=use_cache)
        return metadata, None

    release_group = get_release_group_with_releases(rg["id"]) or rg
    browsed_releases = browse_release_group_releases(rg["id"])
    if browsed_releases:
        release_group["release-list"] = browsed_releases

    if release_override_id:
        release_details = get_release_details(release_override_id)
    else:
        track_release = pick_track_release(
            release_group.get("release-list", []),
            release_group.get("title", album),
            expected_track_count,
        )
        release_details = get_release_details(track_release["id"]) if track_release else None
    tracks = format_release_tracks(release_details)

    albumartist = artist_credit_phrase(release_group) or artist_credit_phrase(rg)
    iso_date = original_release_date(release_group, rg)
    display_date = iso_to_display_date(iso_date) if iso_date else None
    release_type = (
        release_group.get("primary-type")
        or rg.get("primary-type")
        or ""
    ).lower()

    metadata = {
        "album": release_group.get("title") or rg.get("title"),
        "albumartist": albumartist,
        "cover": cover_art_url(release_details),
        "date": display_date,
        "date_iso": iso_date,
        "expected_track_count": expected_track_count,
        "year": date_year(iso_date),
        "releasetype": release_type,
        "use_canonical_album_title": matched_with_transliterated_title,
        "tracks": tracks,
    }

    if display_date:
        log("MusicBrainz", f"MusicBrainz metadata matched for {artist} — {album} ({display_date})", "🎼")

    if developer_mode:
        log("MusicBrainz", f"[DEV MODE] Writing fresh MusicBrainz metadata to cache for {artist} - {album}", "🧪")
    cache_metadata_lookup_result(key, persistent_cache_key, metadata, reason=None, use_cache=use_cache)
    return metadata, None


def fetch_metadata_result(
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    expected_titles: list[str] | None = None,
    preferred_release_type: str | None = None,
    use_cache: bool = True,
) -> dict:
    metadata, reason = fetch_metadata_with_reason(
        artist,
        album,
        expected_track_count=expected_track_count,
        expected_titles=expected_titles,
        preferred_release_type=preferred_release_type,
        use_cache=use_cache,
    )
    if not metadata:
        return resolution_failure("musicbrainz", reason or "no_candidates")

    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=expected_track_count,
        expected_titles=tuple(expected_titles or []),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    evidence = provider_metadata_evidence("musicbrainz", metadata, lookup)
    return resolution_success("musicbrainz", metadata, confidence=evidence_confidence(evidence), evidence=evidence)
