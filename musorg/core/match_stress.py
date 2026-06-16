from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Sequence

from musorg.core.stages.metadata_read import (
    collect_source_album_keys,
    is_singles_bucket_track,
    known_album_value,
    source_album_group_key,
    source_track_sort_key,
    unpack_album_metadata_payload,
)
from musorg.filesystem.scanner import scan_files
from musorg.metadata.normalizer import normalize_track, release_type_hint_from_album
from musorg.metadata.parser import read_tags
from musorg.services.album_match import (
    LookupInput,
    normalized_title_for_matching,
    select_preferred_metadata_provider,
)
from musorg.services.deezer import clear_deezer_cache, get_album_data
from musorg.services.musicbrainz import clear_musicbrainz_caches, fetch_metadata_result
from musorg.utils.debug import set_log_console_enabled, warning


def prepare_track_for_match_stress(tags: dict) -> dict:
    track = normalize_track(tags)
    source_album = tags.get("album")
    track["_source_album"] = source_album
    track["_source_release_type_hint"] = release_type_hint_from_album(source_album)
    return track


def scan_library_tracks(root_path: str) -> list[dict]:
    tracks: list[dict] = []
    for file_path in scan_files(root_path):
        tags = read_tags(file_path)
        if not tags:
            continue
        tracks.append(prepare_track_for_match_stress(tags))
    return tracks


def scan_library_tracks_from_roots(root_paths: Sequence[str]) -> list[dict]:
    tracks: list[dict] = []
    for root_path in root_paths:
        tracks.extend(scan_library_tracks(root_path))
    return tracks


def build_match_stress_groups(tracks: list[dict]) -> list[dict]:
    grouped_tracks: dict[tuple[str, str], list[dict]] = {}
    for track in tracks:
        album = track.get("album")
        if not known_album_value(album):
            continue
        group_key = source_album_group_key(track)
        grouped_tracks.setdefault(group_key, []).append(track)

    album_keys = collect_source_album_keys(tracks)
    entries: list[dict] = []

    for group_key, payload in album_keys.items():
        group_tracks = sorted(grouped_tracks.get(group_key, []), key=source_track_sort_key)
        if not group_tracks:
            continue

        lookup_artist, lookup_album, _track_count, ordered_titles, preferred_release_type, instructions = unpack_album_metadata_payload(payload)
        is_singles_group = is_singles_bucket_track(group_tracks[0])
        local_track_titles = [str(track.get("title") or "") for track in group_tracks]

        entries.append({
            "group_id": f"{group_key[0]}::{group_key[1]}",
            "source_dir": os.path.dirname(group_tracks[0].get("path", "")),
            "lookup_artist": lookup_artist,
            "lookup_album": lookup_album,
            "local_track_count": len(group_tracks),
            "local_track_titles": local_track_titles,
            "lookup_track_titles": [lookup_album] if is_singles_group else list(ordered_titles),
            "lookup_expected_track_count": None if is_singles_group else len(group_tracks),
            "preferred_release_type": (preferred_release_type or ("single" if is_singles_group else None)),
            "is_singles_bucket": is_singles_group,
            "instructions": instructions,
        })

    entries.sort(
        key=lambda entry: (
            entry["source_dir"].lower(),
            entry["lookup_artist"].lower(),
            entry["lookup_album"].lower(),
            entry["group_id"],
        )
    )
    return entries


def provider_track_title_match(metadata: dict | None, title: str | None) -> bool:
    if not metadata or not title:
        return False

    expected = normalized_title_for_matching(title)
    if not expected:
        return False

    for track in metadata.get("tracks") or []:
        actual = normalized_title_for_matching(str(track.get("title") or ""))
        if actual and actual == expected:
            return True

    return False


def provider_report(provider: str, result: dict | None, entry: dict) -> dict:
    normalized_result = result or {"provider": provider, "success": False, "reason": "unknown", "confidence": None, "evidence": None}
    metadata = normalized_result.get("metadata") or {}
    success = bool(normalized_result.get("success"))
    reason = normalized_result.get("reason")

    if success and entry["is_singles_bucket"] and not provider_track_title_match(metadata, entry["lookup_album"]):
        success = False
        reason = "track_title_missing"
        metadata = {}

    tracks = metadata.get("tracks") or []
    matched_track_count = len(tracks) if isinstance(tracks, list) else None

    return {
        "provider": provider,
        "success": success,
        "reason": reason,
        "confidence": normalized_result.get("confidence"),
        "evidence": normalized_result.get("evidence"),
        "album_title": metadata.get("album") or metadata.get("title"),
        "albumartist": metadata.get("albumartist") or metadata.get("artist"),
        "album_id": metadata.get("album_id"),
        "release_date": metadata.get("date_iso") or metadata.get("date"),
        "matched_track_count": matched_track_count,
        "release_type": metadata.get("releasetype") or metadata.get("record_type"),
        "page_url": metadata.get("page_url"),
        "contains_lookup_track": (
            provider_track_title_match(metadata, entry["lookup_album"])
            if entry["is_singles_bucket"] and success
            else None
        ),
    }


def combine_match_results(
    entry: dict,
    deezer_result: dict,
    musicbrainz_result: dict,
    deezer_metadata: dict | None = None,
    musicbrainz_metadata: dict | None = None,
) -> dict:
    deezer_success = bool(deezer_result.get("success"))
    musicbrainz_success = bool(musicbrainz_result.get("success"))
    lookup = LookupInput(
        artist=entry["lookup_artist"],
        album=entry["lookup_album"],
        expected_track_count=entry["lookup_expected_track_count"],
        expected_titles=tuple(entry["lookup_track_titles"]),
        preferred_release_type=(entry.get("preferred_release_type") or "").lower(),
    )

    if deezer_success and musicbrainz_success:
        winner = select_preferred_metadata_provider(
            deezer_metadata,
            musicbrainz_metadata,
            lookup,
        )
        return {"outcome": "both_match", "winner": winner}

    if deezer_success:
        return {"outcome": "deezer_only", "winner": "deezer"}

    if musicbrainz_success:
        return {"outcome": "musicbrainz_only", "winner": "musicbrainz"}

    return {"outcome": "no_match", "winner": None}


def resolve_match_stress_entry(entry: dict, use_cache: bool = False) -> dict:
    deezer_raw = get_album_data(
        entry["lookup_artist"],
        entry["lookup_album"],
        expected_track_count=entry["lookup_expected_track_count"],
        expected_titles=entry["lookup_track_titles"],
        preferred_release_type=entry.get("preferred_release_type"),
        warn_on_miss=False,
        use_cache=use_cache,
    )
    musicbrainz_raw = fetch_metadata_result(
        entry["lookup_artist"],
        entry["lookup_album"],
        expected_track_count=entry["lookup_expected_track_count"],
        expected_titles=entry["lookup_track_titles"],
        preferred_release_type=entry.get("preferred_release_type"),
        use_cache=use_cache,
    )

    deezer_result = provider_report("deezer", deezer_raw, entry)
    musicbrainz_result = provider_report("musicbrainz", musicbrainz_raw, entry)
    combined = combine_match_results(
        entry,
        deezer_result,
        musicbrainz_result,
        deezer_metadata=(deezer_raw or {}).get("metadata"),
        musicbrainz_metadata=(musicbrainz_raw or {}).get("metadata"),
    )

    resolved_entry = dict(entry)
    resolved_entry["deezer"] = deezer_result
    resolved_entry["musicbrainz"] = musicbrainz_result
    resolved_entry["combined"] = combined
    return resolved_entry


def top_failure_reasons(entries: list[dict], provider: str, limit: int = 5) -> list[dict]:
    counts = Counter(
        str(entry[provider].get("reason") or "unknown")
        for entry in entries
        if not entry[provider].get("success")
    )
    return [
        {"reason": reason, "count": count}
        for reason, count in counts.most_common(limit)
    ]


def summarize_match_subset(entries: list[dict]) -> dict:
    total_groups = len(entries)
    deezer_success_count = sum(1 for entry in entries if entry["deezer"]["success"])
    musicbrainz_success_count = sum(1 for entry in entries if entry["musicbrainz"]["success"])
    both_match_count = sum(1 for entry in entries if entry["combined"]["outcome"] == "both_match")
    deezer_only_count = sum(1 for entry in entries if entry["combined"]["outcome"] == "deezer_only")
    deezer_only_catalog_absence_count = sum(
        1
        for entry in entries
        if entry["combined"]["outcome"] == "deezer_only"
        and str(entry.get("musicbrainz", {}).get("reason") or "") == "likely_catalog_absence"
    )
    musicbrainz_only_count = sum(1 for entry in entries if entry["combined"]["outcome"] == "musicbrainz_only")
    no_match_count = sum(1 for entry in entries if entry["combined"]["outcome"] == "no_match")
    combined_success_count = total_groups - no_match_count

    def rate(value: int) -> float:
        if total_groups == 0:
            return 0.0
        return round(value / total_groups, 4)

    return {
        "total_groups": total_groups,
        "deezer_success_count": deezer_success_count,
        "deezer_success_rate": rate(deezer_success_count),
        "musicbrainz_success_count": musicbrainz_success_count,
        "musicbrainz_success_rate": rate(musicbrainz_success_count),
        "combined_success_count": combined_success_count,
        "combined_success_rate": rate(combined_success_count),
        "both_match_count": both_match_count,
        "deezer_only_count": deezer_only_count,
        "deezer_only_catalog_absence_count": deezer_only_catalog_absence_count,
        "musicbrainz_only_count": musicbrainz_only_count,
        "no_match_count": no_match_count,
        "provider_gap": abs(deezer_success_count - musicbrainz_success_count),
    }


def summarize_match_report(entries: list[dict]) -> dict:
    total_groups = len(entries)
    singles_groups = sum(1 for entry in entries if entry["is_singles_bucket"])
    overall = summarize_match_subset(entries)
    non_singles_entries = [entry for entry in entries if not entry["is_singles_bucket"]]
    non_singles = summarize_match_subset(non_singles_entries)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_groups": total_groups,
        "singles_groups": singles_groups,
        "deezer_success_count": overall["deezer_success_count"],
        "deezer_success_rate": overall["deezer_success_rate"],
        "musicbrainz_success_count": overall["musicbrainz_success_count"],
        "musicbrainz_success_rate": overall["musicbrainz_success_rate"],
        "combined_success_count": overall["combined_success_count"],
        "combined_success_rate": overall["combined_success_rate"],
        "both_match_count": overall["both_match_count"],
        "deezer_only_count": overall["deezer_only_count"],
        "deezer_only_catalog_absence_count": overall["deezer_only_catalog_absence_count"],
        "musicbrainz_only_count": overall["musicbrainz_only_count"],
        "no_match_count": overall["no_match_count"],
        "provider_gap": overall["provider_gap"],
        "non_singles": non_singles,
        "top_failure_reasons": {
            "deezer": top_failure_reasons(entries, "deezer"),
            "musicbrainz": top_failure_reasons(entries, "musicbrainz"),
        },
    }


def resolve_match_stress_entries(
    entries: Sequence[dict],
    *,
    workers: int = 2,
    use_cache: bool = False,
    existing_results: Sequence[dict] | None = None,
    on_entry_resolved: Callable[[dict], None] | None = None,
) -> list[dict]:
    existing_by_group_id = {
        str(entry.get("group_id")): entry
        for entry in (existing_results or [])
        if entry.get("group_id")
    }
    resolved_entries: list[dict | None] = [None] * len(entries)
    pending_entries: list[tuple[int, dict]] = []

    for index, entry in enumerate(entries):
        cached_result = existing_by_group_id.get(str(entry.get("group_id")))
        if cached_result is not None:
            resolved_entries[index] = cached_result
            continue
        pending_entries.append((index, entry))

    max_workers = max(1, int(workers or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(resolve_match_stress_entry, entry, use_cache): index
            for index, entry in pending_entries
        }
        entry_by_index = dict(pending_entries)
        for future in as_completed(future_map):
            index = future_map[future]
            try:
                resolved_entry = future.result()
            except Exception as exc:
                # Keep the batch alive: preserve the failed entry with an error
                # marker instead of letting one failure abort every result.
                source_entry = entry_by_index.get(index, {})
                warning("MatchStress", f"Failed to resolve entry {source_entry.get('group_id')}: {exc}")
                resolved_entries[index] = {**source_entry, "error": str(exc)}
                continue
            resolved_entries[index] = resolved_entry
            if on_entry_resolved is not None:
                on_entry_resolved(resolved_entry)

    return [entry for entry in resolved_entries if entry is not None]


def resolve_match_stress_json_path(json_out: str | None) -> str:
    if json_out:
        return os.path.abspath(json_out)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(tempfile.gettempdir(), f"musorg-match-stress-{timestamp}.json")


def write_match_stress_report(report: dict, json_out: str | None = None) -> str:
    output_path = resolve_match_stress_json_path(json_out)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return output_path


def build_match_stress_report(
    entries: list[dict],
    *,
    library_path: str,
    use_cache: bool,
    workers: int,
    limit: int | None = None,
    extra_fields: dict | None = None,
) -> dict:
    report = {
        "library_path": os.path.abspath(library_path),
        "used_cache": bool(use_cache),
        "workers": max(1, int(workers or 1)),
        "limit": limit,
        "summary": summarize_match_report(entries),
        "entries": entries,
    }
    if extra_fields:
        report.update(extra_fields)
    return report


def format_provider_console_value(provider_result: dict | None) -> str:
    result = provider_result or {}
    title = str(result.get("album_title") or "").strip()
    track_count = result.get("matched_track_count")
    reason = str(result.get("reason") or "unknown")

    if result.get("success"):
        if title and track_count is not None:
            return f"{title} ({track_count} tracks)"
        if title:
            return title
        return "success"

    if title and track_count is not None:
        return f"{reason} [{title}, {track_count} tracks]"
    if title:
        return f"{reason} [{title}]"
    return reason


def format_problem_match_line(entry: dict) -> str:
    return (
        f"{entry['lookup_artist']} — {entry['lookup_album']} | "
        f"Deezer: {format_provider_console_value(entry.get('deezer'))} | "
        f"MusicBrainz: {format_provider_console_value(entry.get('musicbrainz'))}"
    )


def format_match_stress_summary(
    summary: dict,
    report_path: str,
    *,
    entries: Sequence[dict] | None = None,
    part_label: str | None = None,
    artist_range: str | None = None,
    processed_groups: int | None = None,
    verbose: bool = False,
) -> str:
    total_groups = int(summary["total_groups"])
    processed = total_groups if processed_groups is None else int(processed_groups)
    lines: list[str] = []

    if part_label:
        lines.append(f"Part {part_label} complete")
    else:
        lines.append("Match stress complete")

    if artist_range:
        lines.append(f"Artist range: {artist_range}")

    lines.append(f"Groups processed: {processed}/{total_groups}")
    lines.append(f"Deezer: {summary['deezer_success_count']}/{total_groups}")
    lines.append(f"MusicBrainz: {summary['musicbrainz_success_count']}/{total_groups}")
    lines.append(f"Combined: {summary['combined_success_count']}/{total_groups}")
    lines.append(f"both_match = {summary['both_match_count']}")
    lines.append(f"deezer_only = {summary['deezer_only_count']}")
    deezer_only_catalog_absence_count = int(summary.get("deezer_only_catalog_absence_count") or 0)
    if deezer_only_catalog_absence_count:
        lines.append(f"deezer_only_catalog_absence = {deezer_only_catalog_absence_count}")
    lines.append(f"musicbrainz_only = {summary['musicbrainz_only_count']}")
    lines.append(f"no_match = {summary['no_match_count']}")
    skipped_singles_groups = int(summary.get("skipped_singles_groups") or 0)
    if skipped_singles_groups:
        lines.append(f"Skipped singles groups: {skipped_singles_groups}")
    non_singles = summary.get("non_singles") or {}
    if non_singles and non_singles.get("total_groups") != summary["total_groups"]:
        lines.append(
            "Albums/non-singles: "
            f"Deezer {non_singles.get('deezer_success_count', 0)}/{non_singles.get('total_groups', 0)}, "
            f"MusicBrainz {non_singles.get('musicbrainz_success_count', 0)}/{non_singles.get('total_groups', 0)}, "
            f"both_match = {non_singles.get('both_match_count', 0)}, "
            f"deezer_only = {non_singles.get('deezer_only_count', 0)}, "
            f"musicbrainz_only = {non_singles.get('musicbrainz_only_count', 0)}, "
            f"provider_gap = {non_singles.get('provider_gap', 0)}"
        )
    lines.append(f"report = {report_path}")

    if entries is not None:
        problem_found = False
        grouped_outcomes = (
            (
                "deezer_only_catalog_absence",
                [
                    entry
                    for entry in entries
                    if str(entry.get("combined", {}).get("outcome")) == "deezer_only"
                    and str(entry.get("musicbrainz", {}).get("reason") or "") == "likely_catalog_absence"
                ],
            ),
            (
                "deezer_only",
                [
                    entry
                    for entry in entries
                    if str(entry.get("combined", {}).get("outcome")) == "deezer_only"
                    and str(entry.get("musicbrainz", {}).get("reason") or "") != "likely_catalog_absence"
                ],
            ),
            (
                "musicbrainz_only",
                [
                    entry
                    for entry in entries
                    if str(entry.get("combined", {}).get("outcome")) == "musicbrainz_only"
                ],
            ),
            (
                "no_match",
                [
                    entry
                    for entry in entries
                    if str(entry.get("combined", {}).get("outcome")) == "no_match"
                ],
            ),
        )
        for outcome, outcome_entries in grouped_outcomes:
            if not outcome_entries:
                continue
            problem_found = True
            lines.append("")
            lines.append(outcome)
            for entry in outcome_entries:
                lines.append(format_problem_match_line(entry))
        if not problem_found:
            lines.append("")
            lines.append("No remaining problem matches in this part.")

    if verbose:
        deezer_reasons = ", ".join(
            f"{item['reason']}={item['count']}"
            for item in summary["top_failure_reasons"]["deezer"]
        ) or "none"
        musicbrainz_reasons = ", ".join(
            f"{item['reason']}={item['count']}"
            for item in summary["top_failure_reasons"]["musicbrainz"]
        ) or "none"
        lines.append("")
        lines.append(f"Top Deezer failures: {deezer_reasons}")
        lines.append(f"Top MusicBrainz failures: {musicbrainz_reasons}")

    return "\n".join(lines)


def print_match_stress_summary(
    summary: dict,
    report_path: str,
    *,
    entries: Sequence[dict] | None = None,
    part_label: str | None = None,
    artist_range: str | None = None,
    processed_groups: int | None = None,
    verbose: bool = False,
) -> None:
    print(
        format_match_stress_summary(
            summary,
            report_path,
            entries=entries,
            part_label=part_label,
            artist_range=artist_range,
            processed_groups=processed_groups,
            verbose=verbose,
        )
    )


def run_match_stress(
    root_path: str,
    json_out: str | None = None,
    workers: int = 2,
    limit: int | None = None,
    use_cache: bool = False,
    verbose: bool = False,
) -> dict:
    if not os.path.isdir(root_path):
        raise FileNotFoundError(f"Library path not found: {root_path}")

    clear_deezer_cache()
    clear_musicbrainz_caches()

    previous_console_enabled = set_log_console_enabled(False)
    try:
        tracks = scan_library_tracks(root_path)
        entries = build_match_stress_groups(tracks)
        if limit is not None:
            entries = entries[: max(0, int(limit))]

        max_workers = max(1, int(workers or 1))
        resolved_entries = resolve_match_stress_entries(
            entries,
            workers=max_workers,
            use_cache=use_cache,
        )
        report = build_match_stress_report(
            resolved_entries,
            library_path=root_path,
            use_cache=use_cache,
            workers=max_workers,
            limit=limit,
        )
        report_path = write_match_stress_report(report, json_out=json_out)
    finally:
        set_log_console_enabled(previous_console_enabled)

    print_match_stress_summary(report["summary"], report_path, verbose=verbose)
    report["report_path"] = report_path
    return report
