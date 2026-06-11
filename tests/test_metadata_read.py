import unittest
import os
from unittest import mock

from musorg.core.runtime_state import runtime_options
from musorg.core.stages.metadata_read import (
    apply_deezer_metadata,
    apply_musicbrainz_album_metadata,
    fill_missing_albumartist,
    pick_deezer_track_metadata,
    apply_release_track_count,
    canonical_lookup_signature,
    collect_source_album_keys,
    deezer_artist_search_plan,
    fetch_album_metadata,
    fetch_single_album_metadata,
    is_singles_bucket_track,
    lookup_artist_credit,
    metadata_stage,
    normalize_track_release_dates,
    pick_lookup_artist,
    deezer_artist_candidates,
    resolve_deezer_match,
    resolve_album_metadata,
    source_album_group_key,
)
from musorg.core.context import Context
from musorg.core.run_report import RunReport


class ApplyMusicBrainzAlbumMetadataTests(unittest.TestCase):
    def test_normalize_track_release_dates_converts_iso_date_back_to_display_format(self):
        track = {
            "date": "2026-03-13",
            "release_date_iso": "",
        }

        normalize_track_release_dates(track)

        self.assertEqual(track["date"], "13-03-2026")
        self.assertEqual(track["release_date_iso"], "2026-03-13")

    def test_lookup_artist_credit_keeps_collaboration(self):
        self.assertEqual(
            lookup_artist_credit("Miyagi & Andy Panda"),
            "Miyagi & Andy Panda",
        )

    def test_lookup_artist_credit_canonicalizes_parenthetical_alias(self):
        self.assertEqual(
            lookup_artist_credit("Miyagi & Andy Panda (Эндшпиль)"),
            "Miyagi & Andy Panda",
        )

    def test_pick_lookup_artist_keeps_joint_albumartist(self):
        self.assertEqual(
            pick_lookup_artist([
                {
                    "albumartist": "Miyagi & Andy Panda (Эндшпиль)",
                    "artist": "Miyagi",
                }
            ]),
            "Miyagi & Andy Panda",
        )

    def test_fill_missing_albumartist_preserves_existing_joint_credit(self):
        track = {
            "albumartist": "King Gizzard & The Lizard Wizard",
            "artist": "King Gizzard & The Lizard Wizard",
        }

        fill_missing_albumartist(track, track["artist"])

        self.assertEqual(track["albumartist"], "King Gizzard & The Lizard Wizard")

    def test_collect_source_album_keys_uses_joint_lookup_artist(self):
        album_keys = collect_source_album_keys([
            {
                "path": "/music/yamakasi/01.mp3",
                "album": "YAMAKASI",
                "albumartist": "Miyagi & Andy Panda (Эндшпиль)",
                "artist": "Miyagi",
                "title": "Utopia",
                "tracknumber": 1,
            }
        ])

        self.assertEqual(
            next(iter(album_keys.values()))[0],
            "Miyagi & Andy Panda",
        )

    def test_singles_bucket_tracks_use_per_track_title_lookup(self):
        track = {
            "path": "/music/Artist/Singles/01 Track.flac",
            "album": "Singles",
            "albumartist": "Artist",
            "artist": "Artist",
            "title": "Track Title",
            "tracknumber": 1,
        }

        self.assertTrue(is_singles_bucket_track(track))
        self.assertEqual(
            source_album_group_key(track),
            (os.path.dirname(track["path"]), "release track title"),
        )

        album_keys = collect_source_album_keys([track])

        self.assertEqual(
            album_keys[source_album_group_key(track)],
            ("Artist", "Track Title", 1, ["Track Title"], None, {}),
        )

    def test_deezer_updates_singles_bucket_album_title_from_matched_release(self):
        track = {
            "path": "/music/Artist/Singles/01 Track.flac",
            "album": "Singles",
            "albumartist": "Artist",
            "artist": "Artist",
            "title": "Track Title",
            "tracknumber": 1,
            "cover_width": 0,
            "cover_height": 0,
        }

        apply_deezer_metadata(
            track,
            {
                "album": "Real EP",
                "albumartist": "Artist",
                "releasetype": "ep",
                "tracks": [{"artist": "Artist", "title": "Track Title", "tracknumber": 1}],
                "expected_track_count": 1,
            },
        )

        self.assertEqual(track["album"], "Real EP")
        self.assertEqual(track["releasetype"], "ep")

    def test_musicbrainz_release_type_overrides_stale_local_value(self):
        track = {
            "albumartist": "Unknown",
            "releasetype": "single",
        }

        apply_musicbrainz_album_metadata(
            track,
            {
                "albumartist": "Хаски",
                "releasetype": "ep",
            },
        )

        self.assertEqual(track["albumartist"], "Хаски")
        self.assertEqual(track["releasetype"], "ep")

    def test_fetch_album_metadata_logs_album_progress(self):
        album_keys = {
            ("artist", "album"): ("Artist", "Album", 1, ["Track 1"], None),
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.get_album_data", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.log") as log_mock,
        ):
            fetch_album_metadata(album_keys)

        self.assertTrue(
            any(
                call.args[0] == "Metadata" and "Matching album metadata 1/1: Artist — Album" in call.args[1]
                for call in log_mock.call_args_list
            )
        )

    def test_canonical_lookup_signature_normalizes_track_titles_and_release_type(self):
        signature = canonical_lookup_signature(("Artist", "Album", 2, ["A", "B"], "EP"))

        self.assertEqual(signature, ("Artist", "Album", 2, ("A", "B"), "ep", ""))

    def test_deezer_artist_candidates_split_collaboration_credit(self):
        candidates = deezer_artist_candidates("Индаблэк & Скриптонит & qurt")

        self.assertEqual(candidates[0], "Индаблэк & Скриптонит & qurt")
        self.assertIn("Индаблэк", candidates)
        self.assertIn("Скриптонит", candidates)
        self.assertIn("qurt", candidates)
        self.assertNotIn("qурт", candidates)

    def test_deezer_artist_search_plan_prioritizes_full_credit_before_split_rescue(self):
        phases = deezer_artist_search_plan("Индаблэк & Скриптонит & qurt")

        self.assertEqual(phases[0]["artists"], ["Индаблэк & Скриптонит & qurt"])
        self.assertFalse(phases[0]["include_album_only_queries"])
        self.assertFalse(phases[0]["include_track_title_fallback"])
        self.assertEqual(phases[1]["artists"], ["Индаблэк", "Скриптонит", "qurt"])
        self.assertEqual(phases[2]["artists"], ["Индаблэк", "Скриптонит", "qurt"])
        self.assertEqual(phases[2]["artist_query_mode"], "expanded")
        self.assertFalse(phases[2]["include_album_only_queries"])
        self.assertFalse(phases[2]["include_track_title_fallback"])
        self.assertEqual(phases[-1]["artists"], ["Индаблэк & Скриптонит & qurt"])
        self.assertTrue(phases[-1]["include_album_only_queries"])
        self.assertTrue(phases[-1]["include_track_title_fallback"])

    def test_resolve_deezer_match_emits_one_final_warning_after_all_phases_fail(self):
        failures = [
            {"success": False, "metadata": None, "reason": "no_candidates", "terminal": True},
            {"success": False, "metadata": None, "reason": "no_acceptable_candidate", "terminal": True},
            {"success": False, "metadata": None, "reason": "track_count_mismatch", "terminal": True},
        ]

        with (
            mock.patch(
                "musorg.core.stages.metadata_read.deezer_artist_search_plan",
                return_value=[
                    {"artists": ["Full Credit"], "artist_query_mode": "exact", "include_album_only_queries": False, "include_track_title_fallback": False},
                    {"artists": ["Split Credit"], "artist_query_mode": "exact", "include_album_only_queries": False, "include_track_title_fallback": False},
                    {"artists": ["Broad Credit"], "artist_query_mode": "exact", "include_album_only_queries": True, "include_track_title_fallback": True},
                ],
            ),
            mock.patch("musorg.core.stages.metadata_read.get_album_data", side_effect=failures),
            mock.patch("musorg.core.stages.metadata_read.warning") as warning_mock,
        ):
            result = resolve_deezer_match(
                "Artist",
                "Album",
                15,
                ["Track 1"],
                None,
                warn_on_miss=True,
            )

        self.assertEqual(result["reason"], "track_count_mismatch")
        warning_mock.assert_called_once()
        self.assertEqual(warning_mock.call_args.args[0], "Deezer")
        self.assertIn(
            "track count mismatch",
            warning_mock.call_args.args[1],
        )

    def test_fetch_single_album_metadata_skips_musicbrainz_for_complete_deezer_match(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None, {})
        deezer_match = {
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.get_album_data", return_value=deezer_match),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", side_effect=AssertionError("musicbrainz should not be called")),
            mock.patch("musorg.core.stages.metadata_read.fetch_original_release_date", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.deezer_page_release_date", return_value=None),
        ):
            key, musicbrainz_match, resolved_deezer_match = fetch_single_album_metadata(
                ("artist", "album"),
                payload,
                total_albums=1,
                index=1,
            )

        self.assertEqual(key, ("artist", "album"))
        self.assertIsNone(musicbrainz_match)
        self.assertEqual(resolved_deezer_match, deezer_match)

    def test_fetch_single_album_metadata_falls_back_to_musicbrainz_when_deezer_missing(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None)
        musicbrainz_match = {
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.get_album_data", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=musicbrainz_match) as fetch_metadata_mock,
        ):
            _key, resolved_musicbrainz_match, resolved_deezer_match = fetch_single_album_metadata(
                ("artist", "album"),
                payload,
                total_albums=1,
                index=1,
            )

        fetch_metadata_mock.assert_called_once()
        self.assertEqual(resolved_musicbrainz_match, musicbrainz_match)
        self.assertIsNone(resolved_deezer_match)

    def test_fetch_single_album_metadata_does_not_retry_deezer_after_musicbrainz(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None)
        musicbrainz_match = {
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        with (
            mock.patch(
                "musorg.core.stages.metadata_read.get_album_data",
                return_value={
                    "success": False,
                    "metadata": None,
                    "reason": "album_details_unavailable",
                    "terminal": True,
                },
            ) as get_album_data_mock,
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=musicbrainz_match),
        ):
            _key, resolved_musicbrainz_match, resolved_deezer_match = fetch_single_album_metadata(
                ("artist", "album"),
                payload,
                total_albums=1,
                index=1,
            )

        get_album_data_mock.assert_called_once()
        self.assertEqual(resolved_musicbrainz_match, musicbrainz_match)
        self.assertIsNone(resolved_deezer_match)

    def test_fetch_single_album_metadata_falls_back_to_musicbrainz_after_terminal_deezer_failure(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None)
        musicbrainz_match = {
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        with (
            mock.patch(
                "musorg.core.stages.metadata_read.get_album_data",
                return_value={
                    "success": False,
                    "metadata": None,
                    "reason": "no_candidates",
                    "terminal": True,
                },
            ),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=musicbrainz_match) as fetch_metadata_mock,
        ):
            _key, resolved_musicbrainz_match, resolved_deezer_match = fetch_single_album_metadata(
                ("artist", "album"),
                payload,
                total_albums=1,
                index=1,
            )

        fetch_metadata_mock.assert_called_once()
        self.assertEqual(resolved_musicbrainz_match, musicbrainz_match)
        self.assertIsNone(resolved_deezer_match)

    def test_fetch_single_album_metadata_logs_provider_timings_in_developer_mode(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None)
        deezer_result = {
            "success": True,
            "metadata": {
                "albumartist": "Artist",
                "releasetype": "album",
                "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
                "expected_track_count": 1,
            },
            "reason": None,
            "terminal": False,
        }

        with (
            runtime_options(developer_mode=True),
            mock.patch("musorg.core.stages.metadata_read.get_album_data", return_value=deezer_result),
            mock.patch("musorg.core.stages.metadata_read.log") as log_mock,
        ):
            fetch_single_album_metadata(
                ("artist", "album"),
                payload,
                total_albums=1,
                index=1,
            )

        self.assertTrue(any("⏱️ Deezer lookup:" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("⏱️ Metadata validation:" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("deezer-fast-path in" in call.args[1] for call in log_mock.call_args_list))

    def test_fetch_single_album_metadata_logs_dev_fallback_reason(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None)

        with (
            runtime_options(developer_mode=True),
            mock.patch(
                "musorg.core.stages.metadata_read.get_album_data",
                return_value={
                    "success": False,
                    "metadata": None,
                    "reason": "album_details_unavailable",
                    "terminal": True,
                },
            ),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.log") as log_mock,
        ):
            fetch_single_album_metadata(
                ("artist", "album"),
                payload,
                total_albums=1,
                index=1,
            )

        self.assertTrue(
            any(
                "Falling back to MusicBrainz due to album details unavailable" in call.args[1]
                for call in log_mock.call_args_list
            )
        )

    def test_resolve_album_metadata_emits_fallback_callback_before_musicbrainz_lookup(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None, {})
        callback_events: list[dict] = []
        call_order: list[str] = []
        musicbrainz_match = {
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        def fake_musicbrainz_lookup(*args, **kwargs):
            call_order.append("musicbrainz")
            return musicbrainz_match

        with (
            mock.patch(
                "musorg.core.stages.metadata_read.resolve_deezer_match",
                return_value={
                    "success": False,
                    "metadata": None,
                    "reason": "no_acceptable_candidate",
                    "terminal": True,
                },
            ),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", side_effect=fake_musicbrainz_lookup),
        ):
            resolved = resolve_album_metadata(
                payload,
                total_albums=1,
                index=1,
                on_fallback=lambda event: (
                    callback_events.append(event),
                    call_order.append("fallback"),
                ),
            )

        self.assertEqual(call_order, ["fallback", "musicbrainz"])
        self.assertEqual(callback_events[0]["from"], "deezer")
        self.assertEqual(callback_events[0]["to"], "musicbrainz")
        self.assertEqual(callback_events[0]["reason"], "no_acceptable_candidate")
        self.assertEqual(callback_events[0]["progress"], "matching")
        self.assertEqual(resolved["musicbrainz"], musicbrainz_match)

    def test_resolve_album_metadata_verifies_deezer_fast_path_date_with_musicbrainz(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None, {})
        deezer_result = {
            "success": True,
            "metadata": {
                "albumartist": "Artist",
                "album": "Album",
                "album_id": 123,
                "date": "08-09-2017",
                "date_iso": "2017-09-08",
                "expected_track_count": 1,
                "releasetype": "ep",
                "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            },
            "reason": None,
            "terminal": False,
        }
        mb_date = {
            "date": "27-09-2013",
            "date_iso": "2013-09-27",
            "expected_track_count": 1,
            "year": "2013",
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.resolve_deezer_match", return_value=deezer_result),
            mock.patch("musorg.core.stages.metadata_read.fetch_original_release_date", return_value=mb_date) as mb_mock,
        ):
            resolved = resolve_album_metadata(payload, total_albums=1, index=1)

        mb_mock.assert_called_once()
        self.assertEqual(resolved["path"], "deezer-fast-path")
        self.assertEqual(resolved["deezer"]["date_iso"], "2017-09-08")
        self.assertEqual(resolved["musicbrainz"]["date_iso"], "2013-09-27")

    def test_resolve_album_metadata_prefers_musicbrainz_when_shared_evidence_is_stronger(self):
        payload = ("Artist", "Album", 2, ["Track 1", "Track 2"], None, {})
        deezer_result = {
            "success": True,
            "metadata": {
                "albumartist": "Artist",
                "album": "Album",
                "album_id": 123,
                "date": "08-09-2017",
                "date_iso": "2017-09-08",
                "expected_track_count": 2,
                "releasetype": "album",
                "tracks": [{"artist": "Artist", "title": "Wrong 1", "tracknumber": 1}, {"artist": "Artist", "title": "Wrong 2", "tracknumber": 2}],
            },
            "reason": None,
            "terminal": False,
            "confidence": "low",
        }
        musicbrainz_match = {
            "albumartist": "Artist",
            "album": "Album",
            "date": "27-09-2013",
            "date_iso": "2013-09-27",
            "expected_track_count": 2,
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}, {"artist": "Artist", "title": "Track 2", "tracknumber": 2}],
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.resolve_deezer_match", return_value=deezer_result),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=musicbrainz_match),
            mock.patch("musorg.core.stages.metadata_read.fetch_original_release_date", side_effect=AssertionError("date-only lookup should not be used")),
        ):
            resolved = resolve_album_metadata(payload, total_albums=1, index=1)

        self.assertEqual(resolved["winner"], "musicbrainz")
        self.assertEqual(resolved["path"], "deezer-then-musicbrainz")
        self.assertEqual(resolved["musicbrainz"], musicbrainz_match)

    def test_resolve_album_metadata_skips_musicbrainz_date_verification_when_deezer_forced(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None, {"metadataProvider": "deezer"})
        deezer_result = {
            "success": True,
            "metadata": {
                "albumartist": "Artist",
                "album": "Album",
                "album_id": 123,
                "date": "08-09-2017",
                "date_iso": "2017-09-08",
                "expected_track_count": 1,
                "releasetype": "ep",
                "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            },
            "reason": None,
            "terminal": False,
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.resolve_deezer_match", return_value=deezer_result),
            mock.patch("musorg.core.stages.metadata_read.fetch_original_release_date") as mb_mock,
        ):
            resolved = resolve_album_metadata(payload, total_albums=1, index=1)

        mb_mock.assert_not_called()
        self.assertIsNone(resolved["musicbrainz"])
        self.assertEqual(resolved["path"], "deezer-forced")

    def test_resolve_album_metadata_uses_deezer_page_date_when_musicbrainz_date_missing(self):
        payload = ("Artist", "Album", 1, ["Track 1"], None, {})
        deezer_result = {
            "success": True,
            "metadata": {
                "albumartist": "Artist",
                "album": "Album",
                "album_id": 123,
                "date": "08-09-2017",
                "date_iso": "2017-09-08",
                "expected_track_count": 1,
                "releasetype": "ep",
                "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            },
            "reason": None,
            "terminal": False,
        }

        with (
            mock.patch("musorg.core.stages.metadata_read.resolve_deezer_match", return_value=deezer_result),
            mock.patch("musorg.core.stages.metadata_read.fetch_original_release_date", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.deezer_page_release_date", return_value="2013-09-27") as page_date_mock,
        ):
            resolved = resolve_album_metadata(payload, total_albums=1, index=1)

        page_date_mock.assert_called_once_with(123)
        self.assertIsNone(resolved["musicbrainz"])
        self.assertEqual(resolved["deezer"]["date_iso"], "2013-09-27")
        self.assertEqual(resolved["deezer"]["date"], "27-09-2013")

    def test_fetch_album_metadata_reuses_in_run_resolution_for_identical_payloads(self):
        album_keys = {
            ("source-a", "album"): ("Artist", "Album", 1, ["Track 1"], None),
            ("source-b", "album"): ("Artist", "Album", 1, ["Track 1"], None),
        }
        musicbrainz_match = {
            "albumartist": "Artist",
            "releasetype": "album",
            "tracks": [{"artist": "Artist", "title": "Track 1", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        with (
            mock.patch(
                "musorg.core.stages.metadata_read.get_album_data",
                return_value={
                    "success": False,
                    "metadata": None,
                    "reason": "no_candidates",
                    "terminal": True,
                },
            ) as get_album_data_mock,
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=musicbrainz_match) as fetch_metadata_mock,
        ):
            musicbrainz_by_album, deezer_by_album, resolved_album_metadata = fetch_album_metadata(album_keys)

        get_album_data_mock.assert_called_once()
        fetch_metadata_mock.assert_called_once()
        self.assertEqual(musicbrainz_by_album[("source-a", "album")], musicbrainz_match)
        self.assertEqual(musicbrainz_by_album[("source-b", "album")], musicbrainz_match)
        self.assertIsNone(deezer_by_album[("source-a", "album")])
        self.assertIsNone(deezer_by_album[("source-b", "album")])
        self.assertEqual(len(resolved_album_metadata), 1)

    def test_fetch_album_metadata_reports_provider_fallback_for_first_matching_group(self):
        album_keys = {
            ("source-a", "album"): ("Artist", "Album", 1, ["Track 1"], None),
            ("source-b", "album"): ("Artist", "Album", 1, ["Track 1"], None),
        }
        fallback_events: list[tuple[tuple[str, str], dict]] = []

        with mock.patch(
            "musorg.core.stages.metadata_read.resolve_album_metadata",
            return_value={"musicbrainz": None, "deezer": None, "deezer_result": None, "path": "musicbrainz-fallback", "timings": {}},
        ) as resolve_mock:
            def capture_fallback(group_key, payload):
                fallback_events.append((group_key, payload))

            fetch_album_metadata(album_keys, on_fallback=capture_fallback)
            callback = resolve_mock.call_args.kwargs["on_fallback"]
            callback({"from": "deezer", "to": "musicbrainz", "reason": "no_candidates", "path": "musicbrainz-fallback", "progress": "matching"})

        self.assertEqual(fallback_events[0][0], ("source-a", "album"))
        self.assertEqual(fallback_events[0][1]["reason"], "no_candidates")

    def test_fetch_album_metadata_logs_reuse_in_developer_mode(self):
        album_keys = {
            ("source-a", "album"): ("Artist", "Album", 1, ["Track 1"], None),
            ("source-b", "album"): ("Artist", "Album", 1, ["Track 1"], None),
        }

        with (
            runtime_options(developer_mode=True),
            mock.patch(
                "musorg.core.stages.metadata_read.get_album_data",
                return_value={
                    "success": False,
                    "metadata": None,
                    "reason": "no_candidates",
                    "terminal": True,
                },
            ),
            mock.patch("musorg.core.stages.metadata_read.fetch_metadata", return_value=None),
            mock.patch("musorg.core.stages.metadata_read.log") as log_mock,
        ):
            fetch_album_metadata(album_keys)

        self.assertTrue(any("Reusing in-run resolved metadata for album Artist - Album" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("Skipping duplicate Deezer resolution for Artist - Album" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("Skipping duplicate MusicBrainz lookup for Artist - Album" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("⏱️ Album metadata total:" in call.args[1] for call in log_mock.call_args_list))

    def test_musicbrainz_cover_fills_missing_cover(self):
        track = {
            "albumartist": "Unknown",
            "cover_width": 0,
            "cover_height": 0,
        }

        apply_musicbrainz_album_metadata(
            track,
            {
                "albumartist": "Хаски",
                "cover": "https://coverartarchive.org/release/test/front-500",
            },
        )

        self.assertEqual(track["cover"], "https://coverartarchive.org/release/test/front-500")

    def test_musicbrainz_cover_does_not_override_high_res_embedded_cover(self):
        track = {
            "albumartist": "Unknown",
            "cover_width": 1200,
            "cover_height": 1200,
        }

        apply_musicbrainz_album_metadata(
            track,
            {
                "albumartist": "Хаски",
                "cover": "https://coverartarchive.org/release/test/front-500",
            },
        )

        self.assertNotIn("cover", track)

    def test_release_track_count_prefers_available_matched_tracklist(self):
        track = {}

        apply_release_track_count(
            track,
            {
                "tracks": [{"tracknumber": 1}],
            },
            {
                "tracks": [{"tracknumber": 1}, {"tracknumber": 2}],
            },
        )

        self.assertEqual(track["release_track_count"], 2)

    def test_pick_deezer_track_metadata_falls_back_to_title_when_source_position_is_wrong(self):
        track = {
            "title": "Ripe (With Decay)",
            "tracknumber": 11,
        }
        deezer_data = {
            "tracks": [
                {"title": "Somewhat Damaged", "tracknumber": 1, "discnumber": 1},
                {"title": "Ripe (With Decay)", "tracknumber": 11, "discnumber": 2},
            ],
            "expected_track_count": 2,
        }

        picked = pick_deezer_track_metadata(track, deezer_data, source_position=1)

        self.assertEqual(picked["title"], "Ripe (With Decay)")
        self.assertEqual(picked["discnumber"], 2)

    def test_pick_deezer_track_metadata_uses_title_match_for_partial_album_group(self):
        track = {
            "title": "Ripe (With Decay)",
            "tracknumber": 1,
        }
        deezer_data = {
            "tracks": [
                {"title": "Somewhat Damaged", "tracknumber": 1, "discnumber": 1},
                {"title": "Ripe (With Decay)", "tracknumber": 11, "discnumber": 2},
            ],
            "expected_track_count": 1,
        }

        picked = pick_deezer_track_metadata(track, deezer_data, source_position=1)

        self.assertEqual(picked["title"], "Ripe (With Decay)")
        self.assertEqual(picked["discnumber"], 2)

    def test_deezer_does_not_override_musicbrainz_release_type(self):
        track = {
            "albumartist": "Unknown",
            "artist": "Хаски",
            "releasetype": "single",
            "tracknumber": 1,
            "cover_width": 0,
            "cover_height": 0,
        }

        apply_musicbrainz_album_metadata(
            track,
            {
                "albumartist": "Хаски",
                "releasetype": "ep",
            },
        )
        apply_deezer_metadata(
            track,
            {
                "albumartist": "Хаски",
                "releasetype": "single",
                "tracks": [{"artist": "Хаски", "title": "track", "tracknumber": 1}],
                "expected_track_count": 1,
            },
            preserve_release_type=True,
        )

        self.assertEqual(track["releasetype"], "ep")

    def test_deezer_cover_does_not_override_high_res_embedded_cover(self):
        track = {
            "albumartist": "Unknown",
            "artist": "Хаски",
            "tracknumber": 1,
            "cover_width": 1200,
            "cover_height": 1200,
        }

        apply_deezer_metadata(
            track,
            {
                "cover": "https://cdn.deezer.com/cover.jpg",
                "tracks": [{"artist": "Хаски", "title": "track", "tracknumber": 1}],
                "expected_track_count": 1,
            },
        )

        self.assertNotIn("cover", track)

    def test_musicbrainz_release_type_survives_deezer_complete_flow_without_canonical_title(self):
        track = {
            "albumartist": "Unknown",
            "artist": "Хаски",
            "releasetype": "single",
            "tracknumber": 1,
        }
        musicbrainz_data = {
            "albumartist": "Хаски",
            "releasetype": "ep",
            "use_canonical_album_title": False,
        }
        deezer_data = {
            "albumartist": "Хаски",
            "releasetype": "single",
            "tracks": [{"artist": "Хаски", "title": "track", "tracknumber": 1}],
            "expected_track_count": 1,
        }

        apply_musicbrainz_album_metadata(track, musicbrainz_data)
        apply_deezer_metadata(
            track,
            deezer_data,
            preserve_track_title=False,
            preserve_track_artist=False,
            preserve_album_metadata=bool(musicbrainz_data.get("use_canonical_album_title")),
            preserve_release_type=bool(musicbrainz_data.get("releasetype")),
        )

        self.assertEqual(track["releasetype"], "ep")

    def test_deezer_exact_track_count_match_overwrites_stale_title_by_position(self):
        track = {
            "albumartist": "Eminem",
            "artist": "Eminem",
            "title": "Wrong Bonus Track Title",
            "tracknumber": 21,
        }
        deezer_data = {
            "tracks": [
                {"artist": "Eminem", "title": "Track 1", "tracknumber": 1},
                {"artist": "Eminem", "title": "Track 21", "tracknumber": 21},
            ],
            "expected_track_count": 2,
        }

        apply_deezer_metadata(track, deezer_data, source_position=2)

        self.assertEqual(track["title"], "Track 21")

    def test_metadata_stage_uses_musicbrainz_when_deezer_is_rejected(self):
        source_file = "/music/Artist/Album/01 Track.flac"
        original_track = {
            "path": source_file,
            "artist": "Artist",
            "albumartist": "Artist",
            "album": "Album",
            "title": "Track 1",
            "tracknumber": 1,
            "discnumber": 1,
            "date": "2001",
            "releasetype": "",
            "release_date_iso": "",
            "singleoriginaltracknumber": 1,
        }
        normalized_track = dict(original_track)
        context = Context("/music", dry_run=True)
        context.files = [source_file]
        context.run_report = RunReport("/music", dry_run=True)

        with (
            mock.patch("musorg.core.stages.metadata_read.read_tags", return_value=original_track),
            mock.patch("musorg.core.stages.metadata_read.normalize_track", return_value=normalized_track),
            mock.patch(
                "musorg.core.stages.metadata_read.fetch_album_metadata",
                return_value=(
                    {
                        source_album_group_key(original_track): {
                            "albumartist": "Artist",
                            "album": "MusicBrainz Album",
                            "date": "02-03-2004",
                            "date_iso": "2004-03-02",
                            "releasetype": "album",
                            "tracks": [{"title": "MB Track 1", "tracknumber": 1, "discnumber": 1, "artist": "Artist"}],
                            "expected_track_count": 1,
                            "use_canonical_album_title": False,
                        }
                    },
                    {source_album_group_key(original_track): None},
                ),
            ),
        ):
            metadata_stage(context)

        self.assertEqual(context.tracks[0]["title"], "MB Track 1")
        self.assertEqual(context.tracks[0]["albumartist"], "Artist")
        self.assertEqual(context.tracks[0]["releasetype"], "album")
        self.assertEqual(context.tracks[0]["release_date_iso"], "2004-03-02")


if __name__ == "__main__":
    unittest.main()
