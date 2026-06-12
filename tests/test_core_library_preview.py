from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from musorg.core.library_preview import (
    AlbumDetail,
    AlbumPreview,
    TrackPreview,
    load_album_detail,
    scan_album_previews,
    simulate_fixed_album_detail,
    simulate_fixed_album_preview,
)


class CoreLibraryPreviewTests(unittest.TestCase):
    @patch("musorg.core.library_preview.load_album_cover_bytes")
    @patch("musorg.core.library_preview.read_tags")
    def test_scan_album_previews_marks_clean_album_ready(self, read_tags_mock, cover_mock):
        read_tags_mock.return_value = {
            "title": "Angel",
            "tracknumber": "01",
            "duration_seconds": 391.2,
            "has_tracknumber_tag": True,
            "artist": "Massive Attack",
            "albumartist": "Massive Attack",
            "release_date_iso": "1998-04-20",
            "date": "1998",
        }
        cover_mock.return_value = b"cover"

        with tempfile.TemporaryDirectory() as temp_dir:
            album_dir = f"{temp_dir}/Massive Attack/Mezzanine"
            self._touch_flac(f"{album_dir}/01 - Angel.flac")
            self._touch_flac(f"{album_dir}/02 - Risingson.flac")

            previews = scan_album_previews(temp_dir)

        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0].album_title, "Mezzanine")
        self.assertEqual(previews[0].artist_name, "Massive Attack")
        self.assertEqual(previews[0].track_count, 2)
        self.assertEqual(previews[0].status, "Ready")

    @patch("musorg.core.library_preview.load_album_cover_bytes")
    @patch("musorg.core.library_preview.read_tags")
    def test_scan_album_previews_prefers_album_tag_over_folder_name(self, read_tags_mock, cover_mock):
        read_tags_mock.return_value = {
            "title": "мой дивный мир",
            "tracknumber": "01",
            "duration_seconds": 231.0,
            "has_tracknumber_tag": True,
            "artist": "Астра",
            "albumartist": "Астра",
            "album": "начало",
            "release_date_iso": "2024-01-01",
            "date": "2024",
        }
        cover_mock.return_value = b"cover"

        with tempfile.TemporaryDirectory() as temp_dir:
            album_dir = f"{temp_dir}/Астра/2024 - начало"
            self._touch_flac(f"{album_dir}/01 - track.flac")

            previews = scan_album_previews(temp_dir)

        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0].album_title, "начало")

    @patch("musorg.core.library_preview.load_album_cover_bytes")
    @patch("musorg.core.library_preview.read_tags")
    def test_scan_album_previews_prefers_tag_artist_over_unknown_folder_artist(self, read_tags_mock, cover_mock):
        read_tags_mock.return_value = {
            "title": "Track",
            "tracknumber": "01",
            "duration_seconds": 180.0,
            "has_tracknumber_tag": True,
            "artist": "Pharaoh & Boulevard Depo",
            "albumartist": "Unknown artist",
            "release_date_iso": "2016-01-01",
            "date": "2016",
        }
        cover_mock.return_value = b"cover"

        with tempfile.TemporaryDirectory() as temp_dir:
            album_dir = f"{temp_dir}/Unknown artist/2016 - Плакшери"
            self._touch_flac(f"{album_dir}/01 - Track.flac")

            previews = scan_album_previews(temp_dir)

        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0].artist_name, "Pharaoh & Boulevard Depo")
        self.assertNotIn("unknown_artist", previews[0].issues)

    @patch("musorg.core.library_preview.load_album_cover_bytes")
    @patch("musorg.core.library_preview.read_tags")
    def test_scan_album_previews_marks_root_level_album_as_needing_fix(self, read_tags_mock, cover_mock):
        read_tags_mock.return_value = {
            "title": "Track",
            "tracknumber": "01",
            "duration_seconds": 120.0,
            "has_tracknumber_tag": True,
            "artist": "Unknown",
            "albumartist": "Unknown",
            "release_date_iso": "",
            "date": "",
        }
        cover_mock.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            album_dir = f"{temp_dir}/Mystery Album"
            self._touch_flac(f"{album_dir}/01 - Track.flac")

            previews = scan_album_previews(temp_dir)

        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0].album_title, "Mystery Album")
        self.assertEqual(previews[0].artist_name, "Unknown artist")
        self.assertEqual(previews[0].status, "Needs Fix")
        self.assertIn("unknown_artist", previews[0].issues)
        self.assertIn("missing_cover", previews[0].issues)

    @patch("musorg.core.library_preview.load_album_cover_bytes")
    @patch("musorg.core.library_preview.read_tags")
    def test_scan_album_previews_returns_multiple_album_folders_sorted(self, read_tags_mock, cover_mock):
        read_tags_mock.return_value = {
            "title": "Track",
            "tracknumber": "01",
            "duration_seconds": 180.0,
            "has_tracknumber_tag": True,
            "artist": "Artist",
            "albumartist": "Artist",
            "release_date_iso": "2001-01-01",
            "date": "2001",
        }
        cover_mock.return_value = b"cover"

        with tempfile.TemporaryDirectory() as temp_dir:
            self._touch_flac(f"{temp_dir}/Portishead/Dummy/01 - Mysterons.flac")
            self._touch_flac(f"{temp_dir}/Boards of Canada/Music Has the Right to Children/01 - Wildlife Analysis.flac")

            previews = scan_album_previews(temp_dir)

        self.assertEqual([preview.artist_name for preview in previews], ["Boards of Canada", "Portishead"])
        self.assertEqual([preview.track_count for preview in previews], [1, 1])

    @patch("musorg.core.library_preview.read_tags")
    def test_load_album_detail_uses_metadata_when_available(self, read_tags_mock):
        read_tags_mock.return_value = {
            "title": "Angel",
            "tracknumber": "01",
            "duration_seconds": 391.2,
            "has_tracknumber_tag": True,
            "artist": "Massive Attack",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            album_dir = f"{temp_dir}/Massive Attack/Mezzanine"
            self._touch_flac(f"{album_dir}/01 - Angel.flac")

            detail = load_album_detail(album_dir, temp_dir)

        self.assertEqual(detail.album_title, "Mezzanine")
        self.assertEqual(detail.artist_name, "Massive Attack")
        self.assertEqual(detail.status, "Needs Fix")
        self.assertEqual(detail.tracks[0].track_number, "01")
        self.assertEqual(detail.tracks[0].track_title, "Angel")
        self.assertEqual(detail.tracks[0].duration_text, "6:31")
        self.assertEqual(detail.tracks[0].status, "OK")

    @patch("musorg.core.library_preview.read_tags")
    def test_load_album_detail_falls_back_to_filename_for_missing_metadata(self, read_tags_mock):
        read_tags_mock.return_value = {
            "title": "Unknown",
            "tracknumber": "0",
            "duration_seconds": None,
            "has_tracknumber_tag": False,
            "artist": "Unknown",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            album_dir = f"{temp_dir}/Loose Files"
            self._touch_flac(f"{album_dir}/01 - Mystery Track.flac")

            detail = load_album_detail(album_dir, temp_dir)

        self.assertEqual(detail.artist_name, "Unknown artist")
        self.assertEqual(detail.status, "Needs Fix")
        self.assertEqual(detail.tracks[0].track_number, "1")
        self.assertEqual(detail.tracks[0].track_title, "Mystery Track")
        self.assertEqual(detail.tracks[0].duration_text, "")
        self.assertEqual(detail.tracks[0].status, "Missing metadata")
        self.assertIn("unknown_artist", detail.issues)

    def test_load_album_detail_handles_missing_folder_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_dir = f"{temp_dir}/Deleted Artist/Gone Album"

            detail = load_album_detail(missing_dir, temp_dir)

        self.assertEqual(detail.album_title, "Gone Album")
        self.assertEqual(detail.artist_name, "Deleted Artist")
        self.assertEqual(detail.status, "Needs Fix")
        self.assertEqual(detail.tracks, [])
        self.assertIn("missing_track_numbers", detail.issues)

    def test_simulate_fixed_album_preview_replaces_unknown_artist_and_marks_ready(self):
        preview = AlbumPreview(
            album_title="Mystery Album",
            artist_name="Unknown artist",
            track_count=3,
            folder_path="/tmp/music/Mystery Album",
            status="Needs Fix",
            issues=("unknown_artist", "missing_cover", "missing_release_date", "missing_track_numbers"),
        )

        fixed_preview = simulate_fixed_album_preview(preview)

        self.assertEqual(fixed_preview.artist_name, "Placeholder Artist")
        self.assertEqual(fixed_preview.status, "Ready")
        self.assertEqual(fixed_preview.issues, ())

    def test_simulate_fixed_album_detail_marks_tracks_ok(self):
        detail = AlbumDetail(
            album_title="Mystery Album",
            artist_name="Unknown artist",
            folder_path="/tmp/music/Mystery Album",
            status="Needs Fix",
            tracks=[
                TrackPreview("1", "Track One", "", "Missing metadata"),
                TrackPreview("2", "Track Two", "", "Missing metadata"),
            ],
            issues=("unknown_artist", "missing_cover"),
        )

        fixed_detail = simulate_fixed_album_detail(detail)

        self.assertEqual(fixed_detail.artist_name, "Placeholder Artist")
        self.assertEqual(fixed_detail.status, "Ready")
        self.assertTrue(all(track.status == "OK" for track in fixed_detail.tracks))
        self.assertEqual(fixed_detail.issues, ())

    def _touch_flac(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"fLaC")
