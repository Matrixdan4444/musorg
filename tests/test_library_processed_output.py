from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from musorg.api.services.library import (
    get_album_actions_payload_for_root,
    get_album_detail_payload_for_root,
    get_related_releases_payload_for_root,
    list_albums_for_root,
)
from musorg.core.library_preview import AlbumDetail, AlbumPreview, TrackPreview


class LibraryProcessedOutputTests(unittest.TestCase):
    def test_list_albums_marks_completed_when_output_exists(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source_dir = root / "Artist" / "Album"
            output_dir = root / "Artist" / "Album_organized"
            source_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            self._write_run_summary(root, source_dir, output_dir)

            preview = AlbumPreview(
                album_title="Album",
                artist_name="Artist",
                track_count=10,
                folder_path=str(source_dir),
                status="Ready",
                issues=(),
            )

            output_detail = AlbumDetail(
                album_title="Album Organized",
                artist_name="Artist Clean",
                folder_path=str(output_dir),
                status="Ready",
                tracks=[TrackPreview(track_number="1", track_title="Clean Track", duration_text="03:10", status="OK")],
                album_artist="Artist Clean",
                release_year="2024",
                genre="Electronic",
                disc_number="1",
                issues=(),
            )

            with patch("musorg.api.services.library.scan_album_previews", return_value=[preview]), patch(
                "musorg.api.services.library.load_album_detail",
                return_value=output_detail,
            ):
                payload = list_albums_for_root(str(root))

            album = payload.albums[0]
            self.assertEqual(album.processingState, "completed")
            self.assertEqual(album.outputPath, str(output_dir.resolve()))
            self.assertEqual(album.title, "Album Organized")
            self.assertEqual(album.year, "2024")
            self.assertEqual(album.artist, "Artist Clean")
            self.assertEqual(album.status, "ready")
            self.assertEqual(album.issueCounts.warning, 0)

    def test_list_albums_returns_raw_state_when_output_removed(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source_dir = root / "Artist" / "Album"
            missing_output_dir = root / "Artist" / "Album_organized"
            source_dir.mkdir(parents=True)
            self._write_run_summary(root, source_dir, missing_output_dir)

            preview = AlbumPreview(
                album_title="Album",
                artist_name="Artist",
                track_count=10,
                folder_path=str(source_dir),
                status="Ready",
                issues=(),
            )

            with patch("musorg.api.services.library.scan_album_previews", return_value=[preview]):
                payload = list_albums_for_root(str(root))

            album = payload.albums[0]
            self.assertIsNone(album.processingState)
            self.assertIsNone(album.outputPath)
            self.assertEqual(album.status, "ready")
            self.assertEqual(album.issueCounts.warning, 0)

    def test_album_detail_returns_raw_state_when_output_removed(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source_dir = root / "Artist" / "Album"
            source_dir.mkdir(parents=True)
            missing_output_dir = root / "Artist" / "Album_organized"
            self._write_run_summary(root, source_dir, missing_output_dir)

            detail = AlbumDetail(
                album_title="Album",
                artist_name="Artist",
                folder_path=str(source_dir),
                status="Ready",
                tracks=[],
                album_artist="Artist",
                release_year="2024",
                genre="Rock",
                disc_number="1",
                issues=(),
            )

            album_id = self._encode_album_id(str(source_dir))
            with patch("musorg.api.services.library.load_album_detail", return_value=detail):
                payload = get_album_detail_payload_for_root(album_id, str(root))

            self.assertIsNone(payload.album.processingState)
            self.assertIsNone(payload.album.outputPath)
            self.assertEqual(payload.album.title, "Album")

    def test_album_detail_uses_processed_output_metadata_when_output_is_valid(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source_dir = root / "Artist" / "Album"
            output_dir = root / "Artist" / "Album_organized"
            source_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            self._write_run_summary(root, source_dir, output_dir)

            output_detail = AlbumDetail(
                album_title="Album Organized",
                artist_name="Artist Clean",
                folder_path=str(output_dir),
                status="Ready",
                tracks=[TrackPreview(track_number="1", track_title="Clean Track", duration_text="03:10", status="OK")],
                album_artist="Artist Clean",
                release_year="2025",
                genre="House",
                disc_number="1",
                issues=(),
            )

            album_id = self._encode_album_id(str(source_dir))
            with patch("musorg.api.services.library.load_album_detail", return_value=output_detail):
                payload = get_album_detail_payload_for_root(album_id, str(root))

            self.assertEqual(payload.album.processingState, "completed")
            self.assertEqual(payload.album.outputPath, str(output_dir.resolve()))
            self.assertEqual(payload.album.title, "Album Organized")
            self.assertEqual(payload.album.artist, "Artist Clean")

    def test_runtime_resolver_downgrades_to_raw_when_output_deleted_after_being_valid(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source_dir = root / "Artist" / "Album"
            output_dir = root / "Artist" / "Album_organized"
            source_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            self._write_run_summary(root, source_dir, output_dir)

            preview = AlbumPreview(
                album_title="Album",
                artist_name="Artist",
                track_count=10,
                folder_path=str(source_dir),
                status="Ready",
                issues=(),
            )
            output_detail = AlbumDetail(
                album_title="Album Organized",
                artist_name="Artist Clean",
                folder_path=str(output_dir),
                status="Ready",
                tracks=[TrackPreview(track_number="1", track_title="Clean Track", duration_text="03:10", status="OK")],
                album_artist="Artist Clean",
                release_year="2024",
                genre="Electronic",
                disc_number="1",
                issues=(),
            )

            with patch("musorg.api.services.library.scan_album_previews", return_value=[preview]), patch(
                "musorg.api.services.library.load_album_detail",
                return_value=output_detail,
            ):
                first_payload = list_albums_for_root(str(root))

            output_dir.rmdir()

            with patch("musorg.api.services.library.scan_album_previews", return_value=[preview]):
                second_payload = list_albums_for_root(str(root))

            self.assertEqual(first_payload.albums[0].processingState, "completed")
            self.assertIsNone(second_payload.albums[0].processingState)
            self.assertIsNone(second_payload.albums[0].outputPath)
            self.assertEqual(second_payload.albums[0].artist, "Artist")

    def test_title_serialization_does_not_duplicate_year_prefix(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source_dir = root / "Artist" / "Album"
            output_dir = root / "Artist" / "Album_organized"
            source_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            self._write_run_summary(root, source_dir, output_dir)

            preview = AlbumPreview(
                album_title="2022 - DECIDE",
                artist_name="Artist",
                track_count=10,
                folder_path=str(source_dir),
                status="Ready",
                issues=(),
            )
            output_detail = AlbumDetail(
                album_title="2022 - DECIDE",
                artist_name="Artist Clean",
                folder_path=str(output_dir),
                status="Ready",
                tracks=[TrackPreview(track_number="1", track_title="Clean Track", duration_text="03:10", status="OK")],
                album_artist="Artist Clean",
                release_year="2022",
                genre="Electronic",
                disc_number="1",
                issues=(),
            )

            with patch("musorg.api.services.library.scan_album_previews", return_value=[preview]), patch(
                "musorg.api.services.library.load_album_detail",
                return_value=output_detail,
            ):
                payload = list_albums_for_root(str(root))

            self.assertEqual(payload.albums[0].title, "DECIDE")
            self.assertEqual(payload.albums[0].year, "2022")

    def test_related_releases_payload_assigns_stable_ids_without_serializer_collision(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            current_dir = root / "A Beautiful Lie"
            duplicate_dir = root / "A Beautiful Lie (FLAC)"
            current_dir.mkdir(parents=True)
            duplicate_dir.mkdir(parents=True)
            current_file = current_dir / "01-Attack.m4a"
            duplicate_file = duplicate_dir / "01-Attack.flac"
            current_file.write_bytes(b"stub")
            duplicate_file.write_bytes(b"stub")

            previews = [
                AlbumPreview("A Beautiful Lie", "30 Seconds To Mars", 1, str(current_dir.resolve()), "Ready", ()),
                AlbumPreview("A Beautiful Lie", "30 Seconds To Mars", 1, str(duplicate_dir.resolve()), "Ready", ()),
            ]
            detail = AlbumDetail(
                album_title="A Beautiful Lie",
                artist_name="30 Seconds To Mars",
                folder_path="",
                status="Ready",
                tracks=[TrackPreview("1", "Attack", "3:09", "OK", "30 Seconds To Mars", 0)],
                album_artist="30 Seconds To Mars",
                release_year="2005",
                genre="Rock",
                disc_number="1",
                issues=(),
            )
            tags_by_path = {
                str(current_file.resolve()): {
                    "title": "Attack",
                    "artist": "30 Seconds To Mars",
                    "tracknumber": "1",
                    "duration_seconds": 189.0,
                    "bitrate": 320000,
                    "sample_rate": 44100,
                    "bit_depth": 16,
                    "format": "m4a",
                    "has_replaygain": False,
                    "cover_width": 600,
                    "cover_height": 600,
                    "musicbrainz_release_id": "",
                },
                str(duplicate_file.resolve()): {
                    "title": "Attack",
                    "artist": "30 Seconds To Mars",
                    "tracknumber": "1",
                    "duration_seconds": 189.0,
                    "bitrate": 1000000,
                    "sample_rate": 96000,
                    "bit_depth": 24,
                    "format": "flac",
                    "has_replaygain": True,
                    "cover_width": 3000,
                    "cover_height": 3000,
                    "musicbrainz_release_id": "",
                },
            }

            album_id = self._encode_album_id(str(current_dir.resolve()))
            with (
                patch("musorg.core.release_intelligence.scan_album_previews", return_value=previews),
                patch("musorg.core.release_intelligence.load_album_detail", return_value=detail),
                patch("musorg.core.release_intelligence.read_tags", side_effect=lambda path: tags_by_path[path]),
            ):
                payload = get_related_releases_payload_for_root(album_id, str(root))

            self.assertEqual(payload.current.id, album_id)
            self.assertTrue(all(item.id for item in payload.family))
            self.assertEqual(len({item.id for item in payload.family}), len(payload.family))

    def test_album_actions_endpoint_payload_returns_payload(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            current_dir = root / "A Beautiful Lie"
            duplicate_dir = root / "A Beautiful Lie (AAC)"
            current_dir.mkdir(parents=True)
            duplicate_dir.mkdir(parents=True)
            current_file = current_dir / "01-Attack.flac"
            duplicate_file = duplicate_dir / "01-Attack.m4a"
            current_file.write_bytes(b"stub")
            duplicate_file.write_bytes(b"stub")

            previews = [
                AlbumPreview("A Beautiful Lie", "30 Seconds To Mars", 1, str(current_dir.resolve()), "Ready", ()),
                AlbumPreview("A Beautiful Lie", "30 Seconds To Mars", 1, str(duplicate_dir.resolve()), "Ready", ()),
            ]
            detail = AlbumDetail(
                album_title="A Beautiful Lie",
                artist_name="30 Seconds To Mars",
                folder_path="",
                status="Ready",
                tracks=[TrackPreview("1", "Attack", "3:09", "OK", "30 Seconds To Mars", 0)],
                album_artist="30 Seconds To Mars",
                release_year="2005",
                genre="Rock",
                disc_number="1",
                issues=(),
            )
            tags_by_path = {
                str(current_file.resolve()): {
                    "title": "Attack",
                    "artist": "30 Seconds To Mars",
                    "tracknumber": "1",
                    "duration_seconds": 189.0,
                    "bitrate": 1000000,
                    "sample_rate": 96000,
                    "bit_depth": 24,
                    "format": "flac",
                    "has_replaygain": True,
                    "cover_width": 3000,
                    "cover_height": 3000,
                    "musicbrainz_release_id": "",
                },
                str(duplicate_file.resolve()): {
                    "title": "Attack",
                    "artist": "30 Seconds To Mars",
                    "tracknumber": "1",
                    "duration_seconds": 189.0,
                    "bitrate": 320000,
                    "sample_rate": 44100,
                    "bit_depth": 16,
                    "format": "m4a",
                    "has_replaygain": False,
                    "cover_width": 600,
                    "cover_height": 600,
                    "musicbrainz_release_id": "",
                },
            }

            album_id = self._encode_album_id(str(current_dir.resolve()))
            with (
                patch("musorg.core.release_intelligence.scan_album_previews", return_value=previews),
                patch("musorg.core.release_intelligence.load_album_detail", return_value=detail),
                patch("musorg.core.release_intelligence.read_tags", side_effect=lambda path: tags_by_path[path]),
            ):
                payload = get_album_actions_payload_for_root(album_id, str(root))

            self.assertEqual(payload.albumId, album_id)
            self.assertEqual(payload.albumId, album_id)
            self.assertTrue(payload.snapshotId)

    @staticmethod
    def _write_run_summary(root: Path, source_dir: Path, output_dir: Path) -> None:
        runs_dir = root / ".musorg" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "changed_albums": [
                {
                    "source_dir": str(source_dir),
                    "output_dir": str(output_dir),
                    "metadata_intelligence": None,
                }
            ]
        }
        (runs_dir / "latest.json").write_text(json.dumps(summary), encoding="utf-8")

    @staticmethod
    def _encode_album_id(folder_path: str) -> str:
        import base64

        return base64.urlsafe_b64encode(folder_path.encode("utf-8")).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
