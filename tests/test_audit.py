import json
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from musorg.cli.main import run
from musorg.core.audit import (
    AuditReport,
    AlbumAuditIssue,
    DuplicateAlbumIssue,
    DuplicateTrackIssue,
    MixedAlbumArtistIssue,
    TrackAuditIssue,
    audit_library,
    detect_duplicate_albums,
    detect_duplicate_tracks,
    format_audit_summary,
    health_score_breakdown,
)


class AuditLibraryTests(unittest.TestCase):
    @patch("musorg.core.audit.read_tags")
    @patch("musorg.core.audit.scan_files")
    def test_audit_library_collects_mvp_findings(self, scan_files_mock, read_tags_mock):
        scan_files_mock.return_value = [
            "/music/Artist/Album/01.flac",
            "/music/Artist/Album/02.flac",
            "/music/Artist/Broken.flac",
        ]
        read_tags_mock.side_effect = [
            {
                "path": "/music/Artist/Album/01.flac",
                "artist": "Artist",
                "albumartist": "Artist",
                "album": "Album",
                "title": "Track 1",
                "tracknumber": "1",
                "date": "2020",
                "releasetime": "",
                "musicbrainz_release_id": "",
                "musicbrainz_track_id": "",
                "duration_seconds": 180.0,
                "has_date_tag": False,
                "has_releasetime_tag": False,
                "has_tracknumber_tag": True,
                "has_cover_art": False,
            },
            {
                "path": "/music/Artist/Album/02.flac",
                "artist": "Artist",
                "albumartist": "Guest Artist",
                "album": "Album",
                "title": "Track 2",
                "tracknumber": "0",
                "date": "2020",
                "releasetime": "2020-01-01",
                "musicbrainz_release_id": "",
                "musicbrainz_track_id": "",
                "duration_seconds": 181.0,
                "has_date_tag": True,
                "has_releasetime_tag": True,
                "has_tracknumber_tag": False,
                "has_cover_art": False,
            },
            None,
        ]

        report = audit_library("/music")

        self.assertEqual(report.counts()["files_scanned"], 3)
        self.assertEqual(report.counts()["readable_tracks"], 2)
        self.assertEqual(report.counts()["source_album_count"], 1)
        self.assertEqual(report.counts()["albums_checked"], 1)
        self.assertEqual(report.counts()["missing_date"], 1)
        self.assertEqual(report.counts()["missing_releasetime"], 1)
        self.assertEqual(report.counts()["missing_tracknumber"], 1)
        self.assertEqual(report.counts()["missing_cover_art"], 1)
        self.assertEqual(report.counts()["mixed_albumartist"], 1)
        self.assertEqual(report.counts()["duplicate_albums"], 0)
        self.assertEqual(report.counts()["duplicate_tracks"], 0)
        self.assertEqual(report.unreadable_flac, ["/music/Artist/Broken.flac"])
        self.assertEqual(report.mixed_albumartist[0].albumartists, ["Artist", "Guest Artist"])
        self.assertEqual(report.to_dict()["issue_counts"]["missing_cover_art"], 1)

    def test_health_score_uses_weighted_penalties(self):
        report = AuditReport(
            root_path="/music",
            files_scanned=3,
            readable_tracks=2,
            grouped_album_count=1,
            source_album_count=1,
            unreadable_flac=["/music/broken.flac"],
            missing_date=[TrackAuditIssue(path="/music/01.flac", albumartist="Artist", album="Album", title="Track 1")],
            missing_releasetime=[TrackAuditIssue(path="/music/01.flac", albumartist="Artist", album="Album", title="Track 1")],
            missing_tracknumber=[TrackAuditIssue(path="/music/02.flac", albumartist="Artist", album="Album", title="Track 2")],
            missing_cover_art=[AlbumAuditIssue(source_dir="/music/Artist/Album", album="Album", albumartist="Artist", track_count=2, paths=["/music/01.flac", "/music/02.flac"])],
            mixed_albumartist=[MixedAlbumArtistIssue(source_dir="/music/Artist/Album", album="Album", albumartists=["Artist", "Guest Artist"], track_count=2, paths=["/music/01.flac", "/music/02.flac"])],
            duplicate_albums=[DuplicateAlbumIssue(albumartist="Artist", album="Album", source_dirs=["/music/A", "/music/B"], track_counts=[2, 2], musicbrainz_release_ids=[], match_signals=["normalized_artist_album", "matching_track_count"], paths=["/music/A/01.flac", "/music/B/01.flac"])],
            duplicate_tracks=[DuplicateTrackIssue(artist="Artist", title="Track 1", durations_seconds=[180.0, 181.0], musicbrainz_track_ids=[], match_signals=["artist_title", "duration_tolerance"], paths=["/music/A/01.flac", "/music/B/01.flac"])],
        )

        weights = health_score_breakdown()
        expected_score = 100 - (
            weights["unreadable_flac"]
            + weights["missing_date"]
            + weights["missing_releasetime"]
            + weights["missing_tracknumber"]
            + weights["missing_cover_art"]
            + weights["mixed_albumartist"]
            + weights["duplicate_albums"]
            + weights["duplicate_tracks"]
        )

        self.assertEqual(report.health_score, expected_score)
        self.assertEqual(report.counts()["health_score"], expected_score)

    def test_json_report_includes_machine_readable_fields(self):
        report = AuditReport(
            root_path="/tmp/music",
            files_scanned=3,
            readable_tracks=2,
            grouped_album_count=1,
            source_album_count=1,
            unreadable_flac=["/tmp/music/broken.flac"],
            missing_date=[TrackAuditIssue(path="/tmp/music/01.flac", albumartist="Artist", album="Album", title="Track 1")],
            missing_releasetime=[],
            missing_tracknumber=[],
            missing_cover_art=[],
            mixed_albumartist=[],
            duplicate_albums=[DuplicateAlbumIssue(albumartist="Artist", album="Album", source_dirs=["/tmp/music/A", "/tmp/music/B"], track_counts=[2, 2], musicbrainz_release_ids=[], match_signals=["normalized_artist_album", "matching_track_count"], paths=["/tmp/music/A/01.flac", "/tmp/music/B/01.flac"])],
            duplicate_tracks=[DuplicateTrackIssue(artist="Artist", title="Track 1", durations_seconds=[180.0, 181.0], musicbrainz_track_ids=[], match_signals=["artist_title", "duration_tolerance"], paths=["/tmp/music/A/01.flac", "/tmp/music/B/01.flac"])],
        )

        payload = report.to_dict()

        self.assertEqual(payload["library_path"], "/tmp/music")
        self.assertEqual(payload["files_scanned"], 3)
        self.assertEqual(payload["readable_tracks"], 2)
        self.assertEqual(payload["albums_checked"], 1)
        self.assertEqual(payload["health_score"], report.health_score)
        self.assertEqual(payload["issue_counts"]["missing_date"], 1)
        self.assertEqual(payload["issue_counts"]["duplicate_albums"], 1)
        self.assertEqual(payload["issue_counts"]["duplicate_tracks"], 1)
        self.assertEqual(payload["detailed_findings"]["unreadable_flac"], ["/tmp/music/broken.flac"])
        self.assertEqual(payload["detailed_findings"]["duplicate_albums"][0]["album"], "Album")
        self.assertEqual(payload["detailed_findings"]["duplicate_tracks"][0]["title"], "Track 1")

    def test_detect_duplicate_albums_by_normalized_artist_and_album(self):
        source_album_groups = {
            ("dir-1", "album"): [
                {"path": "/music/A/01.flac", "albumartist": "Artist", "artist": "Artist", "album": "Album", "musicbrainz_release_id": ""},
                {"path": "/music/A/02.flac", "albumartist": "Artist", "artist": "Artist", "album": "Album", "musicbrainz_release_id": ""},
            ],
            ("dir-2", "album"): [
                {"path": "/music/B/01.flac", "albumartist": "artist", "artist": "artist", "album": "ALBUM", "musicbrainz_release_id": ""},
                {"path": "/music/B/02.flac", "albumartist": "artist", "artist": "artist", "album": "ALBUM", "musicbrainz_release_id": ""},
            ],
            ("dir-3", "album"): [
                {"path": "/music/C/01.flac", "albumartist": "Artist", "artist": "Artist", "album": "Album (Deluxe)", "musicbrainz_release_id": ""},
                {"path": "/music/C/02.flac", "albumartist": "Artist", "artist": "Artist", "album": "Album (Deluxe)", "musicbrainz_release_id": ""},
            ],
        }

        duplicates = detect_duplicate_albums(source_album_groups)

        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].album, "Album")
        self.assertEqual(duplicates[0].match_signals, ["matching_track_count", "normalized_artist_album"])

    def test_detect_duplicate_albums_by_musicbrainz_release_id(self):
        source_album_groups = {
            ("dir-1", "album"): [
                {"path": "/music/A/01.flac", "albumartist": "Artist", "artist": "Artist", "album": "Album", "musicbrainz_release_id": "mb-1"},
            ],
            ("dir-2", "album"): [
                {"path": "/music/B/01.flac", "albumartist": "Artist", "artist": "Artist", "album": "Album (Remastered)", "musicbrainz_release_id": "mb-1"},
            ],
        }

        duplicates = detect_duplicate_albums(source_album_groups)

        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].musicbrainz_release_ids, ["mb-1"])
        self.assertEqual(duplicates[0].match_signals, ["musicbrainz_release_id"])

    def test_detect_duplicate_tracks_by_artist_title_and_duration_tolerance(self):
        tracks = [
            {"path": "/music/A/01.flac", "artist": "Artist", "title": "Track", "duration_seconds": 180.0, "musicbrainz_track_id": ""},
            {"path": "/music/B/01.flac", "artist": "artist", "title": "TRACK", "duration_seconds": 181.5, "musicbrainz_track_id": ""},
            {"path": "/music/C/01.flac", "artist": "Artist", "title": "Track", "duration_seconds": 184.5, "musicbrainz_track_id": ""},
        ]

        duplicates = detect_duplicate_tracks(tracks)

        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].title, "Track")
        self.assertEqual(duplicates[0].match_signals, ["artist_title", "duration_tolerance"])
        self.assertEqual(len(duplicates[0].paths), 2)

    def test_detect_duplicate_tracks_by_musicbrainz_track_id(self):
        tracks = [
            {"path": "/music/A/01.flac", "artist": "Artist", "title": "Track", "duration_seconds": 180.0, "musicbrainz_track_id": "mb-track-1"},
            {"path": "/music/B/01.flac", "artist": "Artist", "title": "Track", "duration_seconds": 240.0, "musicbrainz_track_id": "mb-track-1"},
        ]

        duplicates = detect_duplicate_tracks(tracks)

        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].musicbrainz_track_ids, ["mb-track-1"])
        self.assertEqual(duplicates[0].match_signals, ["musicbrainz_track_id"])


class AuditFormattingTests(unittest.TestCase):
    def test_verbose_summary_shows_file_and_album_level_findings(self):
        report = AuditReport(
            root_path="/tmp/music",
            files_scanned=3,
            readable_tracks=2,
            grouped_album_count=1,
            source_album_count=1,
            unreadable_flac=["/tmp/music/broken.flac"],
            missing_date=[TrackAuditIssue(path="/tmp/music/01.flac", albumartist="Artist", album="Album", title="Track 1")],
            missing_releasetime=[],
            missing_tracknumber=[],
            missing_cover_art=[AlbumAuditIssue(source_dir="/tmp/music/Artist/Album", album="Album", albumartist="Artist", track_count=2, paths=["/tmp/music/01.flac"])],
            mixed_albumartist=[MixedAlbumArtistIssue(source_dir="/tmp/music/Artist/Album", album="Album", albumartists=["Artist", "Guest Artist"], track_count=2, paths=["/tmp/music/01.flac"])],
            duplicate_albums=[DuplicateAlbumIssue(albumartist="Artist", album="Album", source_dirs=["/tmp/music/A", "/tmp/music/B"], track_counts=[2, 2], musicbrainz_release_ids=[], match_signals=["normalized_artist_album", "matching_track_count"], paths=["/tmp/music/A/01.flac", "/tmp/music/B/01.flac"])],
            duplicate_tracks=[DuplicateTrackIssue(artist="Artist", title="Track 1", durations_seconds=[180.0, 181.0], musicbrainz_track_ids=[], match_signals=["artist_title", "duration_tolerance"], paths=["/tmp/music/A/01.flac", "/tmp/music/B/01.flac"])],
        )

        output = format_audit_summary(report, verbose=True)

        self.assertIn("Health score: ", output)
        self.assertIn("Tracks missing DATE:", output)
        self.assertIn("/tmp/music/01.flac: Artist - Album - Track 1", output)
        self.assertIn("Albums missing cover art:", output)
        self.assertIn("/tmp/music/Artist/Album: Artist - Album (2 tracks)", output)
        self.assertIn("Albums with mixed ALBUMARTIST:", output)
        self.assertIn("Duplicate albums:", output)
        self.assertIn("Artist - Album: 2 copies", output)
        self.assertIn("Duplicate tracks:", output)
        self.assertIn("Artist - Track 1: 2 copies", output)


class AuditCliTests(unittest.TestCase):
    @staticmethod
    def _report():
        return AuditReport(
            root_path="/tmp/music",
            files_scanned=3,
            readable_tracks=2,
            grouped_album_count=1,
            source_album_count=1,
            unreadable_flac=["/tmp/music/broken.flac"],
            missing_date=[TrackAuditIssue(path="/tmp/music/01.flac", albumartist="Artist", album="Album", title="Track 1")],
            missing_releasetime=[],
            missing_tracknumber=[],
            missing_cover_art=[],
            mixed_albumartist=[],
            duplicate_albums=[DuplicateAlbumIssue(albumartist="Artist", album="Album", source_dirs=["/tmp/music/A", "/tmp/music/B"], track_counts=[2, 2], musicbrainz_release_ids=[], match_signals=["normalized_artist_album", "matching_track_count"], paths=["/tmp/music/A/01.flac", "/tmp/music/B/01.flac"])],
            duplicate_tracks=[DuplicateTrackIssue(artist="Artist", title="Track 1", durations_seconds=[180.0, 181.0], musicbrainz_track_ids=[], match_signals=["artist_title", "duration_tolerance"], paths=["/tmp/music/A/01.flac", "/tmp/music/B/01.flac"])],
        )

    @patch("musorg.cli.main.audit_library")
    def test_audit_command_prints_summary_with_health_score(self, audit_library_mock):
        audit_library_mock.return_value = self._report()
        runner = CliRunner()

        result = runner.invoke(run, ["audit", "/tmp/music"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Audit summary for /tmp/music", result.output)
        self.assertIn("Health score: ", result.output)
        self.assertIn("Duplicate albums: 1", result.output)
        self.assertIn("Duplicate tracks: 1", result.output)
        self.assertIn("Broken/unreadable FLAC: 1", result.output)

    @patch("musorg.cli.main.audit_library")
    def test_audit_command_supports_json_output(self, audit_library_mock):
        audit_library_mock.return_value = self._report()
        runner = CliRunner()

        result = runner.invoke(run, ["audit", "/tmp/music", "--json"])

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.output)
        self.assertEqual(payload["library_path"], "/tmp/music")
        self.assertEqual(payload["issue_counts"]["unreadable_flac"], 1)
        self.assertEqual(payload["issue_counts"]["duplicate_albums"], 1)
        self.assertEqual(payload["issue_counts"]["duplicate_tracks"], 1)
        self.assertIn("health_score", payload)

    @patch("musorg.cli.main.audit_library")
    def test_audit_command_supports_verbose_output(self, audit_library_mock):
        audit_library_mock.return_value = self._report()
        runner = CliRunner()

        result = runner.invoke(run, ["audit", "/tmp/music", "--verbose"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Tracks missing DATE:", result.output)
        self.assertIn("/tmp/music/01.flac: Artist - Album - Track 1", result.output)
        self.assertIn("Duplicate albums:", result.output)
        self.assertIn("Duplicate tracks:", result.output)


if __name__ == "__main__":
    unittest.main()
