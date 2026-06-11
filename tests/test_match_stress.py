import json
import os
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from musorg.cli.main import run
from musorg.core.match_stress import (
    build_match_stress_groups,
    combine_match_results,
    resolve_match_stress_json_path,
    run_match_stress,
    summarize_match_report,
)


def _track(path: str, artist: str, album: str, title: str, tracknumber: int, albumartist: str | None = None) -> dict:
    return {
        "path": path,
        "artist": artist,
        "albumartist": albumartist or artist,
        "album": album,
        "title": title,
        "tracknumber": tracknumber,
        "discnumber": 1,
        "_source_release_type_hint": "",
    }


class MatchStressGroupingTests(unittest.TestCase):
    def test_regular_album_folder_collapses_into_one_lookup(self):
        tracks = [
            _track("/music/Artist/Album/01.flac", "Artist", "Album", "Track 1", 1),
            _track("/music/Artist/Album/02.flac", "Artist", "Album", "Track 2", 2),
        ]

        groups = build_match_stress_groups(tracks)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["lookup_artist"], "Artist")
        self.assertEqual(groups[0]["lookup_album"], "Album")
        self.assertEqual(groups[0]["local_track_count"], 2)
        self.assertEqual(groups[0]["lookup_expected_track_count"], 2)
        self.assertEqual(groups[0]["local_track_titles"], ["Track 1", "Track 2"])
        self.assertFalse(groups[0]["is_singles_bucket"])

    def test_singles_bucket_creates_one_lookup_per_track_title(self):
        tracks = [
            _track("/music/Artist/Singles/01.flac", "Artist", "Singles", "Track A", 1),
            _track("/music/Artist/Singles/02.flac", "Artist", "Singles", "Track B", 2),
        ]

        groups = build_match_stress_groups(tracks)

        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group["is_singles_bucket"] for group in groups))
        self.assertEqual({group["lookup_album"] for group in groups}, {"Track A", "Track B"})
        self.assertEqual({group["local_track_count"] for group in groups}, {1})
        self.assertEqual({group["lookup_expected_track_count"] for group in groups}, {None})
        self.assertEqual({group["preferred_release_type"] for group in groups}, {"single"})


class MatchStressAggregationTests(unittest.TestCase):
    def test_combine_match_results_marks_provider_outcomes(self):
        entry = {
            "lookup_artist": "Artist",
            "lookup_album": "Album",
            "lookup_expected_track_count": 2,
            "lookup_track_titles": ["Track 1", "Track 2"],
            "preferred_release_type": "album",
        }

        deezer_only = combine_match_results(
            entry,
            {"success": True},
            {"success": False},
        )
        musicbrainz_only = combine_match_results(
            entry,
            {"success": False},
            {"success": True},
        )
        no_match = combine_match_results(
            entry,
            {"success": False},
            {"success": False},
        )

        self.assertEqual(deezer_only, {"outcome": "deezer_only", "winner": "deezer"})
        self.assertEqual(musicbrainz_only, {"outcome": "musicbrainz_only", "winner": "musicbrainz"})
        self.assertEqual(no_match, {"outcome": "no_match", "winner": None})

    def test_combine_match_results_uses_shared_provider_selection_when_both_match(self):
        entry = {
            "lookup_artist": "Artist",
            "lookup_album": "Album",
            "lookup_expected_track_count": 2,
            "lookup_track_titles": ["Track 1", "Track 2"],
            "preferred_release_type": "album",
        }
        deezer_metadata = {
            "album": "Album (Live)",
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
        }
        musicbrainz_metadata = {
            "album": "Album",
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
        }

        combined = combine_match_results(
            entry,
            {"success": True},
            {"success": True},
            deezer_metadata=deezer_metadata,
            musicbrainz_metadata=musicbrainz_metadata,
        )

        self.assertEqual(combined["outcome"], "both_match")
        self.assertEqual(combined["winner"], "musicbrainz")

    def test_summary_counts_provider_outcomes_and_failure_reasons(self):
        entries = [
            {
                "is_singles_bucket": False,
                "deezer": {"success": True, "reason": None},
                "musicbrainz": {"success": False, "reason": "no_candidates"},
                "combined": {"outcome": "deezer_only", "winner": "deezer"},
            },
            {
                "is_singles_bucket": True,
                "deezer": {"success": False, "reason": "no_candidates"},
                "musicbrainz": {"success": True, "reason": None},
                "combined": {"outcome": "musicbrainz_only", "winner": "musicbrainz"},
            },
            {
                "is_singles_bucket": False,
                "deezer": {"success": False, "reason": "track_count_mismatch"},
                "musicbrainz": {"success": False, "reason": "no_candidates"},
                "combined": {"outcome": "no_match", "winner": None},
            },
        ]

        summary = summarize_match_report(entries)

        self.assertEqual(summary["total_groups"], 3)
        self.assertEqual(summary["singles_groups"], 1)
        self.assertEqual(summary["deezer_success_count"], 1)
        self.assertEqual(summary["musicbrainz_success_count"], 1)
        self.assertEqual(summary["combined_success_count"], 2)
        self.assertEqual(summary["deezer_only_count"], 1)
        self.assertEqual(summary["musicbrainz_only_count"], 1)
        self.assertEqual(summary["no_match_count"], 1)
        self.assertEqual(summary["provider_gap"], 0)
        self.assertEqual(summary["non_singles"]["total_groups"], 2)
        self.assertEqual(summary["non_singles"]["deezer_success_count"], 1)
        self.assertEqual(summary["non_singles"]["musicbrainz_success_count"], 0)
        self.assertEqual(summary["non_singles"]["provider_gap"], 1)
        self.assertEqual(summary["top_failure_reasons"]["deezer"][0]["reason"], "no_candidates")
        self.assertEqual(summary["top_failure_reasons"]["musicbrainz"][0]["reason"], "no_candidates")


class MatchStressRunnerTests(unittest.TestCase):
    @patch("musorg.core.match_stress.set_log_console_enabled", side_effect=[True, False])
    @patch("musorg.core.match_stress.clear_musicbrainz_caches")
    @patch("musorg.core.match_stress.clear_deezer_cache")
    @patch("musorg.core.match_stress.fetch_metadata_result")
    @patch("musorg.core.match_stress.get_album_data")
    @patch("musorg.core.match_stress.scan_library_tracks")
    def test_run_match_stress_writes_json_report_and_handles_singles(
        self,
        scan_library_tracks_mock,
        get_album_data_mock,
        fetch_metadata_result_mock,
        clear_deezer_cache_mock,
        clear_musicbrainz_caches_mock,
        set_log_console_enabled_mock,
    ):
        scan_library_tracks_mock.return_value = [
            _track("/music/Artist/Album/01.flac", "Artist", "Album", "Track 1", 1),
            _track("/music/Artist/Album/02.flac", "Artist", "Album", "Track 2", 2),
            _track("/music/Artist/Singles/01.flac", "Artist", "Singles", "Solo Track", 1),
        ]

        def deezer_side_effect(artist, album, **_kwargs):
            if album == "Album":
                return {
                    "success": True,
                    "metadata": {
                        "album": "Album",
                        "albumartist": artist,
                        "album_id": 101,
                        "releasetype": "album",
                        "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
                    },
                    "reason": None,
                    "confidence": "high",
                    "evidence": None,
                }
            return {
                "success": False,
                "metadata": None,
                "reason": "no_candidates",
                "confidence": None,
                "evidence": None,
            }

        def musicbrainz_side_effect(artist, album, **_kwargs):
            if album == "Solo Track":
                return {
                    "success": True,
                    "metadata": {
                        "album": "Real Single",
                        "albumartist": artist,
                        "releasetype": "single",
                        "date_iso": "2024-05-10",
                        "tracks": [{"title": "Solo Track"}, {"title": "B-Side"}],
                    },
                    "reason": None,
                    "confidence": "medium",
                    "evidence": None,
                }
            return {
                "success": False,
                "metadata": None,
                "reason": "no_candidates",
                "confidence": None,
                "evidence": None,
            }

        get_album_data_mock.side_effect = deezer_side_effect
        fetch_metadata_result_mock.side_effect = musicbrainz_side_effect

        with tempfile.TemporaryDirectory() as library_root:
            json_out = os.path.join(library_root, "report.json")
            report = run_match_stress(library_root, json_out=json_out, workers=1)

            clear_deezer_cache_mock.assert_called_once()
            clear_musicbrainz_caches_mock.assert_called_once()
            self.assertEqual(set_log_console_enabled_mock.call_count, 2)
            get_album_data_mock.assert_any_call(
                "Artist",
                "Album",
                expected_track_count=2,
                expected_titles=["Track 1", "Track 2"],
                preferred_release_type=None,
                warn_on_miss=False,
                use_cache=False,
            )
            get_album_data_mock.assert_any_call(
                "Artist",
                "Solo Track",
                expected_track_count=None,
                expected_titles=["Solo Track"],
                preferred_release_type="single",
                warn_on_miss=False,
                use_cache=False,
            )
            self.assertEqual(report["summary"]["total_groups"], 2)
            self.assertEqual(report["summary"]["deezer_only_count"], 1)
            self.assertEqual(report["summary"]["musicbrainz_only_count"], 1)
            self.assertTrue(os.path.exists(report["report_path"]))

            with open(report["report_path"], "r", encoding="utf-8") as handle:
                payload = json.load(handle)

            self.assertIn("summary", payload)
            self.assertEqual(len(payload["entries"]), 2)
            self.assertEqual(payload["entries"][1]["musicbrainz"]["album_title"], "Real Single")
            self.assertEqual(payload["entries"][1]["combined"]["outcome"], "musicbrainz_only")

    def test_default_json_output_path_is_generated_under_tmp(self):
        output_path = resolve_match_stress_json_path(None)

        self.assertTrue(output_path.startswith(tempfile.gettempdir()))
        self.assertTrue(output_path.endswith(".json"))


class MatchStressCliTests(unittest.TestCase):
    @patch("musorg.cli.main.run_match_stress")
    def test_cli_wires_match_stress_command_and_options(self, run_match_stress_mock):
        runner = CliRunner()

        result = runner.invoke(
            run,
            [
                "match-stress",
                "/Volumes/Music",
                "--json-out",
                "/tmp/report.json",
                "--workers",
                "3",
                "--limit",
                "25",
                "--use-cache",
                "--verbose",
            ],
        )

        self.assertEqual(result.exit_code, 0)
        run_match_stress_mock.assert_called_once_with(
            "/Volumes/Music",
            json_out="/tmp/report.json",
            workers=3,
            limit=25,
            use_cache=True,
            verbose=True,
        )
