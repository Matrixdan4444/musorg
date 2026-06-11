from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from musorg.core.match_stress import (
    build_match_stress_groups,
    build_match_stress_report,
    print_match_stress_summary,
    resolve_match_stress_entries,
    scan_library_tracks_from_roots,
    write_match_stress_report,
)
from musorg.services.deezer import clear_deezer_cache
from musorg.services.musicbrainz import clear_musicbrainz_caches
from musorg.utils.debug import set_log_console_enabled

CHECKPOINT_VERSION = 2
DEFAULT_LIBRARY_PATH = "/Volumes/Music"


def load_parts_manifest(manifest_path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(manifest_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid parts manifest: {manifest_path}")
    return payload


def get_part_config(manifest: dict[str, Any], part_number: int) -> dict[str, Any]:
    for part in manifest.get("parts") or []:
        if int(part.get("part_number", -1)) == int(part_number):
            return part
    raise KeyError(f"Unknown part number: {part_number}")


def part_slug(part_config: dict[str, Any]) -> str:
    label = str(part_config["label"]).replace("/", "-of-")
    return f"part-{label}"


def resolve_part_artist_dirs(part_config: dict[str, Any], library_path: str) -> list[str]:
    return [
        os.path.join(library_path, artist_dir)
        for artist_dir in (part_config.get("artist_dirs") or [])
    ]


def checkpoint_paths(results_dir: str, part_config: dict[str, Any]) -> tuple[str, str]:
    slug = part_slug(part_config)
    state_path = os.path.join(results_dir, f"{slug}.state.json")
    report_path = os.path.join(results_dir, f"{slug}.report.json")
    return state_path, report_path


def _load_json(path: str) -> dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return None
    return payload


def load_checkpoint_state(
    state_path: str,
    *,
    part_config: dict[str, Any],
    library_path: str,
    include_singles: bool = False,
) -> dict[str, Any]:
    state = _load_json(state_path)
    if not state:
        return {}

    if int(state.get("checkpoint_version", -1)) != CHECKPOINT_VERSION:
        return {}
    if int(state.get("part_number", -1)) != int(part_config["part_number"]):
        return {}
    if str(state.get("part_label") or "") != str(part_config["label"]):
        return {}
    if os.path.abspath(str(state.get("library_path") or "")) != os.path.abspath(library_path):
        return {}
    if list(state.get("artist_dirs") or []) != list(part_config.get("artist_dirs") or []):
        return {}
    if bool(state.get("included_singles")) != bool(include_singles):
        return {}
    return state


def write_checkpoint_state(state_path: str, state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def save_checkpoint_state(
    state_path: str,
    *,
    part_config: dict[str, Any],
    library_path: str,
    workers: int,
    use_cache: bool,
    include_singles: bool,
    selected_group_count: int,
    entries_by_group_id: dict[str, dict[str, Any]],
) -> None:
    completed_group_ids = sorted(entries_by_group_id)
    payload = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "part_number": int(part_config["part_number"]),
        "part_label": str(part_config["label"]),
        "artist_range": str(part_config.get("artist_range") or ""),
        "artist_dirs": list(part_config.get("artist_dirs") or []),
        "library_path": os.path.abspath(library_path),
        "workers": int(workers),
        "used_cache": bool(use_cache),
        "included_singles": bool(include_singles),
        "selected_group_count": int(selected_group_count),
        "completed_group_count": len(completed_group_ids),
        "completed_group_ids": completed_group_ids,
        "entries_by_group_id": entries_by_group_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_checkpoint_state(state_path, payload)


def run_match_stress_part(
    part_config: dict[str, Any],
    *,
    library_path: str = DEFAULT_LIBRARY_PATH,
    results_dir: str,
    workers: int = 2,
    limit: int | None = None,
    use_cache: bool = False,
    include_singles: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    if not os.path.isdir(library_path):
        raise FileNotFoundError(f"Library path not found: {library_path}")

    artist_paths = resolve_part_artist_dirs(part_config, library_path)
    missing_dirs = [path for path in artist_paths if not os.path.isdir(path)]
    if missing_dirs:
        raise FileNotFoundError(f"Artist paths not found for part {part_config['label']}: {missing_dirs[0]}")

    clear_deezer_cache()
    clear_musicbrainz_caches()

    state_path, report_path = checkpoint_paths(results_dir, part_config)
    previous_console_enabled = set_log_console_enabled(False)
    try:
        tracks = scan_library_tracks_from_roots(artist_paths)
        all_entries = build_match_stress_groups(tracks)
        skipped_singles_groups = 0
        if include_singles:
            entries = all_entries
        else:
            entries = [entry for entry in all_entries if not entry.get("is_singles_bucket")]
            skipped_singles_groups = len(all_entries) - len(entries)
        if limit is not None:
            entries = entries[: max(0, int(limit))]

        state = load_checkpoint_state(
            state_path,
            part_config=part_config,
            library_path=library_path,
            include_singles=include_singles,
        )
        entries_by_group_id = {
            str(group_id): payload
            for group_id, payload in (state.get("entries_by_group_id") or {}).items()
            if group_id
        }

        def on_entry_resolved(resolved_entry: dict[str, Any]) -> None:
            entries_by_group_id[str(resolved_entry["group_id"])] = resolved_entry
            save_checkpoint_state(
                state_path,
                part_config=part_config,
                library_path=library_path,
                workers=workers,
                use_cache=use_cache,
                include_singles=include_singles,
                selected_group_count=len(entries),
                entries_by_group_id=entries_by_group_id,
            )

        resolved_entries = resolve_match_stress_entries(
            entries,
            workers=workers,
            use_cache=use_cache,
            existing_results=list(entries_by_group_id.values()),
            on_entry_resolved=on_entry_resolved,
        )

        report = build_match_stress_report(
            resolved_entries,
            library_path=library_path,
            use_cache=use_cache,
            workers=workers,
            limit=limit,
            extra_fields={
                "part_number": int(part_config["part_number"]),
                "part_label": str(part_config["label"]),
                "artist_dirs": artist_paths,
                "artist_range": str(part_config.get("artist_range") or ""),
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "checkpoint_version": CHECKPOINT_VERSION,
                "completed_group_count": len(resolved_entries),
                "skipped_singles_groups": skipped_singles_groups,
                "included_singles": bool(include_singles),
            },
        )
        report["summary"]["skipped_singles_groups"] = skipped_singles_groups
        report["summary"]["included_singles"] = bool(include_singles)
        report_path = write_match_stress_report(report, json_out=report_path)
        save_checkpoint_state(
            state_path,
            part_config=part_config,
            library_path=library_path,
            workers=workers,
            use_cache=use_cache,
            include_singles=include_singles,
            selected_group_count=len(entries),
            entries_by_group_id={entry["group_id"]: entry for entry in resolved_entries},
        )
    finally:
        set_log_console_enabled(previous_console_enabled)

    print_match_stress_summary(
        report["summary"],
        report_path,
        entries=report["entries"],
        part_label=report["part_label"],
        artist_range=report["artist_range"],
        processed_groups=report["completed_group_count"],
        verbose=verbose,
    )
    report["report_path"] = report_path
    report["state_path"] = state_path
    return report


def repo_root_from_path(path: str | os.PathLike[str]) -> str:
    return str(Path(path).resolve().parents[1])
