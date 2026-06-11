import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from musorg.core.match_stress import format_match_stress_summary, summarize_match_report
from musorg.core.match_stress_parts import (
    checkpoint_paths,
    get_part_config,
    load_parts_manifest,
    run_match_stress_part,
    save_checkpoint_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "test" / "parts_manifest.json"


def _resolved_entry(
    group_id: str,
    outcome: str,
    *,
    deezer_success: bool,
    musicbrainz_success: bool,
    deezer_reason: str | None = None,
    musicbrainz_reason: str | None = None,
) -> dict:
    return {
        "group_id": group_id,
        "lookup_artist": "Artist",
        "lookup_album": f"Album {group_id}",
        "is_singles_bucket": False,
        "deezer": {
            "success": deezer_success,
            "reason": None if deezer_success else (deezer_reason or "no_candidates"),
            "album_title": "Deezer Album" if deezer_success else None,
            "matched_track_count": 10 if deezer_success else None,
        },
        "musicbrainz": {
            "success": musicbrainz_success,
            "reason": None if musicbrainz_success else (musicbrainz_reason or "no_candidates"),
            "album_title": "MB Album" if musicbrainz_success else None,
            "matched_track_count": 10 if musicbrainz_success else None,
        },
        "combined": {
            "outcome": outcome,
            "winner": "deezer" if outcome == "deezer_only" else "musicbrainz" if outcome == "musicbrainz_only" else None,
        },
    }


def _resolved_single_entry(group_id: str, outcome: str, *, deezer_success: bool, musicbrainz_success: bool) -> dict:
    entry = _resolved_entry(group_id, outcome, deezer_success=deezer_success, musicbrainz_success=musicbrainz_success)
    entry["is_singles_bucket"] = True
    return entry


class MatchStressPartManifestTests(unittest.TestCase):
    def test_manifest_contains_parts_four_through_ten_with_ranges(self):
        manifest = load_parts_manifest(MANIFEST_PATH)

        self.assertEqual([part["part_number"] for part in manifest["parts"]], [4, 5, 6, 7, 8, 9, 10])
        for part_number in range(4, 11):
            part = get_part_config(manifest, part_number)
            self.assertTrue(part["artist_range"])
            self.assertTrue(part["artist_dirs"])
            self.assertGreater(part["group_count"], 0)


class MatchStressPartResumeTests(unittest.TestCase):
    @patch("musorg.core.match_stress_parts.set_log_console_enabled", side_effect=[True, False])
    @patch("musorg.core.match_stress_parts.clear_musicbrainz_caches")
    @patch("musorg.core.match_stress_parts.clear_deezer_cache")
    @patch("musorg.core.match_stress_parts.build_match_stress_groups")
    @patch("musorg.core.match_stress_parts.scan_library_tracks_from_roots")
    @patch("musorg.core.match_stress_parts.resolve_match_stress_entries")
    def test_run_match_stress_part_resumes_from_checkpoint(
        self,
        resolve_entries_mock,
        scan_tracks_mock,
        build_groups_mock,
        clear_deezer_cache_mock,
        clear_musicbrainz_cache_mock,
        set_log_console_enabled_mock,
    ):
        del scan_tracks_mock
        part_config = {
            "part_number": 4,
            "label": "4/10",
            "artist_range": "Artist A - Artist B",
            "artist_dirs": ["Artist A", "Artist B"],
        }
        lookup_entries = [
            {"group_id": "group-1", "lookup_artist": "Artist", "lookup_album": "Album 1"},
            {"group_id": "group-2", "lookup_artist": "Artist", "lookup_album": "Album 2"},
        ]
        build_groups_mock.return_value = lookup_entries
        existing_entry = _resolved_entry("group-1", "deezer_only", deezer_success=True, musicbrainz_success=False)
        new_entry = _resolved_entry("group-2", "both_match", deezer_success=True, musicbrainz_success=True)

        def resolve_side_effect(entries, **kwargs):
            self.assertEqual(entries, lookup_entries)
            self.assertEqual([entry["group_id"] for entry in kwargs["existing_results"]], ["group-1"])
            kwargs["on_entry_resolved"](new_entry)
            return [existing_entry, new_entry]

        resolve_entries_mock.side_effect = resolve_side_effect

        with tempfile.TemporaryDirectory() as temp_dir:
            library_path = os.path.join(temp_dir, "Music")
            results_dir = os.path.join(temp_dir, "results")
            os.makedirs(os.path.join(library_path, "Artist A"))
            os.makedirs(os.path.join(library_path, "Artist B"))

            state_path, _report_path = checkpoint_paths(results_dir, part_config)
            save_checkpoint_state(
                state_path,
                part_config=part_config,
                library_path=library_path,
                workers=2,
                use_cache=False,
                include_singles=False,
                selected_group_count=2,
                entries_by_group_id={existing_entry["group_id"]: existing_entry},
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                report = run_match_stress_part(
                    part_config,
                    library_path=library_path,
                    results_dir=results_dir,
                    workers=2,
                )

            clear_deezer_cache_mock.assert_called_once()
            clear_musicbrainz_cache_mock.assert_called_once()
            self.assertEqual(set_log_console_enabled_mock.call_count, 2)
            self.assertEqual(report["completed_group_count"], 2)
            self.assertTrue(os.path.exists(report["report_path"]))
            self.assertTrue(os.path.exists(report["state_path"]))

            with open(report["state_path"], "r", encoding="utf-8") as handle:
                state_payload = json.load(handle)

            self.assertEqual(state_payload["completed_group_count"], 2)
            self.assertEqual(sorted(state_payload["completed_group_ids"]), ["group-1", "group-2"])
            self.assertIn("Part 4/10 complete", buffer.getvalue())

    @patch("musorg.core.match_stress_parts.set_log_console_enabled", side_effect=[True, False])
    @patch("musorg.core.match_stress_parts.clear_musicbrainz_caches")
    @patch("musorg.core.match_stress_parts.clear_deezer_cache")
    @patch("musorg.core.match_stress_parts.build_match_stress_groups")
    @patch("musorg.core.match_stress_parts.scan_library_tracks_from_roots")
    @patch("musorg.core.match_stress_parts.resolve_match_stress_entries")
    def test_run_match_stress_part_excludes_singles_by_default(
        self,
        resolve_entries_mock,
        scan_tracks_mock,
        build_groups_mock,
        clear_deezer_cache_mock,
        clear_musicbrainz_cache_mock,
        set_log_console_enabled_mock,
    ):
        del scan_tracks_mock, clear_deezer_cache_mock, clear_musicbrainz_cache_mock, set_log_console_enabled_mock
        part_config = {
            "part_number": 5,
            "label": "5/10",
            "artist_range": "Artist A - Artist B",
            "artist_dirs": ["Artist A"],
        }
        album_entry = {"group_id": "album-1", "lookup_artist": "Artist", "lookup_album": "Album 1", "is_singles_bucket": False}
        single_entry = {"group_id": "single-1", "lookup_artist": "Artist", "lookup_album": "Single 1", "is_singles_bucket": True}
        build_groups_mock.return_value = [album_entry, single_entry]
        resolve_entries_mock.return_value = [_resolved_entry("album-1", "both_match", deezer_success=True, musicbrainz_success=True)]

        with tempfile.TemporaryDirectory() as temp_dir:
            library_path = os.path.join(temp_dir, "Music")
            results_dir = os.path.join(temp_dir, "results")
            os.makedirs(os.path.join(library_path, "Artist A"))
            report = run_match_stress_part(
                part_config,
                library_path=library_path,
                results_dir=results_dir,
                workers=1,
            )

        self.assertEqual(resolve_entries_mock.call_args.args[0], [album_entry])
        self.assertEqual(report["summary"]["total_groups"], 1)
        self.assertEqual(report["summary"]["skipped_singles_groups"], 1)
        self.assertFalse(report["included_singles"])


class MatchStressPartSummaryTests(unittest.TestCase):
    def test_format_match_stress_summary_groups_problem_cases(self):
        entries = [
            _resolved_entry(
                "group-1",
                "deezer_only",
                deezer_success=True,
                musicbrainz_success=False,
                musicbrainz_reason="likely_catalog_absence",
            ),
            _resolved_entry("group-2", "musicbrainz_only", deezer_success=False, musicbrainz_success=True),
            _resolved_entry("group-3", "no_match", deezer_success=False, musicbrainz_success=False),
        ]

        summary = summarize_match_report(entries)
        text = format_match_stress_summary(
            summary,
            "/tmp/part-4-of-10.report.json",
            entries=entries,
            part_label="4/10",
            artist_range="Artist A - Artist C",
            processed_groups=3,
        )

        self.assertIn("Part 4/10 complete", text)
        self.assertIn("Artist range: Artist A - Artist C", text)
        self.assertIn("deezer_only_catalog_absence", text)
        self.assertIn("musicbrainz_only", text)
        self.assertIn("no_match", text)
        self.assertIn("Artist — Album group-1", text)

    def test_summarize_match_report_counts_catalog_absence_subtype(self):
        entries = [
            _resolved_entry(
                "group-1",
                "deezer_only",
                deezer_success=True,
                musicbrainz_success=False,
                musicbrainz_reason="likely_catalog_absence",
            ),
            _resolved_entry("group-2", "deezer_only", deezer_success=True, musicbrainz_success=False),
        ]

        summary = summarize_match_report(entries)

        self.assertEqual(summary["deezer_only_count"], 2)
        self.assertEqual(summary["deezer_only_catalog_absence_count"], 1)

    def test_format_match_stress_summary_prints_skipped_singles_groups(self):
        entries = [
            _resolved_entry("group-1", "both_match", deezer_success=True, musicbrainz_success=True),
        ]
        summary = summarize_match_report(entries)
        summary["skipped_singles_groups"] = 7
        text = format_match_stress_summary(
            summary,
            "/tmp/part-5-of-10.report.json",
            entries=entries,
            part_label="5/10",
            artist_range="Artist A - Artist B",
            processed_groups=1,
        )

        self.assertIn("Skipped singles groups: 7", text)

    def test_format_match_stress_summary_mentions_clean_part(self):
        entries = [
            _resolved_entry("group-1", "both_match", deezer_success=True, musicbrainz_success=True),
        ]

        summary = summarize_match_report(entries)
        text = format_match_stress_summary(
            summary,
            "/tmp/part-6-of-10.report.json",
            entries=entries,
            part_label="6/10",
            artist_range="Artist A - Artist A",
            processed_groups=1,
        )

        self.assertIn("No remaining problem matches in this part.", text)


class MatchStressPartDriverTests(unittest.TestCase):
    def test_run_match_part_script_invokes_selected_part(self):
        script_path = REPO_ROOT / "test" / "run_match_part.py"
        spec = importlib.util.spec_from_file_location("match_part_driver_test", script_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with patch.object(module, "load_parts_manifest", return_value={"parts": []}) as load_manifest_mock, patch.object(
            module,
            "get_part_config",
            return_value={"part_number": 4, "label": "4/10", "artist_dirs": [], "artist_range": "A - B"},
        ) as get_part_config_mock, patch.object(module, "run_match_stress_part") as run_part_mock, patch.object(
            sys,
            "argv",
            [str(script_path), "4", "--workers", "3", "--use-cache", "--include-singles"],
        ):
            exit_code = module.main()

        self.assertEqual(exit_code, 0)
        load_manifest_mock.assert_called_once()
        get_part_config_mock.assert_called_once_with({"parts": []}, 4)
        run_part_mock.assert_called_once()
        self.assertEqual(run_part_mock.call_args.kwargs["workers"], 3)
        self.assertTrue(run_part_mock.call_args.kwargs["use_cache"])
        self.assertTrue(run_part_mock.call_args.kwargs["include_singles"])

    def test_command_wrappers_target_expected_part_numbers(self):
        for part_number in range(4, 11):
            command_path = REPO_ROOT / "test" / f"run-part-{part_number}-of-10.command"
            self.assertTrue(command_path.exists())
            contents = command_path.read_text(encoding="utf-8")
            self.assertIn(f'test/run_match_part.py" {part_number} ', contents)
