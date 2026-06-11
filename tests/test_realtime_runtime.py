from __future__ import annotations

import asyncio
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from musorg.api.schemas.music import CleanLibraryRequest, LibrarySettingsResponse
from musorg.api.services.cleanup import clean_library
from musorg.api.services.cleanup_runs import finish_cleanup_run, get_active_cleanup_run
from musorg.api.services.log_stream import log_broadcaster
from musorg.utils.debug import log, warning


class RealtimeRuntimeTests(unittest.TestCase):
    def tearDown(self) -> None:
        active_run = get_active_cleanup_run()
        if active_run is not None:
            finish_cleanup_run(active_run.run_id)
        log_broadcaster.set_active_run(None)

    def test_cleanup_streams_live_runtime_events_before_run_completion(self):
        with TemporaryDirectory() as library_root, TemporaryDirectory() as output_root:
            self._touch_flac(Path(library_root) / "Artist A" / "Fast Album" / "01 - Fast.flac")
            self._touch_flac(Path(library_root) / "Artist B" / "Slow Album" / "01 - Slow.flac")

            settings_state = LibrarySettingsResponse(
                libraryRoot=library_root,
                outputRoot=output_root,
                developerMode=True,
                language="en",
                isConfigured=True,
                isAvailable=True,
                source="settings",
                pickerAvailable=False,
            )

            response_holder: dict[str, object] = {}
            response_done = threading.Event()

            def fake_read_tags(file_path: str):
                path = Path(file_path)
                album = path.parent.name
                artist = path.parent.parent.name
                title = path.stem.split(" - ", maxsplit=1)[-1]
                return {
                    "path": str(path),
                    "artist": artist,
                    "albumartist": artist,
                    "album": album,
                    "title": title,
                    "tracknumber": 1,
                    "discnumber": 1,
                    "date": "",
                    "releasetype": "",
                    "release_date_iso": "",
                    "singleoriginaltracknumber": 1,
                    "cover": "",
                }

            def fake_resolve_album_metadata(payload, total_albums, index, run_report=None, on_fallback=None):
                artist, album, track_count, _track_titles, preferred_release_type, _instructions = payload
                log("Metadata", f"Album {index}/{total_albums}: {artist} - {album}", "🧠")
                time.sleep(0.05 if album == "Fast Album" else 0.25)
                if album == "Slow Album":
                    warning("Deezer", f"No acceptable album match for {artist} - {album}, falling back to MusicBrainz")
                    if on_fallback:
                        on_fallback({
                            "from": "deezer",
                            "to": "musicbrainz",
                            "reason": "no_acceptable_candidate",
                            "path": "musicbrainz-fallback",
                            "progress": "matching",
                        })
                return {
                    "musicbrainz": None,
                    "deezer": {
                        "album": album,
                        "albumartist": artist,
                        "artist": artist,
                        "date": f"200{index}",
                        "date_iso": f"200{index}-01-01",
                        "releasetype": preferred_release_type or "album",
                        "tracks": [{"title": album, "tracknumber": 1, "discnumber": 1}],
                        "expected_track_count": track_count,
                        "cover": "",
                    },
                    "path": "deezer-fast-path",
                    "timings": {
                        "deezer_phase": 0.01,
                        "musicbrainz_fallback_phase": 0.0,
                        "album_total": 0.01,
                    },
                }

            def fake_organize_track(track: dict, output: str, dry_run: bool = False, journal=None, cleanup_conflicts: bool = True):
                time.sleep(0.03)
                target_dir = Path(output) / str(track.get("albumartist") or "Unknown") / str(track.get("album") or "Unknown")
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / Path(str(track.get("path") or "track.flac")).name
                target_path.write_bytes(b"")
                return str(target_path)

            def trigger_cleanup():
                response_holder["response"] = clean_library(CleanLibraryRequest(overrides=[]))
                response_done.set()

            with (
                patch("musorg.api.services.cleanup.get_library_settings_state", return_value=settings_state),
                patch("musorg.core.stages.metadata_read.read_tags", side_effect=fake_read_tags),
                patch("musorg.core.stages.metadata_read.resolve_album_metadata", side_effect=fake_resolve_album_metadata),
                patch("musorg.core.stages.organize.cleanup_stale_single_track", return_value=None),
                patch("musorg.core.stages.organize.is_standalone_single", return_value=False),
                patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)),
                patch("musorg.core.stages.organize.organize_track", side_effect=fake_organize_track),
            ):
                events = asyncio.run(self._collect_live_events(trigger_cleanup, response_done))

            response = response_holder.get("response")
            self.assertIsNotNone(response)
            self.assertEqual(response.status, "completed")
            event_types = [str(event.get("type") or "") for event in events]
            processed_titles = [
                str((((event.get("payload") or {}).get("processedAlbum") or (event.get("payload") or {}).get("albumPatch") or {}).get("title")) or "")
                for event in events
                if event.get("type") == "album_output_ready"
            ]

            self.assertIn("stage_started", event_types)
            self.assertIn("stage_completed", event_types)
            self.assertIn("matching_phase_started", event_types)
            self.assertIn("matching_phase_completed", event_types)
            self.assertIn("album_processing_started", event_types)
            self.assertIn("metadata_match", event_types)
            self.assertIn("metadata_resolved", event_types)
            self.assertIn("organize_completed", event_types)
            self.assertIn("album_output_ready", event_types)
            self.assertIn("album_processed", event_types)
            self.assertIn("pipeline_completed", event_types)
            self.assertTrue(any(event.get("type") == "log" and "checking 2 albums online" in str(event.get("message") or "").lower() for event in events))
            self.assertTrue(any(event.get("type") == "log" and "falling back to MusicBrainz" in str(event.get("message") or "") for event in events))
            self.assertTrue(any(str(event.get("message") or "").startswith("event emitted:") for event in events if event.get("type") == "dev_diagnostic"))
            self.assertTrue(any(str(event.get("message") or "").startswith("websocket_log_emit:") for event in events if event.get("type") == "dev_diagnostic"))
            self.assertEqual(len(processed_titles), 2)
            self.assertIn("Fast Album", processed_titles[0])
            self.assertTrue(any(event.get("type") == "album_output_ready" and not event.get("_responseDone", False) for event in events))
            self.assertTrue(any(
                event.get("type") == "album_output_ready"
                and ((event.get("payload") or {}).get("processedAlbum") or {}).get("processingState") == "completed"
                for event in events
            ))
            self.assertTrue(any(
                event.get("type") == "album_output_ready"
                and ((event.get("payload") or {}).get("processedAlbum") or {}).get("metadataIntelligence")
                for event in events
            ))
            self.assertTrue(any(
                event.get("type") == "log"
                and "checking 2 albums online" in str(event.get("message") or "").lower()
                and not event.get("_responseDone", False)
                for event in events
            ))
            first_provider_log_index = next(
                index
                for index, event in enumerate(events)
                if event.get("type") == "log" and event.get("source") in {"Deezer", "MusicBrainz"}
            )
            self.assertLess(event_types.index("matching_phase_started"), first_provider_log_index)
            self.assertLess(event_types.index("matching_phase_completed"), event_types.index("organize_completed"))

    async def _collect_live_events(self, trigger_cleanup, response_done: threading.Event) -> list[dict]:
        queue, _active_run_id = log_broadcaster.subscribe()
        events: list[dict] = []
        worker = threading.Thread(target=trigger_cleanup, daemon=True)
        worker.start()
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=10)
                events.append({
                    **event,
                    "_responseDone": response_done.is_set(),
                })
                if event.get("type") == "pipeline_completed":
                    break
        finally:
            worker.join(timeout=5)
            log_broadcaster.unsubscribe(queue)
        return events

    @staticmethod
    def _touch_flac(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
