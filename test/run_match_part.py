#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from musorg.core.match_stress_parts import (  # noqa: E402
    DEFAULT_LIBRARY_PATH,
    get_part_config,
    load_parts_manifest,
    run_match_stress_part,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run match-only Deezer/MusicBrainz stress test for a frozen library part.",
    )
    parser.add_argument("part_number", type=int, help="Frozen part number to run, for example 4.")
    parser.add_argument(
        "--library-path",
        default=DEFAULT_LIBRARY_PATH,
        help=f"Library root to scan. Default: {DEFAULT_LIBRARY_PATH}",
    )
    parser.add_argument(
        "--manifest",
        default=str(REPO_ROOT / "test" / "parts_manifest.json"),
        help="Path to the frozen part manifest JSON.",
    )
    parser.add_argument(
        "--results-dir",
        default=str(REPO_ROOT / "test" / "results"),
        help="Directory for checkpoint and report files.",
    )
    parser.add_argument("--workers", default=2, type=int, help="Maximum concurrent provider lookups.")
    parser.add_argument("--limit", type=int, help="Process only the first N grouped lookups.")
    parser.add_argument("--use-cache", action="store_true", help="Allow provider cache reads/writes.")
    parser.add_argument("--include-singles", action="store_true", help="Include synthetic Singles groups in the run.")
    parser.add_argument("--verbose", action="store_true", help="Print provider failure reason aggregates.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_parts_manifest(args.manifest)
    part_config = get_part_config(manifest, args.part_number)
    run_match_stress_part(
        part_config,
        library_path=args.library_path,
        results_dir=args.results_dir,
        workers=args.workers,
        limit=args.limit,
        use_cache=args.use_cache,
        include_singles=args.include_singles,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
