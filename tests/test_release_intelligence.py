import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from musorg.core.library_preview import AlbumDetail, AlbumPreview, TrackPreview
from musorg.core.release_intelligence import build_release_intelligence_registry


class ReleaseIntelligenceTests(unittest.TestCase):
    def test_groups_exact_duplicates_and_prefers_lossless_best_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            lossy_dir = root / "A Beautiful Lie (AAC)"
            lossless_dir = root / "A Beautiful Lie"
            lossy_dir.mkdir()
            lossless_dir.mkdir()
            lossy_file = lossy_dir / "01-Attack.m4a"
            lossless_file = lossless_dir / "01-Attack.flac"
            lossy_file.write_bytes(b"stub")
            lossless_file.write_bytes(b"stub")

            previews = [
                AlbumPreview("A Beautiful Lie", "30 Seconds To Mars", 1, str(lossy_dir.resolve()), "Ready", ()),
                AlbumPreview("A Beautiful Lie", "30 Seconds To Mars", 1, str(lossless_dir.resolve()), "Ready", ()),
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
                str(lossy_file.resolve()): {
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
                str(lossless_file.resolve()): {
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

            with (
                patch("musorg.core.release_intelligence.scan_album_previews", return_value=previews),
                patch("musorg.core.release_intelligence.load_album_detail", side_effect=lambda folder, _root: detail),
                patch("musorg.core.release_intelligence.read_tags", side_effect=lambda path: tags_by_path[path]),
            ):
                registry = build_release_intelligence_registry(str(root))

            lossy_summary = registry.summaries_by_path[str(lossy_dir.resolve())]
            lossless_summary = registry.summaries_by_path[str(lossless_dir.resolve())]

            self.assertEqual(lossless_summary["relationshipStatus"], "best_version")
            self.assertEqual(lossy_summary["relationshipStatus"], "exact_duplicate")
            self.assertGreater(lossless_summary["qualityScore"], lossy_summary["qualityScore"])
            self.assertTrue(
                any(action["id"] == "replace_lossy_release" for action in lossy_summary["releaseActions"])
            )

    def test_keeps_low_confidence_match_as_possible_related_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original_dir = root / "Album"
            candidate_dir = root / "Album Companion"
            original_dir.mkdir()
            candidate_dir.mkdir()
            for index in range(1, 5):
                (original_dir / f"{index:02d}.flac").write_bytes(b"stub")
            for index in range(1, 4):
                (candidate_dir / f"{index:02d}.flac").write_bytes(b"stub")

            previews = [
                AlbumPreview("Album", "Artist", 4, str(original_dir.resolve()), "Ready", ()),
                AlbumPreview("Album", "Artist", 3, str(candidate_dir.resolve()), "Ready", ()),
            ]
            detail_by_folder = {
                str(original_dir.resolve()): AlbumDetail(
                    album_title="Album",
                    artist_name="Artist",
                    folder_path=str(original_dir.resolve()),
                    status="Ready",
                    tracks=[
                        TrackPreview("1", "Track 1", "", "OK", "Artist", 0),
                        TrackPreview("2", "Track 2", "", "OK", "Artist", 0),
                        TrackPreview("3", "Track 3", "", "OK", "Artist", 0),
                        TrackPreview("4", "Track 4", "", "OK", "Artist", 0),
                    ],
                    album_artist="Artist",
                    release_year="2001",
                    genre="Rock",
                    disc_number="1",
                    issues=(),
                ),
                str(candidate_dir.resolve()): AlbumDetail(
                    album_title="Album",
                    artist_name="Artist",
                    folder_path=str(candidate_dir.resolve()),
                    status="Ready",
                    tracks=[
                        TrackPreview("1", "Track 1", "", "OK", "Artist", 0),
                        TrackPreview("2", "Track 2", "", "OK", "Artist", 0),
                        TrackPreview("3", "Track 3", "", "OK", "Artist", 0),
                    ],
                    album_artist="Artist",
                    release_year="2001",
                    genre="Rock",
                    disc_number="1",
                    issues=(),
                ),
            }
            tags_by_path = {}
            for index in range(1, 5):
                tags_by_path[str((original_dir / f"{index:02d}.flac").resolve())] = {
                    "title": f"Track {index}",
                    "artist": "Artist",
                    "tracknumber": str(index),
                    "duration_seconds": None,
                    "bitrate": 800000,
                    "sample_rate": 44100,
                    "bit_depth": 16,
                    "format": "flac",
                    "has_replaygain": False,
                    "cover_width": 1000,
                    "cover_height": 1000,
                    "musicbrainz_release_id": "",
                }
            for index in range(1, 4):
                tags_by_path[str((candidate_dir / f"{index:02d}.flac").resolve())] = {
                    "title": f"Track {index}",
                    "artist": "Artist",
                    "tracknumber": str(index),
                    "duration_seconds": None,
                    "bitrate": 800000,
                    "sample_rate": 44100,
                    "bit_depth": 16,
                    "format": "flac",
                    "has_replaygain": False,
                    "cover_width": 1000,
                    "cover_height": 1000,
                    "musicbrainz_release_id": "",
                }

            with (
                patch("musorg.core.release_intelligence.scan_album_previews", return_value=previews),
                patch("musorg.core.release_intelligence.load_album_detail", side_effect=lambda folder, _root: detail_by_folder[folder]),
                patch("musorg.core.release_intelligence.read_tags", side_effect=lambda path: tags_by_path[path]),
            ):
                registry = build_release_intelligence_registry(str(root))

            original_summary = registry.summaries_by_path[str(original_dir.resolve())]
            candidate_payload = registry.related_payload_by_path[str(original_dir.resolve())]

            self.assertEqual(original_summary["relationshipStatus"], "possible_related_release")
            self.assertEqual(original_summary["relatedReleaseCount"], 0)
            self.assertEqual(len(candidate_payload["possibleMatches"]), 1)


if __name__ == "__main__":
    unittest.main()
