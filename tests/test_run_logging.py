import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from musorg.core.context import Context
from musorg.core.pipeline import Pipeline, RunResult, run_pipeline
from musorg.core.run_report import RunReport
from musorg.core.stages.metadata_read import metadata_stage
from musorg.filesystem.organizer import organize_track, reset_session_state
from musorg.filesystem.rollback import OperationJournal
from musorg.utils.debug import add_log_observer, log, remove_log_observer, warning


class RunLoggingTests(unittest.TestCase):
    def test_log_observer_receives_worker_thread_events(self):
        captured: list[dict] = []

        def observer(event: dict) -> None:
            captured.append(event)

        worker = threading.Thread(target=lambda: log("Metadata", "Worker thread log", "🧠"))

        add_log_observer(observer)
        try:
            worker.start()
            worker.join(timeout=5)
        finally:
            remove_log_observer(observer)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["stage"], "Metadata")
        self.assertEqual(captured[0]["message"], "Worker thread log")

    def test_pipeline_writes_structured_run_summary_file(self):
        with tempfile.TemporaryDirectory() as root_path:
            context = Context(root_path, dry_run=True)
            pipeline = Pipeline()

            def stage(ctx):
                warning("Test", "Captured warning")
                return ctx

            pipeline.stages = [stage]
            pipeline.run(context)

            self.assertIsNotNone(context.run_report)
            self.assertTrue(os.path.exists(context.run_report.summary_path))

            with open(context.run_report.summary_path, "r", encoding="utf-8") as summary_file:
                summary = json.load(summary_file)

            self.assertTrue(summary["dry_run"])
            self.assertEqual(summary["counts"]["warnings"], 1)
            self.assertEqual(summary["warnings"][0]["message"], "Captured warning")
            self.assertIn("profiling", summary)
            self.assertIn("stage_timings", summary["profiling"])

    def test_pipeline_summary_includes_stage_and_hotspot_timings(self):
        with tempfile.TemporaryDirectory() as root_path:
            context = Context(root_path, dry_run=True)
            pipeline = Pipeline()

            def stage(ctx):
                with ctx.run_report.measure("metadata_fetch"):
                    pass
                return ctx

            pipeline.stages = [stage]

            perf_counter_values = iter([1.0, 3.5, 5.0, 5.25])
            with patch("musorg.core.run_report.perf_counter", side_effect=lambda: next(perf_counter_values)):
                pipeline.run(context)

            with open(context.run_report.summary_path, "r", encoding="utf-8") as summary_file:
                summary = json.load(summary_file)

            stage_timings = summary["profiling"]["stage_timings"]
            metrics = summary["profiling"]["metrics"]
            self.assertEqual(stage_timings[0]["stage"], "stage")
            self.assertAlmostEqual(stage_timings[0]["seconds"], 4.25)
            self.assertAlmostEqual(metrics["metadata_fetch"]["total_seconds"], 1.5)
            self.assertAlmostEqual(metrics["stage:stage"]["total_seconds"], 4.25)

    def test_run_report_tracks_musicbrainz_date_metric_separately(self):
        with tempfile.TemporaryDirectory() as root_path:
            report = RunReport(root_path, dry_run=True)

            perf_counter_values = iter([1.0, 1.25])
            with patch("musorg.core.run_report.perf_counter", side_effect=lambda: next(perf_counter_values)):
                with report.measure("metadata_musicbrainz_date"):
                    pass

            metrics = report.profiling_summary()["metrics"]
            self.assertAlmostEqual(metrics["metadata_musicbrainz_date"]["total_seconds"], 0.25)

    def test_run_report_tracks_count_only_metrics(self):
        with tempfile.TemporaryDirectory() as root_path:
            report = RunReport(root_path, dry_run=True)

            report.record_count("metadata_musicbrainz_date_direct_hit")
            report.record_count("metadata_musicbrainz_date_direct_hit")

            metrics = report.profiling_summary()["metrics"]
            self.assertEqual(metrics["metadata_musicbrainz_date_direct_hit"]["count"], 2)
            self.assertAlmostEqual(metrics["metadata_musicbrainz_date_direct_hit"]["total_seconds"], 0.0)

    @patch("musorg.core.pipeline.default_stages", return_value=[])
    def test_run_pipeline_returns_structured_result(self, _default_stages_mock):
        with tempfile.TemporaryDirectory() as root_path:
            result = run_pipeline(root_path, apply=False)

        self.assertIsInstance(result, RunResult)
        self.assertEqual(result.albums_processed, 0)
        self.assertEqual(result.tracks_processed, 0)
        self.assertTrue(result.stats["dry_run"])
        self.assertEqual(result.output_path, None)

    def test_metadata_stage_records_skipped_unresolved_and_changed_albums(self):
        with tempfile.TemporaryDirectory() as root_path:
            context = Context(root_path, dry_run=True)
            context.run_report = RunReport(root_path, dry_run=True)
            source_file = os.path.join(root_path, "Artist", "track01.flac")
            skipped_file = os.path.join(root_path, "Artist", "broken.flac")
            context.files = [source_file, skipped_file]

            original_tags = {
                "path": source_file,
                "artist": "Artist",
                "albumartist": "Artist",
                "album": "Top",
                "title": "Track 1",
                "tracknumber": 1,
                "discnumber": 1,
                "date": "2001",
                "releasetype": "",
                "release_date_iso": "",
                "singleoriginaltracknumber": 1,
            }

            normalized_track = dict(original_tags)
            musicbrainz_data = {
                (os.path.dirname(source_file), "top"): {
                    "album": "ТОП",
                    "albumartist": "Artist",
                    "date": "02-03-2004",
                    "date_iso": "2004-03-02",
                    "releasetype": "album",
                    "cover": None,
                    "tracks": [],
                    "expected_track_count": 1,
                    "use_canonical_album_title": False,
                }
            }

            with (
                patch("musorg.core.stages.metadata_read.read_tags", side_effect=[original_tags, None]),
                patch("musorg.core.stages.metadata_read.normalize_track", return_value=normalized_track),
                patch("musorg.core.stages.metadata_read.fetch_album_metadata", return_value=(musicbrainz_data, {})),
            ):
                metadata_stage(context)

            self.assertEqual(len(context.run_report.skipped_items), 1)
            self.assertEqual(context.run_report.skipped_items[0]["path"], skipped_file)
            self.assertEqual(len(context.run_report.unresolved_matches), 0)
            self.assertEqual(len(context.run_report.changed_albums), 1)
            changed_album = context.run_report.changed_albums[0]
            self.assertEqual(changed_album["before"]["album"], "Top")
            self.assertEqual(changed_album["after"]["album"], "ТОП")
            self.assertEqual(changed_album["after"]["date"], "2004-03-02")

    def test_metadata_stage_records_unresolved_album_matches(self):
        with tempfile.TemporaryDirectory() as root_path:
            context = Context(root_path, dry_run=True)
            context.run_report = RunReport(root_path, dry_run=True)
            source_file = os.path.join(root_path, "Artist", "track01.flac")
            context.files = [source_file]

            track = {
                "path": source_file,
                "artist": "Artist",
                "albumartist": "Artist",
                "album": "Unknown Album",
                "title": "Track 1",
                "tracknumber": 1,
                "discnumber": 1,
                "date": "2001",
                "releasetype": "",
                "release_date_iso": "",
                "singleoriginaltracknumber": 1,
            }

            with (
                patch("musorg.core.stages.metadata_read.read_tags", return_value=track),
                patch("musorg.core.stages.metadata_read.normalize_track", return_value=dict(track)),
                patch("musorg.core.stages.metadata_read.fetch_album_metadata", return_value=({}, {})),
            ):
                metadata_stage(context)

            self.assertEqual(len(context.run_report.unresolved_matches), 1)
            unresolved = context.run_report.unresolved_matches[0]
            self.assertEqual(unresolved["artist"], "Artist")
            self.assertEqual(unresolved["album"], "Unknown Album")

    def test_organize_track_records_duplicate_destination_collisions(self):
        with tempfile.TemporaryDirectory() as root_output:
            run_report = RunReport(root_output, dry_run=True)
            journal = OperationJournal(root_output, dry_run=True, run_report=run_report)
            track = {
                "path": os.path.join(root_output, "source1.flac"),
                "albumartist": "Artist",
                "artist": "Artist",
                "album": "Album",
                "title": "Track",
                "date": "01-01-2020",
                "release_date_iso": "2020-01-01",
                "tracknumber": 1,
                "discnumber": 1,
                "singleoriginaltracknumber": 1,
            }

            reset_session_state()
            organize_track(dict(track), root_output, dry_run=True, journal=journal)
            organize_track(dict(track, path=os.path.join(root_output, "source2.flac")), root_output, dry_run=True, journal=journal)

            self.assertEqual(len(run_report.duplicates), 1)
            duplicate = run_report.duplicates[0]
            self.assertEqual(duplicate["category"], "destination_collision")
            self.assertTrue(duplicate["resolved_destination"].endswith("(2).flac"))

    def test_copy_track_to_destination_records_audio_and_tag_timings(self):
        from musorg.filesystem.organizer import copy_track_to_destination

        run_report = RunReport("/tmp/music", dry_run=False)
        journal = OperationJournal("/tmp/music_out", dry_run=False, run_report=run_report)
        track = {
            "path": "/tmp/source.flac",
            "artist": "Artist",
            "albumartist": "Artist",
            "album": "Album",
            "title": "Title",
            "tracknumber": 1,
            "discnumber": 1,
            "date": "2020",
            "release_date_iso": "",
            "singleoriginaltracknumber": 1,
            "cover": None,
        }

        perf_counter_values = iter([10.0, 10.4, 11.0, 11.6])
        with (
            patch("musorg.core.run_report.perf_counter", side_effect=lambda: next(perf_counter_values)),
            patch("musorg.filesystem.organizer.create_flac_file"),
            patch("musorg.filesystem.organizer.write_metadata_tags"),
        ):
            copy_track_to_destination(track, "/tmp/output.flac", dry_run=False, journal=journal)

        self.assertAlmostEqual(run_report.profiling_summary()["metrics"]["audio_write"]["total_seconds"], 0.4)
        self.assertAlmostEqual(run_report.profiling_summary()["metrics"]["tag_write"]["total_seconds"], 0.6)

    def test_write_cover_art_records_download_and_processing_timings(self):
        from musorg.filesystem.tagging import write_cover_art

        run_report = RunReport("/tmp/music", dry_run=False)

        class Response:
            headers = {"Content-Type": "image/jpeg"}
            content = b"cover"

            def raise_for_status(self):
                return None

        audio = type("Audio", (), {
            "clear_pictures": lambda self: None,
            "add_picture": lambda self, picture: None,
            "save": lambda self: None,
        })()

        perf_counter_values = iter([1.0, 1.2, 2.0, 2.35])
        with (
            patch("musorg.core.run_report.perf_counter", side_effect=lambda: next(perf_counter_values)),
            patch("musorg.filesystem.tagging.cover_request_session") as cover_request_session_mock,
            patch("musorg.filesystem.tagging.FLAC", return_value=audio),
            patch("musorg.filesystem.tagging.normalize_picture_data", return_value=(b"normalized", "image/jpeg")),
        ):
            session = type("Session", (), {"get": lambda self, *_args, **_kwargs: Response()})()
            cover_request_session_mock.return_value = session
            write_cover_art("/tmp/test.flac", "https://example.com/cover.jpg", run_report=run_report)

        metrics = run_report.profiling_summary()["metrics"]
        self.assertAlmostEqual(metrics["cover_download"]["total_seconds"], 0.2)
        self.assertAlmostEqual(metrics["cover_processing"]["total_seconds"], 0.35)


if __name__ == "__main__":
    unittest.main()
