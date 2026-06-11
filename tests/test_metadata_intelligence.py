from __future__ import annotations

import unittest

from musorg.core.metadata_intelligence import build_metadata_intelligence


class MetadataIntelligenceTests(unittest.TestCase):
    def test_build_metadata_intelligence_marks_manual_override_and_fallback(self):
        before = {
            "albumartist": "Unknown artist",
            "artist": "Unknown artist",
            "album": "DECIDE",
            "date": "Unknown",
            "genre": "Unknown",
            "cover": "Local low-quality cover",
            "releasetype": "Unknown",
            "trackCount": 18,
        }
        after = {
            "albumartist": "Boulevard Depo",
            "artist": "Boulevard Depo",
            "album": "OLD BLOOD",
            "date": "2018",
            "genre": "Rap",
            "cover": "Deezer artwork",
            "releasetype": "album",
            "trackCount": 18,
        }

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved={
                "deezer": None,
                "musicbrainz": {"album": "OLD BLOOD", "date_iso": "2018-01-01", "cover": None},
                "deezer_result": {"success": False, "metadata": None, "reason": "track_count_mismatch", "terminal": True},
                "path": "musicbrainz-fallback",
            },
            override={"albumArtist": "Boulevard Depo"},
            group_tracks=[{"albumartist": "Boulevard Depo", "artist": "Boulevard Depo"}],
        )

        self.assertEqual(intelligence["providerDecisions"]["metadataProvider"], "musicbrainz")
        self.assertEqual(intelligence["confidence"]["level"], "medium")
        self.assertIsInstance(intelligence["confidence"]["score"], int)
        self.assertTrue(intelligence["confidence"]["signals"])
        self.assertTrue(any(item["id"] == "track-count-mismatch" for item in intelligence["suspiciousMetadata"]))
        self.assertTrue(any(item["origin"] == "manual_override" for item in intelligence["diff"]))
        self.assertTrue(any(action["origin"] == "manual_override" for action in intelligence["cleanupActions"]))

    def test_build_metadata_intelligence_scores_high_for_exact_match(self):
        before = {
            "albumartist": "Djo",
            "artist": "Djo",
            "album": "DECIDE",
            "date": "2022",
            "genre": "Indie",
            "cover": "Local cover",
            "releasetype": "album",
            "trackCount": 2,
        }
        after = dict(before)
        resolved = {
            "deezer": {
                "albumartist": "Djo",
                "album": "DECIDE",
                "date_iso": "2022-09-16",
                "releasetype": "album",
                "tracks": [{"title": "Runner"}, {"title": "Half Life"}],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Djo", "artist": "Djo", "title": "Runner", "tracknumber": 1},
            {"albumartist": "Djo", "artist": "Djo", "title": "Half Life", "tracknumber": 2},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        self.assertEqual(intelligence["confidence"]["level"], "high")
        self.assertGreaterEqual(intelligence["confidence"]["score"], 90)

    def test_musicbrainz_date_only_verification_does_not_trigger_provider_disagreement(self):
        before = {
            "albumartist": "Аффинаж",
            "artist": "Аффинаж",
            "album": "Дети",
            "date": "2017",
            "genre": "Alternative",
            "cover": "Deezer artwork",
            "releasetype": "ep",
            "trackCount": 3,
        }
        after = {
            **before,
            "date": "2013",
        }
        resolved = {
            "deezer": {
                "albumartist": "Аффинаж",
                "album": "Дети",
                "date_iso": "2017-09-08",
                "releasetype": "ep",
                "tracks": [
                    {"title": "Track 1"},
                    {"title": "Track 2"},
                    {"title": "Track 3"},
                ],
            },
            "musicbrainz": {
                "date": "27-09-2013",
                "date_iso": "2013-09-27",
                "expected_track_count": 3,
                "year": "2013",
            },
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Аффинаж", "artist": "Аффинаж", "title": "Track 1", "tracknumber": 1},
            {"albumartist": "Аффинаж", "artist": "Аффинаж", "title": "Track 2", "tracknumber": 2},
            {"albumartist": "Аффинаж", "artist": "Аффинаж", "title": "Track 3", "tracknumber": 3},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        suspicious_ids = {item["id"] for item in intelligence["suspiciousMetadata"]}
        self.assertNotIn("provider-disagreement", suspicious_ids)
        self.assertNotIn("conflicting-release-year", suspicious_ids)
        provider_signal = next(
            signal for signal in intelligence["confidence"]["signals"]
            if signal["id"] == "provider-agreement"
        )
        self.assertEqual(provider_signal["status"], "accepted")

    def test_build_metadata_intelligence_marks_suspicious_release(self):
        before = {
            "albumartist": "Unknown artist",
            "artist": "Unknown artist",
            "album": "Greatest Hits Ultimate Collection 2009_2014",
            "date": "Unknown",
            "genre": "Unknown",
            "cover": "Local low-quality cover",
            "releasetype": "Unknown",
            "trackCount": 4,
        }
        after = {
            "albumartist": "Various Artists",
            "artist": "Various Artists",
            "album": "Greatest Hits Ultimate Collection 2009_2014 Bootleg",
            "date": "2014",
            "genre": "Unknown",
            "cover": "Local low-quality cover",
            "releasetype": "compilation",
            "trackCount": 4,
        }
        resolved = {
            "deezer": {
                "albumartist": "Various Artists",
                "album": "Greatest Hits Ultimate Collection 2009_2014 Bootleg",
                "date_iso": "2014-01-01",
                "releasetype": "compilation",
                "tracks": [{"title": "Song A"}, {"title": "Song A"}, {"title": "Song C"}, {"title": "Song D"}],
            },
            "musicbrainz": {
                "albumartist": "Unknown Artist",
                "album": "Ultimate Collection",
                "date_iso": "2009-01-01",
                "tracks": [{"title": "Alt A"}, {"title": "Alt B"}, {"title": "Alt C"}, {"title": "Alt D"}],
            },
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-then-musicbrainz",
        }
        group_tracks = [
            {"albumartist": "Artist A", "artist": "Artist A", "title": "Song A", "tracknumber": 1},
            {"albumartist": "Artist B", "artist": "Artist B", "title": "Song A", "tracknumber": 3},
            {"albumartist": "Artist A", "artist": "Artist A", "title": "Song C", "tracknumber": 4},
            {"albumartist": "Artist B", "artist": "Artist B", "title": "Song D", "tracknumber": 7},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        self.assertEqual(intelligence["confidence"]["level"], "suspicious")
        suspicious_ids = {item["id"] for item in intelligence["suspiciousMetadata"]}
        self.assertIn("suspicious-release-title", suspicious_ids)
        self.assertNotIn("duplicate-tracks", suspicious_ids)
        self.assertNotIn("broken-sequencing", suspicious_ids)
        self.assertNotIn("sequencing", intelligence["autoFixDiagnostics"])

    def test_title_only_duplicate_tracks_do_not_trigger_warning_without_stronger_evidence(self):
        before = {
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "date": "2024",
            "genre": "Unknown",
            "cover": "No cover",
            "releasetype": "Unknown",
            "trackCount": 4,
        }
        after = dict(before)
        resolved = {
            "deezer": {
                "albumartist": "Artist",
                "album": "Album",
                "date_iso": "2024-01-01",
                "releasetype": "album",
                "tracks": [
                    {"title": "Intro", "tracknumber": 1, "artist": "Artist"},
                    {"title": "Theme", "tracknumber": 2, "artist": "Artist"},
                    {"title": "Intro", "tracknumber": 3, "artist": "Artist"},
                    {"title": "Finale", "tracknumber": 4, "artist": "Artist"},
                ],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Artist", "artist": "Artist", "title": "Intro", "tracknumber": 1},
            {"albumartist": "Artist", "artist": "Artist", "title": "Theme", "tracknumber": 2},
            {"albumartist": "Artist", "artist": "Artist", "title": "Intro", "tracknumber": 3},
            {"albumartist": "Artist", "artist": "Artist", "title": "Finale", "tracknumber": 4},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        suspicious_ids = {item["id"] for item in intelligence["suspiciousMetadata"]}
        self.assertNotIn("duplicate-tracks", suspicious_ids)

    def test_interleaved_multi_disc_order_does_not_trigger_broken_sequencing(self):
        before = {
            "albumartist": "The Limiñanas",
            "artist": "The Limiñanas",
            "album": "Down Underground - LP's 2009 / 2014",
            "date": "2015",
            "genre": "Unknown",
            "cover": "No cover",
            "releasetype": "Unknown",
            "trackCount": 6,
        }
        after = {
            **before,
            "genre": "85",
            "cover": "Provider artwork",
            "releasetype": "album",
        }
        resolved = {
            "deezer": {
                "albumartist": "The Limiñanas",
                "album": "Down Underground - LP's 2009 / 2014",
                "date_iso": "2015-01-01",
                "releasetype": "album",
                "tracks": [
                    {"title": "The Darkside", "tracknumber": 1, "discnumber": 1, "artist": "The Limiñanas"},
                    {"title": "Down Underground", "tracknumber": 2, "discnumber": 1, "artist": "The Limiñanas"},
                    {"title": "Je ne suis pas très drogue", "tracknumber": 3, "discnumber": 1, "artist": "The Limiñanas"},
                    {"title": "Je me souviens comme si j’y étais", "tracknumber": 1, "discnumber": 2, "artist": "The Limiñanas"},
                    {"title": "My Black Sabbath", "tracknumber": 2, "discnumber": 2, "artist": "The Limiñanas"},
                    {"title": "Alicante", "tracknumber": 3, "discnumber": 2, "artist": "The Limiñanas"},
                ],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "The Limiñanas", "artist": "The Limiñanas", "title": "Je me souviens comme si j’y étais", "tracknumber": 1, "discnumber": 2},
            {"albumartist": "The Limiñanas", "artist": "The Limiñanas", "title": "The Darkside", "tracknumber": 1, "discnumber": 1},
            {"albumartist": "The Limiñanas", "artist": "The Limiñanas", "title": "Down Underground", "tracknumber": 2, "discnumber": 1},
            {"albumartist": "The Limiñanas", "artist": "The Limiñanas", "title": "My Black Sabbath", "tracknumber": 2, "discnumber": 2},
            {"albumartist": "The Limiñanas", "artist": "The Limiñanas", "title": "Alicante", "tracknumber": 3, "discnumber": 2},
            {"albumartist": "The Limiñanas", "artist": "The Limiñanas", "title": "Je ne suis pas très drogue", "tracknumber": 3, "discnumber": 1},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        suspicious_ids = {item["id"] for item in intelligence["suspiciousMetadata"]}
        self.assertNotIn("broken-sequencing", suspicious_ids)
        self.assertNotIn("sequencing", intelligence["autoFixDiagnostics"])

    def test_non_contiguous_disc_numbers_still_trigger_structural_failure(self):
        before = {
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "date": "2024",
            "genre": "Unknown",
            "cover": "No cover",
            "releasetype": "Unknown",
            "trackCount": 2,
        }
        after = dict(before)
        resolved = {
            "deezer": {
                "albumartist": "Artist",
                "album": "Album",
                "date_iso": "2024-01-01",
                "releasetype": "album",
                "tracks": [
                    {"title": "Track 1", "tracknumber": 1, "discnumber": 1, "artist": "Artist"},
                    {"title": "Track 2", "tracknumber": 1, "discnumber": 3, "artist": "Artist"},
                ],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 1", "tracknumber": 1, "discnumber": 1},
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 2", "tracknumber": 1, "discnumber": 3},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        sequencing = next(item for item in intelligence["suspiciousMetadata"] if item["id"] == "broken-sequencing")
        self.assertEqual(sequencing["details"]["failingRule"], "non_contiguous_disc_numbers")
        self.assertEqual(sequencing["details"]["discNumbers"], [1, 3])
        self.assertTrue(sequencing["details"]["affectedTracks"])
        self.assertTrue(sequencing["details"]["canonicalOrder"])

    def test_benign_track_number_gap_without_provider_mismatch_does_not_trigger_warning(self):
        before = {
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "date": "2024",
            "genre": "Unknown",
            "cover": "No cover",
            "releasetype": "Unknown",
            "trackCount": 2,
        }
        after = dict(before)
        resolved = {
            "deezer": {
                "albumartist": "Artist",
                "album": "Album",
                "date_iso": "2024-01-01",
                "releasetype": "album",
                "tracks": [
                    {"title": "Track 1", "tracknumber": 1, "artist": "Artist"},
                    {"title": "Track 2", "tracknumber": 2, "artist": "Artist"},
                ],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 1", "tracknumber": 1},
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 2", "tracknumber": 3},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        suspicious_ids = {item["id"] for item in intelligence["suspiciousMetadata"]}
        self.assertNotIn("broken-sequencing", suspicious_ids)

    def test_provider_backed_track_order_mismatch_still_triggers_sequencing_warning(self):
        before = {
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "date": "2024",
            "genre": "Unknown",
            "cover": "No cover",
            "releasetype": "Unknown",
            "trackCount": 3,
        }
        after = dict(before)
        resolved = {
            "deezer": {
                "albumartist": "Artist",
                "album": "Album",
                "date_iso": "2024-01-01",
                "releasetype": "album",
                "tracks": [
                    {"title": "Track 1", "tracknumber": 1, "artist": "Artist"},
                    {"title": "Track 2", "tracknumber": 2, "artist": "Artist"},
                    {"title": "Track 3", "tracknumber": 3, "artist": "Artist"},
                ],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 1", "tracknumber": 1},
            {"albumartist": "Artist", "artist": "Artist", "title": "Wrong Track", "tracknumber": 3},
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 3", "tracknumber": 4},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        sequencing = next(item for item in intelligence["suspiciousMetadata"] if item["id"] == "broken-sequencing")
        self.assertEqual(sequencing["details"]["failingRule"], "track_sequence_jump")

    def test_duplicate_disc_track_slot_still_triggers_duplicate_warning(self):
        before = {
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "date": "2024",
            "genre": "Unknown",
            "cover": "No cover",
            "releasetype": "Unknown",
            "trackCount": 3,
        }
        after = dict(before)
        resolved = {
            "deezer": {
                "albumartist": "Artist",
                "album": "Album",
                "date_iso": "2024-01-01",
                "releasetype": "album",
                "tracks": [
                    {"title": "Track 1", "tracknumber": 1, "artist": "Artist"},
                    {"title": "Track 2", "tracknumber": 2, "artist": "Artist"},
                    {"title": "Track 3", "tracknumber": 3, "artist": "Artist"},
                ],
            },
            "musicbrainz": None,
            "deezer_result": {"success": True, "metadata": {}, "reason": None, "terminal": False},
            "path": "deezer-fast-path",
        }
        group_tracks = [
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 1", "tracknumber": 1, "discnumber": 1},
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 1", "tracknumber": 1, "discnumber": 1},
            {"albumartist": "Artist", "artist": "Artist", "title": "Track 3", "tracknumber": 3, "discnumber": 1},
        ]

        intelligence = build_metadata_intelligence(
            before=before,
            after=after,
            resolved=resolved,
            override={},
            group_tracks=group_tracks,
        )

        duplicate_tracks = next(item for item in intelligence["suspiciousMetadata"] if item["id"] == "duplicate-tracks")
        self.assertEqual(duplicate_tracks["details"]["duplicateTitles"][0]["positions"], [1, 2])
