import json
import re
import threading
import time
from datetime import datetime

import requests
from rapidfuzz import fuzz

from musorg.core.runtime_state import is_developer_mode
from musorg.metadata.normalizer import normalize_lookup_text_for_matching
from musorg.services.album_match import (
    LookupInput,
    album_query_variants as shared_album_query_variants,
    album_title_variants as shared_album_title_variants,
    album_titles_match as shared_album_titles_match,
    any_artist_matches as shared_any_artist_matches,
    artist_match as shared_artist_match,
    artist_query_variants as shared_artist_query_variants,
    artist_tokens as shared_artist_tokens,
    build_candidate_evidence,
    build_deezer_album_query_plan,
    build_deezer_track_query_plan,
    evidence_confidence,
    latin_transliteration_variants as shared_latin_transliteration_variants,
    locale_track_sequence_title_rescue,
    lookup_input_signature,
    normalize_album_title as shared_normalize_album_title,
    normalize_lookup_text,
    provider_metadata_evidence,
    resolution_failure,
    resolution_success,
    split_credit_names as shared_split_credit_names,
    strict_album_title_match as shared_strict_album_title_match,
    track_title_sequence_score_from_titles,
    version_penalty as shared_version_penalty,
)
from musorg.services.cache import _CACHE_MISS, cache_get, cache_set, serialize_cache_key
from musorg.utils.debug import log, warning


DEEZER_ALBUM_SEARCH_URL = "https://api.deezer.com/search/album"
DEEZER_TRACK_SEARCH_URL = "https://api.deezer.com/search"
DEEZER_ALBUM_URL = "https://api.deezer.com/album/{album_id}"
DEEZER_ALBUM_PAGE_URL = "https://www.deezer.com/en/album/{album_id}"
DEEZER_TRACK_URL = "https://api.deezer.com/track/{track_id}"
REQUEST_HEADERS = {
    "User-Agent": "musorg/0.1 (+https://example.com)",
}
_ALBUM_DATA_CACHE = {}
_ALBUM_DATA_CACHE_NAMESPACE = "deezer.album_data.v2"
REQUEST_TIMEOUT = (5, 20)
REQUEST_MAX_ATTEMPTS = 5
REQUEST_BACKOFF_BASE_SECONDS = 0.75
REQUEST_BACKOFF_MAX_SECONDS = 8.0
RETRIABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_THREAD_LOCAL = threading.local()
ACCEPTED_RECORD_TYPES = {"album", "single", "ep"}
_FULL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ARTIST_CREDIT_SPLIT_RE = re.compile(r"\s*(?:,|&|/|\\| feat\. | ft\. )\s*", re.IGNORECASE)
_NON_CACHEABLE_FAILURE_REASONS = {
    "album_details_unavailable",
    "no_candidates",
    "no_acceptable_candidate",
    "search_unavailable",
    "track_count_mismatch",
    "unknown",
}
GENERIC_BRACKET_HINT_WORDS = {
    "album",
    "cd",
    "disc",
    "digital",
    "ep",
    "lp",
    "release",
    "single",
}
ALBUM_SEARCH_QUERY_BUDGET = 24
ALBUM_SEARCH_CANDIDATE_BUDGET = 80
ALBUM_SEARCH_RESCUE_CANDIDATE_BUDGET = 120
EXACT_ALBUM_RESCUE_QUERY_BUDGET = 6
EXACT_ALBUM_RESCUE_CANDIDATE_BUDGET = 24
TRACK_SEARCH_QUERY_BUDGET = 12
TRACK_SEARCH_CANDIDATE_BUDGET = 20
TRACK_SEARCH_RESCUE_QUERY_BUDGET = 16
TRACK_SEARCH_RESCUE_CANDIDATE_BUDGET = 30
HYDRATED_CANDIDATE_LIMIT = 12
TRACK_PROBE_MAX_TITLES = 4
GENERIC_TRACK_PROBE_TOKENS = {"intro", "outro", "interlude", "skit"}
LOCALE_TITLE_SEQUENCE_RESCUE_SCORE = 95.0


def clear_deezer_cache() -> None:
    _ALBUM_DATA_CACHE.clear()


def deezer_resolution_success(metadata: dict) -> dict:
    lookup = LookupInput(
        artist=str(metadata.get("albumartist") or ""),
        album=str(metadata.get("album") or ""),
        expected_track_count=metadata.get("expected_track_count"),
        expected_titles=tuple(str(track.get("title") or "") for track in metadata.get("tracks", []) if isinstance(track, dict)),
        preferred_release_type=str(metadata.get("releasetype") or ""),
    )
    evidence = provider_metadata_evidence("deezer", metadata, lookup)
    return resolution_success("deezer", metadata, confidence=evidence_confidence(evidence), evidence=evidence)


def deezer_resolution_failure(reason: str, terminal: bool = True) -> dict:
    return resolution_failure("deezer", reason, terminal=terminal)


def deezer_resolution_metadata(result: dict | None) -> dict | None:
    if not result or not result.get("success"):
        return None
    return result.get("metadata")


def normalize_deezer_resolution_result(result: dict | None) -> dict:
    if isinstance(result, dict) and "success" in result and "metadata" in result and "reason" in result:
        return result
    if result is None:
        return deezer_resolution_failure("unknown")
    return deezer_resolution_success(result)


def deezer_failure_is_cacheable(result: dict | None) -> bool:
    normalized = normalize_deezer_resolution_result(result)
    if normalized.get("success"):
        return True
    return str(normalized.get("reason") or "unknown") not in _NON_CACHEABLE_FAILURE_REASONS


def contains_non_ascii_letter(value: str | None) -> bool:
    if not value:
        return False

    return any(char.isalpha() and not char.isascii() for char in value)


def contains_ascii_letter(value: str | None) -> bool:
    if not value:
        return False

    return any(char.isalpha() and char.isascii() for char in value)


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


def latin_transliteration_variants(value: str, limit: int = 32) -> list[str]:
    return shared_latin_transliteration_variants(value, limit=limit)


def artist_match_variants(value: str) -> set[str]:
    normalized = normalize_lookup_text(value)
    variants = {normalized} if normalized else set()
    variants.update(latin_transliteration_variants(value))
    matching_normalized = normalize_lookup_text_for_matching(value)
    if matching_normalized:
        variants.add(matching_normalized)
    variants.update(
        normalize_lookup_text_for_matching(variant)
        for variant in list(variants)
        if variant
    )
    variants.discard("")
    return variants


def iso_to_display_date(value: str | None) -> str | None:
    if not value or not _FULL_DATE_RE.match(value):
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return None


def normalize_album_title(value: str) -> str:
    return shared_normalize_album_title(value)


def album_title_variants(value: str | None) -> set[str]:
    return shared_album_title_variants(value)


def album_titles_match(left: str | None, right: str | None) -> bool:
    return shared_album_titles_match(left, right)


def strict_album_title_match(left: str | None, right: str | None) -> bool:
    return shared_strict_album_title_match(left, right)


def album_query_variants(album: str) -> list[str]:
    return shared_album_query_variants(album)


def artist_tokens(value: str) -> set[str]:
    return shared_artist_tokens(value)


def split_credit_names(value: str | None) -> list[str]:
    return shared_split_credit_names(value)


def append_unique_artist_names(names: list[str], seen: set[str], raw_name: str | None) -> None:
    for name in split_credit_names(raw_name):
        key = normalize_lookup_text(name)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(name)


def artist_match(candidate_artist: str, artist: str) -> tuple[bool, float]:
    return shared_artist_match(candidate_artist, artist)


def canonical_album_artist(album_artist: str | None, requested_artist: str) -> str | None:
    if (
        album_artist
        and contains_non_ascii_letter(requested_artist)
        and contains_ascii_letter(album_artist)
        and not contains_non_ascii_letter(album_artist)
        and artist_match(album_artist, requested_artist)[0]
    ):
        return requested_artist

    return album_artist


def contributor_names(value: dict) -> list[str]:
    names = []
    seen = set()

    for contributor in value.get("contributors", []):
        append_unique_artist_names(names, seen, (contributor.get("name") or "").strip())

    return names


def album_artist_names(album_data: dict) -> list[str]:
    names = []
    seen = set()

    append_unique_artist_names(
        names,
        seen,
        (album_data.get("artist", {}) or {}).get("name", "").strip(),
    )

    for name in contributor_names(album_data):
        key = normalize_lookup_text(name)
        if key and key not in seen:
            seen.add(key)
            names.append(name)

    if len(names) > 1:
        for combined_name in (", ".join(names), " & ".join(names)):
            key = normalize_lookup_text(combined_name)
            if key and key not in seen:
                seen.add(key)
                names.append(combined_name)

    return names


def track_artist_names(track_data: dict) -> list[str]:
    names = []
    seen = set()

    append_unique_artist_names(
        names,
        seen,
        (track_data.get("artist", {}) or {}).get("name", "").strip(),
    )

    for name in contributor_names(track_data):
        key = normalize_lookup_text(name)
        if key and key not in seen:
            seen.add(key)
            names.append(name)

    if len(names) > 1:
        for combined_name in (", ".join(names), " & ".join(names)):
            key = normalize_lookup_text(combined_name)
            if key and key not in seen:
                seen.add(key)
                names.append(combined_name)

    return names


def any_artist_matches(candidate_artists: list[str], artist: str) -> tuple[bool, float]:
    return shared_any_artist_matches(candidate_artists, artist)


def version_penalty(value: str) -> int:
    return shared_version_penalty(value)


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), REQUEST_BACKOFF_MAX_SECONDS))
        except (TypeError, ValueError):
            pass

    return min(
        REQUEST_BACKOFF_MAX_SECONDS,
        REQUEST_BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)),
    )


def is_retriable_status_code(status_code: int | None) -> bool:
    return bool(status_code in RETRIABLE_STATUS_CODES)


def request_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "request_session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        _THREAD_LOCAL.request_session = session
    return session


def request_with_retry(url: str, params: dict | None = None):
    last_error = None

    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            response = request_session().get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            if is_retriable_status_code(response.status_code):
                last_error = requests.HTTPError(
                    f"HTTP {response.status_code} for {url}",
                    response=response,
                )
                if attempt < REQUEST_MAX_ATTEMPTS:
                    time.sleep(retry_delay(attempt, response.headers.get("Retry-After")))
                    continue

            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            if attempt < REQUEST_MAX_ATTEMPTS:
                time.sleep(retry_delay(attempt))
                continue
        except requests.HTTPError as e:
            last_error = e
            response = getattr(e, "response", None)
            status_code = response.status_code if response is not None else None
            if is_retriable_status_code(status_code) and attempt < REQUEST_MAX_ATTEMPTS:
                retry_after = response.headers.get("Retry-After") if response is not None else None
                time.sleep(retry_delay(attempt, retry_after))
                continue
            break
        except requests.RequestException as e:
            last_error = e
            break

    warning("Deezer", f"Request failed after {REQUEST_MAX_ATTEMPTS} attempts: {last_error}")
    return None


def get_json(url: str, params: dict | None = None) -> dict | None:
    response = request_with_retry(url, params=params)
    if not response:
        return None

    try:
        return response.json()
    except ValueError:
        warning("Deezer", f"Invalid JSON response from {url}")
        return None


def get_text(url: str, params: dict | None = None) -> str | None:
    response = request_with_retry(url, params=params)
    if not response:
        return None

    return response.text


def _normalize_deezer_page_date(month: str, day: str, year: str) -> str | None:
    try:
        numeric_year = int(year)
        if len(year) == 2:
            numeric_year += 1900 if numeric_year >= 70 else 2000
        parsed = datetime(int(numeric_year), int(month), int(day))
    except (TypeError, ValueError):
        return None

    return parsed.strftime("%Y-%m-%d")


def extract_deezer_page_release_date(html: str | None) -> str | None:
    if not html:
        return None

    meta_match = re.search(
        r'<meta\s+property="music:release_date"\s+content="(\d{4}-\d{2}-\d{2})"',
        html,
        re.IGNORECASE,
    )
    if meta_match and _FULL_DATE_RE.match(meta_match.group(1)):
        return meta_match.group(1)

    seo_match = re.search(
        r"Release date:\s*(\d{1,2})/(\d{1,2})/(\d{2,4})",
        html,
        re.IGNORECASE,
    )
    if seo_match:
        return _normalize_deezer_page_date(
            seo_match.group(1),
            seo_match.group(2),
            seo_match.group(3),
        )

    return None


def deezer_page_release_date(album_id: int | str | None) -> str | None:
    if not album_id:
        return None

    html = get_text(DEEZER_ALBUM_PAGE_URL.format(album_id=album_id))
    return extract_deezer_page_release_date(html)


def deezer_page_track_title(song: dict) -> str | None:
    title = (song.get("SNG_TITLE") or "").strip()
    version = (song.get("VERSION") or "").strip()
    if title and version and version not in title:
        return f"{title} {version}"
    return title or None


def page_album_tracks(album_id: int) -> list[dict]:
    html = get_text(DEEZER_ALBUM_PAGE_URL.format(album_id=album_id))
    if not html:
        return []

    match = re.search(r"window\.__DZR_APP_STATE__\s*=\s*(\{.*?\})</script>", html, re.S)
    if not match:
        return []

    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    songs = state.get("SONGS", {}).get("data", [])
    tracks = []
    for song in songs:
        try:
            song_album_id = int(song.get("ALB_ID") or 0)
        except (TypeError, ValueError):
            continue

        if song_album_id != album_id:
            continue

        tracks.append({
            "id": int(song.get("SNG_ID") or 0) or None,
            "title": deezer_page_track_title(song),
            "track_position": int(song.get("TRACK_NUMBER") or 0) or None,
            "disk_number": int(song.get("DISK_NUMBER") or 0) or None,
            "artist": {"name": song.get("ART_NAME")},
        })

    return tracks


def hydrate_album_track_pages(album_data: dict | None) -> dict | None:
    if not album_data:
        return album_data

    tracks = album_data.get("tracks")
    if not isinstance(tracks, dict):
        return album_data

    merged_items = list(tracks.get("data", []) or [])
    next_url = tracks.get("next")

    while next_url:
        page = get_json(next_url)
        if not page:
            break

        merged_items.extend(page.get("data", []) or [])
        next_url = page.get("next")

    hydrated_tracks = dict(tracks)
    expected_track_count = album_data.get("nb_tracks") or 0
    if expected_track_count and len(merged_items) < expected_track_count:
        album_id = album_data.get("id")
        page_tracks = page_album_tracks(album_id) if album_id else []
        if len(page_tracks) > len(merged_items):
            merged_items = page_tracks

    hydrated_tracks["data"] = merged_items

    if next_url is None:
        hydrated_tracks.pop("next", None)

    hydrated_album_data = dict(album_data)
    hydrated_album_data["tracks"] = hydrated_tracks
    return hydrated_album_data


def fallback_album_data_from_candidate(candidate: dict | None) -> dict | None:
    if not candidate:
        return None

    album_id = candidate.get("id")
    if not album_id:
        return None

    page_tracks = page_album_tracks(int(album_id))
    if not page_tracks:
        return None

    return {
        "id": album_id,
        "title": candidate.get("title"),
        "artist": candidate.get("artist") or {},
        "contributors": candidate.get("contributors") or [],
        "record_type": candidate.get("record_type"),
        "release_date": candidate.get("release_date"),
        "cover": candidate.get("cover"),
        "cover_small": candidate.get("cover_small"),
        "cover_medium": candidate.get("cover_medium"),
        "cover_big": candidate.get("cover_big"),
        "cover_xl": candidate.get("cover_xl"),
        "genre_id": candidate.get("genre_id"),
        "genres": candidate.get("genres") or {},
        "label": candidate.get("label"),
        "nb_tracks": candidate.get("nb_tracks") or len(page_tracks),
        "tracks": {"data": page_tracks},
    }


def artist_query_variants(artist: str, include_transliteration: bool = True) -> list[str]:
    return shared_artist_query_variants(artist, include_transliteration=include_transliteration)


def album_search_queries(
    artist: str,
    album: str,
    *,
    artist_query_mode: str = "expanded",
    include_album_only_queries: bool = True,
) -> list[str]:
    return [
        plan.query
        for plan in build_deezer_album_query_plan(
            artist,
            album,
            artist_query_mode=artist_query_mode,
            include_album_only_queries=include_album_only_queries,
        )
    ]


def candidate_is_exact_artist_title_match(candidate: dict, artist: str, album: str) -> bool:
    title = candidate.get("title")
    if not strict_album_title_match(title, album):
        return False
    artist_matches, _artist_score = any_artist_matches(album_artist_names(candidate), artist)
    return artist_matches


def search_attempt_debug_entries(attempts: list[tuple[str, str, int | None]]) -> str:
    entries = []
    for query, status, result_count in attempts:
        if status == "results":
            entries.append(f"{query} -> results ({result_count})")
        elif status == "empty":
            entries.append(f"{query} -> empty")
        else:
            entries.append(f"{query} -> {status}")
    return "; ".join(entries)


def load_search_query_results(url: str, query: str) -> tuple[list[dict], bool, tuple[str, str, int | None]]:
    response = request_with_retry(url, params={"q": query})
    if not response:
        return [], False, (query, "request failed", None)

    try:
        payload = response.json()
    except ValueError:
        return [], False, (query, "invalid payload", None)

    if not isinstance(payload, dict):
        return [], False, (query, "invalid payload", None)

    if payload.get("error"):
        return [], False, (query, "error payload", None)

    items = payload.get("data")
    if not isinstance(items, list):
        return [], False, (query, "invalid payload", None)

    if not items:
        return [], True, (query, "empty", 0)

    return items, True, (query, "results", len(items))


def run_search_queries(
    url: str,
    queries: list[str],
    *,
    query_budget: int,
    candidate_budget: int,
    id_field: str,
    exact_match_callback=None,
) -> tuple[list[dict], bool, list[tuple[str, str, int | None]]]:
    results = []
    seen_ids = set()
    saw_valid_response = False
    attempts: list[tuple[str, str, int | None]] = []

    for index, query in enumerate(queries, start=1):
        if index > query_budget:
            break

        items, valid_response, attempt = load_search_query_results(url, query)
        attempts.append(attempt)
        saw_valid_response = saw_valid_response or valid_response

        for item in items:
            item_id = item.get(id_field)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            results.append(item)
            if len(results) >= candidate_budget:
                return results, saw_valid_response, attempts
            if exact_match_callback and exact_match_callback(item):
                return results, saw_valid_response, attempts

    return results, saw_valid_response, attempts


def search_album_candidates_with_status(
    artist: str,
    album: str,
    *,
    artist_query_mode: str = "expanded",
    include_album_only_queries: bool = True,
    query_budget: int = ALBUM_SEARCH_QUERY_BUDGET,
    candidate_budget: int = ALBUM_SEARCH_CANDIDATE_BUDGET,
) -> tuple[list[dict], bool, list[tuple[str, str, int | None]]]:
    queries = album_search_queries(
        artist,
        album,
        artist_query_mode=artist_query_mode,
        include_album_only_queries=include_album_only_queries,
    )

    if artist_query_mode == "exact" and not include_album_only_queries:
        query_budget = min(query_budget, 6)

    return run_search_queries(
        DEEZER_ALBUM_SEARCH_URL,
        queries,
        query_budget=query_budget,
        candidate_budget=candidate_budget,
        id_field="id",
    )


def exact_album_search_queries(artist: str, album: str) -> list[str]:
    cleaned_artist = " ".join((artist or "").split()).strip()
    queries = []
    seen = set()

    for album_variant in [album, *album_query_variants(album)]:
        cleaned_album = " ".join((album_variant or "").split()).strip()
        for query in (
            f'artist:"{cleaned_artist}" album:"{cleaned_album}"',
            f'"{cleaned_artist}" "{cleaned_album}"',
        ):
            if not cleaned_artist or not cleaned_album or query in seen:
                continue
            seen.add(query)
            queries.append(query)

    return queries


def search_exact_album_candidates_with_status(
    artist: str,
    album: str,
) -> tuple[list[dict], bool, list[tuple[str, str, int | None]]]:
    return run_search_queries(
        DEEZER_ALBUM_SEARCH_URL,
        exact_album_search_queries(artist, album),
        query_budget=EXACT_ALBUM_RESCUE_QUERY_BUDGET,
        candidate_budget=EXACT_ALBUM_RESCUE_CANDIDATE_BUDGET,
        id_field="id",
    )


def search_album_candidates(
    artist: str,
    album: str,
    *,
    artist_query_mode: str = "expanded",
    include_album_only_queries: bool = True,
    query_budget: int = ALBUM_SEARCH_QUERY_BUDGET,
    candidate_budget: int = ALBUM_SEARCH_CANDIDATE_BUDGET,
) -> list[dict]:
    results, _saw_valid_response, _attempts = search_album_candidates_with_status(
        artist,
        album,
        artist_query_mode=artist_query_mode,
        include_album_only_queries=include_album_only_queries,
        query_budget=query_budget,
        candidate_budget=candidate_budget,
    )
    return results


def search_track_candidates_with_status(
    artist: str,
    titles: list[str],
    *,
    artist_query_mode: str = "expanded",
    query_budget: int = TRACK_SEARCH_QUERY_BUDGET,
    candidate_budget: int = TRACK_SEARCH_CANDIDATE_BUDGET,
    clamp_exact_budget: bool = True,
) -> tuple[list[dict], bool, list[tuple[str, str, int | None]]]:
    queries = [
        plan.query
        for plan in build_deezer_track_query_plan(
            artist,
            titles,
            artist_query_mode=artist_query_mode,
        )
    ]
    if artist_query_mode == "exact" and clamp_exact_budget:
        query_budget = min(query_budget, 4)

    return run_search_queries(
        DEEZER_TRACK_SEARCH_URL,
        queries,
        query_budget=query_budget,
        candidate_budget=candidate_budget,
        id_field="id",
    )


def search_track_candidates(
    artist: str,
    titles: list[str],
    *,
    artist_query_mode: str = "expanded",
    query_budget: int = TRACK_SEARCH_QUERY_BUDGET,
    candidate_budget: int = TRACK_SEARCH_CANDIDATE_BUDGET,
) -> list[dict]:
    results, _saw_valid_response, _attempts = search_track_candidates_with_status(
        artist,
        titles,
        artist_query_mode=artist_query_mode,
        query_budget=query_budget,
        candidate_budget=candidate_budget,
    )
    return results


def title_match(value: str | None, expected_titles: list[str]) -> bool:
    return any(album_titles_match(value, title) for title in expected_titles)


def normalized_track_probe_title(value: str | None) -> str:
    return normalize_lookup_text(value or "")


def generic_track_probe_title(value: str | None) -> bool:
    tokens = normalized_track_probe_title(value).split()
    if not tokens:
        return True
    return len(tokens) <= 2 and all(token in GENERIC_TRACK_PROBE_TOKENS or token.isdigit() for token in tokens)


def representative_track_titles(expected_titles: list[str] | None, max_titles: int = TRACK_PROBE_MAX_TITLES) -> list[str]:
    if not expected_titles:
        return []

    candidates = []
    seen = set()
    for index, title in enumerate(expected_titles):
        cleaned_title = " ".join((title or "").split()).strip()
        normalized = normalized_track_probe_title(cleaned_title)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append({
            "index": index,
            "title": cleaned_title,
            "normalized": normalized,
            "generic": generic_track_probe_title(cleaned_title),
        })

    if not candidates:
        return []

    pool = [candidate for candidate in candidates if not candidate["generic"]] or candidates
    selected: list[dict] = []
    selected_normalized: list[str] = []

    def try_add(candidate: dict) -> None:
        normalized = candidate["normalized"]
        if normalized in selected_normalized:
            return
        if any(fuzz.ratio(normalized, existing) >= 88 for existing in selected_normalized):
            return
        selected.append(candidate)
        selected_normalized.append(normalized)

    for position in (0, len(pool) // 2, len(pool) - 1):
        try_add(pool[position])
        if len(selected) >= max_titles:
            return [candidate["title"] for candidate in selected[:max_titles]]

    for candidate in sorted(
        pool,
        key=lambda item: (
            len(item["normalized"].split()),
            len(item["normalized"]),
            -item["index"],
        ),
        reverse=True,
    ):
        try_add(candidate)
        if len(selected) >= max_titles:
            break

    if len(selected) < max_titles:
        for candidate in pool:
            if candidate["normalized"] in selected_normalized:
                continue
            selected.append(candidate)
            selected_normalized.append(candidate["normalized"])
            if len(selected) >= max_titles:
                break

    return [candidate["title"] for candidate in selected[:max_titles]]


def pick_album_from_track_candidates(
    candidates: list[dict],
    artist: str,
    album: str,
    titles: list[str],
    *,
    expected_track_count: int | None = None,
    expected_titles: list[str] | None = None,
    preferred_release_type: str | None = None,
) -> dict | None:
    for candidate in candidates:
        track_data = candidate
        track_id = candidate.get("id")
        if track_id:
            fetched_track = get_track(track_id)
            if fetched_track and not fetched_track.get("error"):
                track_data = fetched_track

        if not title_match(track_data.get("title"), titles):
            continue

        artist_matches, _artist_score = any_artist_matches(track_artist_names(track_data), artist)
        if not artist_matches:
            continue

        album_id = (track_data.get("album", {}) or {}).get("id")
        if not album_id:
            continue

        album_data = get_album(album_id)
        if not album_data or album_data.get("error"):
            continue

        evidence = hydrated_candidate_evidence(
            album_data,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
            expected_titles=expected_titles or titles,
        )
        if not evidence.title_match and not hydrated_candidate_is_sequence_title_rescue(evidence):
            continue

        matched = {
            "id": album_id,
            "title": album_data.get("title"),
            "record_type": album_data.get("record_type"),
            "artist": album_data.get("artist"),
            "nb_tracks": album_data.get("nb_tracks"),
            "_album_data": album_data,
            "_matched_by_track": True,
        }
        if hydrated_candidate_is_sequence_title_rescue(evidence):
            matched["_title_rescued_by_sequence"] = True
        return matched

    return None


def album_candidate_score(
    candidate: dict,
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> tuple:
    evidence = build_candidate_evidence(
        candidate_artists=album_artist_names(candidate) or [candidate.get("artist", {}).get("name", "")],
        requested_artist=artist,
        candidate_title=candidate.get("title", ""),
        requested_album=album,
        record_type=(candidate.get("record_type") or "").lower(),
        candidate_track_count=candidate.get("nb_tracks") or 0,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
    )

    return (
        evidence.deezer_rank(),
        evidence,
    )


def album_data_track_titles(album_data: dict | None) -> list[str]:
    if not isinstance(album_data, dict):
        return []

    items = ((album_data.get("tracks") or {}).get("data") or [])
    titles = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title:
            titles.append(title)
    return titles


def hydrated_candidate_evidence(
    album_data: dict,
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
    expected_titles: list[str] | None = None,
):
    track_titles = album_data_track_titles(album_data)
    sequence_score = 0.0
    if expected_titles and track_titles:
        sequence_score = track_title_sequence_score_from_titles(expected_titles, track_titles)

    return build_candidate_evidence(
        candidate_artists=album_artist_names(album_data) or [album_data.get("artist", {}).get("name", "")],
        requested_artist=artist,
        candidate_title=album_data.get("title", ""),
        requested_album=album,
        record_type=(album_data.get("record_type") or "").lower(),
        candidate_track_count=album_data.get("nb_tracks") or 0,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
        track_title_sequence_score=sequence_score,
        completeness_score=1 if track_titles else 0,
    )


def hydrated_album_candidate_score(
    album_data: dict,
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
    expected_titles: list[str] | None = None,
) -> tuple[tuple, object]:
    evidence = hydrated_candidate_evidence(
        album_data,
        artist,
        album,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
        expected_titles=expected_titles,
    )

    return evidence.deezer_rank(), evidence


def candidate_rescue_rank(rank: tuple, evidence) -> tuple:
    return (
        evidence.title_match,
        evidence.artist_match,
        evidence.strict_title_match,
        evidence.exact_track_count,
        evidence.artist_score,
        evidence.title_score,
        rank,
    )


def candidate_title_cluster_match(candidate: dict, album: str) -> bool:
    title = candidate.get("title")
    return album_titles_match(title, album) or strict_album_title_match(title, album)


def hydrated_candidate_is_sequence_title_rescue(evidence) -> bool:
    return locale_track_sequence_title_rescue(
        evidence,
        min_sequence_score=LOCALE_TITLE_SEQUENCE_RESCUE_SCORE,
    )


def hydrate_candidate_pool(
    candidates: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
    expected_titles: list[str] | None = None,
) -> list[tuple[tuple, dict, object]]:
    hydrated_ranked: list[tuple[tuple, dict, object]] = []

    for candidate in candidates[:HYDRATED_CANDIDATE_LIMIT]:
        album_id = candidate.get("id")
        album_data = candidate.get("_album_data")
        if not album_data and album_id:
            album_data = get_album(album_id)
            if album_data and not album_data.get("error"):
                candidate["_album_data"] = album_data

        if not album_data or album_data.get("error"):
            continue

        hydrated_rank, _evidence = hydrated_album_candidate_score(
            album_data,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
            expected_titles=expected_titles,
        )
        candidate["_hydrated_evidence"] = _evidence
        hydrated_ranked.append((hydrated_rank, candidate, _evidence))

    return hydrated_ranked


def merge_candidates(*candidate_lists: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen_ids = set()

    for candidates in candidate_lists:
        for candidate in candidates:
            candidate_id = candidate.get("id")
            if candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            merged.append(candidate)

    return merged


def candidate_track_count(candidate: dict) -> int | None:
    album_data = candidate.get("_album_data") if isinstance(candidate, dict) else None
    track_count = (album_data or {}).get("nb_tracks") if isinstance(album_data, dict) else None
    if track_count:
        return int(track_count)

    value = candidate.get("nb_tracks") if isinstance(candidate, dict) else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def title_artist_matching_candidates(
    candidates: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
) -> list[dict]:
    matching = []
    for candidate in candidates:
        rank, evidence = album_candidate_score(
            candidate,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
        )
        if rank[0] and evidence.title_match and evidence.artist_match:
            matching.append(candidate)
    return matching


def strict_count_mismatch_candidates(
    candidates: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None,
    preferred_release_type: str | None = None,
) -> list[dict]:
    if not expected_track_count:
        return []

    mismatches = []
    for candidate in title_artist_matching_candidates(
        candidates,
        artist,
        album,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
    ):
        track_count = candidate_track_count(candidate)
        if track_count and track_count != expected_track_count:
            mismatches.append(candidate)
    return mismatches


def title_cluster_candidates(candidates: list[dict], album: str) -> list[dict]:
    return [candidate for candidate in candidates if candidate_title_cluster_match(candidate, album)]


def log_developer_hydrated_candidates(
    artist: str,
    album: str,
    candidates: list[dict],
) -> None:
    if not is_developer_mode() or not candidates:
        return

    details = ", ".join(
        f"{candidate.get('id')}:{candidate.get('title')}[{candidate_track_count(candidate) or '?'}]"
        for candidate in candidates[:HYDRATED_CANDIDATE_LIMIT]
    )
    log("Deezer", f"[DEV MODE] Hydrated candidates for {artist} - {album}: {details}", "🧪")


def log_developer_shallow_candidates(
    artist: str,
    album: str,
    candidates: list[dict],
) -> None:
    if not is_developer_mode() or not candidates:
        return

    details = ", ".join(
        f"{candidate.get('id')}:{candidate.get('title')}[{candidate_track_count(candidate) or '?'}]"
        for candidate in candidates[:HYDRATED_CANDIDATE_LIMIT]
    )
    log("Deezer", f"[DEV MODE] Shallow candidates for {artist} - {album}: {details}", "🧪")


def log_developer_rescue_phase(
    artist: str,
    album: str,
    phase: str,
    attempts: list[tuple[str, str, int | None]] | None = None,
) -> None:
    if not is_developer_mode():
        return

    log("Deezer", f"[DEV MODE] Running rescue phase '{phase}' for {artist} - {album}", "🧪")
    if attempts:
        log("Deezer", f"[DEV MODE] {phase} attempts for {artist} - {album}: {search_attempt_debug_entries(attempts)}", "🧪")


def pick_album_candidate(
    candidates: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
    hydrate_candidates: bool = False,
    expected_titles: list[str] | None = None,
) -> dict | None:
    ranked_candidates = []
    rescue_candidates = []

    for candidate in candidates:
        rank, evidence = album_candidate_score(
            candidate,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
        )

        if evidence.title_match or evidence.artist_match or candidate_title_cluster_match(candidate, album):
            rescue_candidates.append((candidate_rescue_rank(rank, evidence), candidate))

        if not rank[0] or not evidence.title_match or not evidence.artist_match:
            continue

        ranked_candidates.append((rank, candidate))

    if ranked_candidates and hydrate_candidates:
        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        rescue_candidates.sort(key=lambda item: item[0], reverse=True)
        hydrate_pool = [candidate for _rank, candidate in ranked_candidates]
        for _rank, candidate in rescue_candidates:
            if candidate in hydrate_pool:
                continue
            hydrate_pool.append(candidate)

        log_developer_shallow_candidates(artist, album, hydrate_pool)
        hydrated_ranked = hydrate_candidate_pool(
            hydrate_pool,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
            expected_titles=expected_titles,
        )
        strict_matches = []
        sequence_rescues = []
        for hydrated_rank, candidate, evidence in hydrated_ranked:
            if evidence.title_match and evidence.artist_match:
                strict_matches.append((hydrated_rank, candidate))
            elif hydrated_candidate_is_sequence_title_rescue(evidence):
                sequence_rescues.append(
                    (
                        evidence.track_title_sequence_score,
                        evidence.artist_score,
                        hydrated_rank,
                        candidate,
                    )
                )

        strict_matches.sort(key=lambda item: item[0], reverse=True)
        log_developer_hydrated_candidates(
            artist,
            album,
            [candidate for _rank, candidate, _evidence in hydrated_ranked],
        )
        if strict_matches:
            return strict_matches[0][1]
        if sequence_rescues:
            sequence_rescues.sort(reverse=True)
            rescued_candidate = sequence_rescues[0][3]
            rescued_candidate["_title_rescued_by_sequence"] = True
            return rescued_candidate

    if ranked_candidates:
        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        return ranked_candidates[0][1]

    if hydrate_candidates and rescue_candidates:
        rescue_candidates.sort(key=lambda item: item[0], reverse=True)
        hydrated_ranked = hydrate_candidate_pool(
            [candidate for _rank, candidate in rescue_candidates],
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
            expected_titles=expected_titles,
        )
        log_developer_hydrated_candidates(
            artist,
            album,
            [candidate for _rank, candidate, _evidence in hydrated_ranked],
        )
        for hydrated_rank, candidate, evidence in sorted(hydrated_ranked, key=lambda item: item[0], reverse=True):
            if evidence.title_match and evidence.artist_match:
                return candidate
            if hydrated_candidate_is_sequence_title_rescue(evidence):
                candidate["_title_rescued_by_sequence"] = True
                return candidate

    for _rescue_rank, candidate in sorted(rescue_candidates, key=lambda item: item[0], reverse=True):
        if not candidate_title_cluster_match(candidate, album):
            continue

        album_id = candidate.get("id")
        if not album_id:
            continue

        album_data = candidate.get("_album_data")
        if not album_data:
            album_data = get_album(album_id)
        if not album_data or album_data.get("error"):
            continue

        candidate["_album_data"] = album_data
        evidence = hydrated_candidate_evidence(
            album_data,
            artist,
            album,
            expected_track_count=expected_track_count,
            preferred_release_type=preferred_release_type,
            expected_titles=expected_titles,
        )
        if evidence.title_match and evidence.artist_match:
            return candidate
        if hydrated_candidate_is_sequence_title_rescue(evidence):
            candidate["_title_rescued_by_sequence"] = True
            return candidate

    return None


def album_details_match(album_data: dict, artist: str, album: str) -> bool:
    album_artists = album_artist_names(album_data)
    album_title = album_data.get("title", "")
    record_type = (album_data.get("record_type") or "").lower()

    if record_type and record_type not in ACCEPTED_RECORD_TYPES:
        return False

    title_matches = album_titles_match(album_title, album)
    artist_matches, _artist_score = any_artist_matches(album_artists, artist)

    return title_matches and artist_matches


def get_album(album_id: int) -> dict | None:
    album_data = get_json(DEEZER_ALBUM_URL.format(album_id=album_id))
    return hydrate_album_track_pages(album_data)


def get_track(track_id: int) -> dict | None:
    return get_json(DEEZER_TRACK_URL.format(track_id=track_id))


def contributor_artist_names(track_data: dict, album_data: dict | None = None) -> str | None:
    names = []
    seen = set()

    main_artist = (track_data.get("artist", {}) or {}).get("name", "").strip()
    append_unique_artist_names(names, seen, main_artist)

    for name in contributor_names(track_data):
        key = normalize_lookup_text(name)
        if not key or key in seen:
            continue

        seen.add(key)
        names.append(name)

    if not names:
        return main_artist or None

    return ", ".join(names)


def format_tracks(album_data: dict) -> list[dict]:
    tracks = []
    album_items = album_data.get("tracks", {}).get("data", [])
    album_has_disc_numbers = any(item.get("disk_number") for item in album_items)

    for index, item in enumerate(album_items, start=1):
        track_data = item
        track_id = item.get("id")
        if track_id:
            fetched_track = get_track(track_id)
            if fetched_track and not fetched_track.get("error"):
                track_data = fetched_track

        discnumber = item.get("disk_number")
        if discnumber is None and album_has_disc_numbers:
            discnumber = track_data.get("disk_number")

        tracks.append({
            "title": item.get("title"),
            "tracknumber": item.get("track_position") or track_data.get("track_position") or index,
            "discnumber": discnumber,
            "artist": contributor_artist_names(track_data, album_data),
        })

    return tracks


def deezer_track_count_matches_expected(
    tracks: list[dict],
    expected_track_count: int | None,
) -> bool:
    if not expected_track_count:
        return True

    return len(tracks) == expected_track_count


def max_discnumber(tracks: list[dict]) -> int:
    max_value = 0
    for track in tracks:
        try:
            max_value = max(max_value, int(track.get("discnumber") or 0))
        except (TypeError, ValueError):
            continue
    return max_value


def genre_value(album_data: dict):
    genres = album_data.get("genres", {}).get("data", [])
    if genres:
        return genres[0].get("name") or genres[0].get("id")

    return album_data.get("genre_id")


def cache_album_resolution_result(cache_key, persistent_cache_key: str, result: dict) -> None:
    normalized_result = normalize_deezer_resolution_result(result)
    if deezer_failure_is_cacheable(normalized_result):
        _ALBUM_DATA_CACHE[cache_key] = normalized_result
        cache_set(_ALBUM_DATA_CACHE_NAMESPACE, persistent_cache_key, normalized_result)
        return

    _ALBUM_DATA_CACHE.pop(cache_key, None)


def search_failure_reason(
    candidates: list[dict],
    *valid_response_flags: bool,
) -> str:
    if not any(valid_response_flags):
        return "search_unavailable"
    if candidates:
        return "no_acceptable_candidate"
    return "no_candidates"


def final_search_failure_reason(
    candidates: list[dict],
    artist: str,
    album: str,
    expected_track_count: int | None,
    preferred_release_type: str | None,
    *valid_response_flags: bool,
) -> str:
    mismatches = strict_count_mismatch_candidates(
        candidates,
        artist,
        album,
        expected_track_count,
        preferred_release_type=preferred_release_type,
    )
    if mismatches:
        return "track_count_mismatch"
    return search_failure_reason(candidates, *valid_response_flags)


def rescue_album_candidate_after_mismatch(
    artist: str,
    album: str,
    expected_track_count: int | None,
    expected_titles: list[str] | None,
    preferred_release_type: str | None,
    artist_query_mode: str,
    include_album_only_queries: bool,
    existing_candidates: list[dict],
) -> tuple[dict | None, list[dict], bool, list[tuple[str, str, int | None]], bool, list[tuple[str, str, int | None]], list[str]]:
    log_developer_rescue_phase(artist, album, "album-mismatch-rescue")
    rescue_candidates, rescue_valid, rescue_attempts = search_album_candidates_with_status(
        artist,
        album,
        artist_query_mode=artist_query_mode,
        include_album_only_queries=include_album_only_queries,
        candidate_budget=ALBUM_SEARCH_RESCUE_CANDIDATE_BUDGET,
    )
    exact_rescue_candidates, exact_rescue_valid, exact_rescue_attempts = search_exact_album_candidates_with_status(artist, album)
    rescue_valid = rescue_valid or exact_rescue_valid
    rescue_attempts.extend(exact_rescue_attempts)
    merged_candidates = merge_candidates(existing_candidates, rescue_candidates, exact_rescue_candidates)
    rescued_candidate = pick_album_candidate(
        merged_candidates,
        artist,
        album,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
        hydrate_candidates=True,
        expected_titles=expected_titles,
    )

    track_titles = representative_track_titles(expected_titles)
    track_search_valid = False
    track_search_attempts: list[tuple[str, str, int | None]] = []
    if track_titles:
        log_developer_rescue_phase(artist, album, "track-probe-rescue")
        track_candidates, track_search_valid, track_search_attempts = search_track_candidates_with_status(
            artist,
            track_titles,
            artist_query_mode=artist_query_mode,
            query_budget=TRACK_SEARCH_RESCUE_QUERY_BUDGET,
            candidate_budget=TRACK_SEARCH_RESCUE_CANDIDATE_BUDGET,
            clamp_exact_budget=False,
        )
        track_candidate = pick_album_from_track_candidates(
            track_candidates,
            artist,
            album,
            track_titles,
            expected_track_count=expected_track_count,
            expected_titles=expected_titles,
            preferred_release_type=preferred_release_type,
        )
        if track_candidate:
            merged_candidates = merge_candidates(merged_candidates, [track_candidate])
            rescued_candidate = pick_album_candidate(
                merged_candidates,
                artist,
                album,
                expected_track_count=expected_track_count,
                preferred_release_type=preferred_release_type,
                hydrate_candidates=True,
                expected_titles=expected_titles,
            )

    return (
        rescued_candidate,
        merged_candidates,
        rescue_valid,
        rescue_attempts,
        track_search_valid,
        track_search_attempts,
        track_titles,
    )


def log_developer_search_attempts(
    artist: str,
    album: str,
    album_attempts: list[tuple[str, str, int | None]],
    track_attempts: list[tuple[str, str, int | None]] | None = None,
) -> None:
    if album_attempts:
        log(
            "Deezer",
            f"[DEV MODE] Album search attempts for {artist} - {album}: {search_attempt_debug_entries(album_attempts)}",
            "🧪",
        )
    if track_attempts:
        log(
            "Deezer",
            f"[DEV MODE] Track search attempts for {artist} - {album}: {search_attempt_debug_entries(track_attempts)}",
            "🧪",
        )


def log_developer_failure_candidates(
    artist: str,
    album: str,
    candidates: list[dict],
    expected_track_count: int | None = None,
) -> None:
    if not is_developer_mode() or not candidates:
        return

    log_developer_shallow_candidates(artist, album, candidates)
    cluster = title_cluster_candidates(candidates, album)
    mismatches = [
        candidate for candidate in cluster
        if expected_track_count and candidate_track_count(candidate) not in (None, expected_track_count)
    ]
    log(
        "Deezer",
        (
            f"[DEV MODE] Candidate clusters for {artist} - {album}: "
            f"title_cluster={len(cluster)}, wrong_count_cluster={len(mismatches)}"
        ),
        "🧪",
    )


def get_album_data(
    artist,
    album,
    expected_track_count: int | None = None,
    expected_titles: list[str] | None = None,
    preferred_release_type: str | None = None,
    warn_on_miss: bool = True,
    artist_query_mode: str = "expanded",
    include_album_only_queries: bool = True,
    include_track_title_fallback: bool = True,
    use_cache: bool = True,
):
    developer_mode = is_developer_mode()
    lookup = LookupInput(
        artist=artist,
        album=album,
        expected_track_count=expected_track_count,
        expected_titles=tuple(title for title in (expected_titles or []) if title),
        preferred_release_type=(preferred_release_type or "").lower(),
    )
    cache_key = (
        *lookup_input_signature(lookup),
        artist_query_mode,
        include_album_only_queries,
        include_track_title_fallback,
    )
    if use_cache and cache_key in _ALBUM_DATA_CACHE:
        cached_result = normalize_deezer_resolution_result(_ALBUM_DATA_CACHE[cache_key])
        if not deezer_failure_is_cacheable(cached_result):
            _ALBUM_DATA_CACHE.pop(cache_key, None)
        elif developer_mode:
            log("Deezer", f"[DEV MODE] Ignoring cached Deezer match for {artist} - {album}", "🧪")
        else:
            return cached_result

    persistent_cache_key = serialize_cache_key(cache_key)
    if not use_cache:
        persistent_value = _CACHE_MISS
    elif developer_mode:
        log("Deezer", f"[DEV MODE] Bypassing Deezer persistent cache read for {artist} - {album}", "🧪")
    else:
        persistent_value = cache_get(_ALBUM_DATA_CACHE_NAMESPACE, persistent_cache_key)
        if persistent_value is not _CACHE_MISS:
            normalized_result = normalize_deezer_resolution_result(persistent_value)
            if deezer_failure_is_cacheable(normalized_result):
                _ALBUM_DATA_CACHE[cache_key] = normalized_result
                return normalized_result

    candidate = None
    candidates, album_search_valid, album_search_attempts = search_album_candidates_with_status(
        artist,
        album,
        artist_query_mode=artist_query_mode,
        include_album_only_queries=include_album_only_queries,
    )
    rescued_by_exact_query = False
    if not candidates:
        rescue_candidates, rescue_valid, rescue_attempts = search_exact_album_candidates_with_status(artist, album)
        if rescue_candidates:
            candidates = rescue_candidates
            rescued_by_exact_query = True
        album_search_valid = album_search_valid or rescue_valid
        album_search_attempts.extend(rescue_attempts)
    candidate = pick_album_candidate(
        candidates,
        artist,
        album,
        expected_track_count=expected_track_count,
        preferred_release_type=preferred_release_type,
        hydrate_candidates=True,
        expected_titles=expected_titles,
    )
    if developer_mode and rescued_by_exact_query and candidate:
        log("Deezer", f"[DEV MODE] Exact album query rescue matched {artist} - {album}", "🧪")

    if not candidate and not include_track_title_fallback:
        reason = final_search_failure_reason(
            candidates,
            artist,
            album,
            expected_track_count,
            preferred_release_type,
            album_search_valid,
        )
        if warn_on_miss:
            if reason == "track_count_mismatch":
                mismatch = strict_count_mismatch_candidates(
                    candidates,
                    artist,
                    album,
                    expected_track_count,
                    preferred_release_type=preferred_release_type,
                )
                mismatch_count = candidate_track_count(mismatch[0]) if mismatch else None
                warning(
                    "Deezer",
                    (
                        "Deezer rejected: track count mismatch "
                        f"(local={expected_track_count}, deezer={mismatch_count or 'unknown'}), "
                        "falling back to MusicBrainz"
                    ),
                )
            elif candidates:
                warning("Deezer", f"No acceptable album match for {artist} - {album} out of {len(candidates)} candidates, falling back to MusicBrainz")
            elif reason == "search_unavailable":
                warning("Deezer", f"Album search unavailable for {artist} - {album}, falling back to MusicBrainz")
            else:
                warning("Deezer", f"No album candidates found for {artist} - {album}, falling back to MusicBrainz")
            if developer_mode:
                log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to {reason} for {artist} - {album}", "🧪")
                log_developer_failure_candidates(artist, album, candidates, expected_track_count=expected_track_count)
                log_developer_search_attempts(artist, album, album_search_attempts)
        result = deezer_resolution_failure(reason)
        if use_cache:
            cache_album_resolution_result(cache_key, persistent_cache_key, result)
        return result

    track_search_valid = False
    track_search_attempts: list[tuple[str, str, int | None]] = []
    if not candidate and include_track_title_fallback:
        track_titles = representative_track_titles(expected_titles) or ([album] if normalize_album_title(album) else [])
        track_candidates, track_search_valid, track_search_attempts = search_track_candidates_with_status(
            artist,
            track_titles,
            artist_query_mode=artist_query_mode,
            clamp_exact_budget=False,
        )
        candidate = pick_album_from_track_candidates(
            track_candidates,
            artist,
            album,
            track_titles,
            expected_track_count=expected_track_count,
            expected_titles=expected_titles,
            preferred_release_type=preferred_release_type,
        )

        if not candidate:
            reason = final_search_failure_reason(
                candidates,
                artist,
                album,
                expected_track_count,
                preferred_release_type,
                album_search_valid,
                track_search_valid,
            )
            if warn_on_miss:
                if reason == "track_count_mismatch":
                    mismatch = strict_count_mismatch_candidates(
                        candidates,
                        artist,
                        album,
                        expected_track_count,
                        preferred_release_type=preferred_release_type,
                    )
                    mismatch_count = candidate_track_count(mismatch[0]) if mismatch else None
                    warning(
                        "Deezer",
                        (
                            "Deezer rejected: track count mismatch "
                            f"(local={expected_track_count}, deezer={mismatch_count or 'unknown'}), "
                            "falling back to MusicBrainz"
                        ),
                    )
                elif candidates:
                    warning("Deezer", f"No acceptable album match for {artist} - {album} out of {len(candidates)} candidates, falling back to MusicBrainz")
                elif reason == "search_unavailable":
                    warning("Deezer", f"Album search unavailable for {artist} - {album}, falling back to MusicBrainz")
                else:
                    warning("Deezer", f"No album candidates found for {artist} - {album}, falling back to MusicBrainz")
                if developer_mode:
                    log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to {reason} for {artist} - {album}", "🧪")
                    log_developer_failure_candidates(artist, album, candidates, expected_track_count=expected_track_count)
                    log_developer_search_attempts(artist, album, album_search_attempts, track_search_attempts)
            result = deezer_resolution_failure(reason)
            if use_cache:
                cache_album_resolution_result(cache_key, persistent_cache_key, result)
            return result

    album_id = candidate.get("id") if candidate else None
    if not album_id:
        reason = final_search_failure_reason(
            candidates,
            artist,
            album,
            expected_track_count,
            preferred_release_type,
            album_search_valid,
            track_search_valid,
        )
        if developer_mode:
            log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to {reason} for {artist} - {album}", "🧪")
            log_developer_failure_candidates(artist, album, candidates, expected_track_count=expected_track_count)
            log_developer_search_attempts(artist, album, album_search_attempts, track_search_attempts)
        result = deezer_resolution_failure(reason)
        if use_cache:
            cache_album_resolution_result(cache_key, persistent_cache_key, result)
        return result

    album_data = candidate.get("_album_data") if candidate else None
    if not album_data:
        album_data = get_album(album_id)
    if not album_data or album_data.get("error"):
        album_data = fallback_album_data_from_candidate(candidate)
    if not album_data or album_data.get("error"):
        warning("Deezer", f"Could not load album details for {artist} - {album}, falling back to MusicBrainz")
        if developer_mode:
            log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to album_details_unavailable for {artist} - {album}", "🧪")
        result = deezer_resolution_failure("album_details_unavailable")
        if use_cache:
            cache_album_resolution_result(cache_key, persistent_cache_key, result)
        return result

    if (
        not (candidate and candidate.get("_matched_by_track"))
        and not (candidate and candidate.get("_title_rescued_by_sequence"))
        and not album_details_match(album_data, artist, album)
    ):
        if not warn_on_miss:
            result = deezer_resolution_failure("album_details_mismatch")
            if use_cache:
                cache_album_resolution_result(cache_key, persistent_cache_key, result)
            return result
        warning("Deezer", f"Album details mismatch for {artist} - {album} (matched #{album_id}), falling back to MusicBrainz")
        if developer_mode:
            log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to album_details_mismatch for {artist} - {album}", "🧪")
        result = deezer_resolution_failure("album_details_mismatch")
        if use_cache:
            cache_album_resolution_result(cache_key, persistent_cache_key, result)
        return result

    tracks = format_tracks(album_data)
    if not isinstance(tracks, list) or not tracks:
        warning("Deezer", f"Invalid Deezer payload for {artist} - {album}, falling back to MusicBrainz")
        if developer_mode:
            log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to invalid_payload for {artist} - {album}", "🧪")
        result = deezer_resolution_failure("invalid_payload")
        if use_cache:
            cache_album_resolution_result(cache_key, persistent_cache_key, result)
        return result

    if not deezer_track_count_matches_expected(tracks, expected_track_count):
        (
            rescued_candidate,
            rescued_candidates,
            rescue_valid,
            rescue_attempts,
            rescue_track_valid,
            rescue_track_attempts,
            rescue_track_titles,
        ) = rescue_album_candidate_after_mismatch(
            artist,
            album,
            expected_track_count,
            expected_titles,
            preferred_release_type,
            artist_query_mode,
            include_album_only_queries,
            candidates,
        )
        candidates = rescued_candidates
        album_search_valid = album_search_valid or rescue_valid
        track_search_valid = track_search_valid or rescue_track_valid
        album_search_attempts.extend(rescue_attempts)
        track_search_attempts.extend(rescue_track_attempts)

        if rescued_candidate and rescued_candidate.get("id") != album_id:
            candidate = rescued_candidate
            album_id = candidate.get("id")
            album_data = candidate.get("_album_data") if candidate else None
            if not album_data and album_id:
                album_data = get_album(album_id)
            if not album_data or album_data.get("error"):
                album_data = fallback_album_data_from_candidate(candidate)
            tracks = format_tracks(album_data) if album_data and not album_data.get("error") else []

        if not deezer_track_count_matches_expected(tracks, expected_track_count):
            warning(
                "Deezer",
                (
                    "Deezer rejected: track count mismatch "
                    f"(local={expected_track_count}, deezer={len(tracks)}), "
                    "falling back to MusicBrainz"
                ),
            )
            if developer_mode:
                log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to track mismatch for {artist} - {album}", "🧪")
                log_developer_failure_candidates(artist, album, candidates, expected_track_count=expected_track_count)
                if rescue_track_titles:
                    log("Deezer", f"[DEV MODE] Representative track probes for {artist} - {album}: {', '.join(rescue_track_titles)}", "🧪")
                log_developer_search_attempts(artist, album, album_search_attempts, track_search_attempts)
            result = deezer_resolution_failure("track_count_mismatch")
            if use_cache:
                cache_album_resolution_result(cache_key, persistent_cache_key, result)
            return result

    album_artist = canonical_album_artist(album_data.get("artist", {}).get("name"), artist)
    album_title = album_data.get("title") or album
    release_date_iso = album_data.get("release_date")
    genre = genre_value(album_data)

    log(
        "Deezer",
        f"Deezer match found for {artist} — {album_title} ({len(tracks)} tracks)",
        "🎧",
    )

    metadata = {
        "albumartist": album_artist,
        "album": album_title,
        "album_id": album_data.get("id") or album_id,
        "cover": album_data.get("cover_xl") or album_data.get("cover_big"),
        "date": iso_to_display_date(release_date_iso),
        "date_iso": release_date_iso,
        "expected_track_count": expected_track_count,
        "genre": genre,
        "page_url": DEEZER_ALBUM_PAGE_URL.format(album_id=album_data.get("id") or album_id),
        "max_discnumber": max_discnumber(tracks),
        "releasetype": (album_data.get("record_type") or "").lower(),
        "tracks": tracks,
    }
    if (
        not metadata.get("albumartist")
        or not metadata.get("releasetype")
        or not isinstance(metadata.get("tracks"), list)
        or not metadata.get("tracks")
    ):
        warning("Deezer", f"Partial album payload for {artist} - {album}, falling back to MusicBrainz")
        if developer_mode:
            log("Deezer", f"[DEV MODE] Falling back to MusicBrainz due to partial_payload for {artist} - {album}", "🧪")
        result = deezer_resolution_failure("partial_payload")
        cache_album_resolution_result(cache_key, persistent_cache_key, result)
        return result

    evidence = provider_metadata_evidence("deezer", metadata, lookup)
    result = resolution_success("deezer", metadata, confidence=evidence_confidence(evidence), evidence=evidence)
    if developer_mode:
        log("Deezer", f"[DEV MODE] Writing fresh Deezer metadata to cache for {artist} - {album}", "🧪")
    if use_cache:
        cache_album_resolution_result(cache_key, persistent_cache_key, result)
    return result
