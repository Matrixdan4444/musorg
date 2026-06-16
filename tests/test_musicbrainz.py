import os
import ssl
import tempfile
import unittest
from unittest.mock import patch

import musicbrainzngs

from musorg.core.runtime_state import runtime_options
from musorg.services.cache import _CACHE_MISS
from musorg.services.musicbrainz import (
    _METADATA_CACHE,
    _ORIGINAL_RELEASE_DATE_CACHE,
    MUSICBRAINZ_REQUEST_TIMEOUT_SECONDS,
    MUSICBRAINZ_SOCKET_MAX_RETRIES,
    MUSICBRAINZ_SOCKET_RETRY_DELAY_SECONDS,
    _build_musicbrainz_opener,
    _build_musicbrainz_ssl_context,
    _safe_musicbrainz_read,
    artist_score,
    clear_musicbrainz_caches,
    cover_art_url,
    fetch_metadata,
    fetch_metadata_result,
    fetch_original_release_date,
    find_release_by_track_titles_with_status,
    search_release_group_direct,
    soundtrack_query_variants,
    musicbrainz_call,
)


class MusicBrainzCoverTests(unittest.TestCase):
    def test_cover_art_url_uses_cover_art_archive_front(self):
        self.assertEqual(
            cover_art_url(
                {
                    "id": "cc586440-b567-4bea-822e-15f96419dcf1",
                    "cover-art-archive": {
                        "front": True,
                    },
                }
            ),
            "https://coverartarchive.org/release/cc586440-b567-4bea-822e-15f96419dcf1/front-500",
        )

    def test_cover_art_url_returns_none_without_front_cover(self):
        self.assertIsNone(
            cover_art_url(
                {
                    "id": "cc586440-b567-4bea-822e-15f96419dcf1",
                    "cover-art-archive": {
                        "front": False,
                    },
                }
            )
        )


class MusicBrainzArtistMatchingTests(unittest.TestCase):
    def test_artist_score_accepts_written_number_artist_name(self):
        exact_name, alias_match, fuzzy = artist_score(
            {"name": "Thirty Seconds To Mars", "alias-list": []},
            "30 Seconds To Mars",
        )

        self.assertTrue(exact_name)
        self.assertFalse(alias_match)
        self.assertGreaterEqual(fuzzy, 85)

    def test_soundtrack_query_variants_include_base_title(self):
        variants = soundtrack_query_variants("The Dark Knight (Original Motion Picture Soundtrack)")

        self.assertIn(("The Dark Knight", False), variants)

    def test_soundtrack_query_variants_include_versionless_album_variant(self):
        variants = soundtrack_query_variants("Minutes To Midnight (Explicit)")

        self.assertIn(("minutes to midnight", False), variants)


class MusicBrainzRetryTests(unittest.TestCase):
    @patch("musorg.services.musicbrainz.time.sleep")
    def test_musicbrainz_call_retries_network_errors_with_exponential_backoff(self, sleep_mock):
        request_mock = unittest.mock.Mock(side_effect=[
            musicbrainzngs.NetworkError(cause=OSError("temporary")),
            musicbrainzngs.NetworkError(cause=OSError("temporary")),
            {"ok": True},
        ])

        result = musicbrainz_call("search artists", request_mock)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleep_mock.call_args_list[0].args[0], 1.0)
        self.assertEqual(sleep_mock.call_args_list[1].args[0], 2.0)

    @patch("musorg.services.musicbrainz.time.sleep")
    def test_musicbrainz_call_retries_response_errors_for_rate_limits(self, sleep_mock):
        cause = unittest.mock.Mock()
        cause.code = 429
        cause.headers = {"Retry-After": "4"}
        request_mock = unittest.mock.Mock(side_effect=[
            musicbrainzngs.ResponseError(cause=cause),
            {"ok": True},
        ])

        result = musicbrainz_call("search artists", request_mock)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleep_mock.call_args_list[0].args[0], 4.0)

    @patch("musorg.services.musicbrainz.time.sleep")
    def test_musicbrainz_call_does_not_retry_non_retriable_response_errors(self, sleep_mock):
        cause = unittest.mock.Mock()
        cause.code = 404
        request_mock = unittest.mock.Mock(side_effect=musicbrainzngs.ResponseError(cause=cause))

        with self.assertRaises(musicbrainzngs.ResponseError):
            musicbrainz_call("search artists", request_mock)

        sleep_mock.assert_not_called()


class MusicBrainzTlsTests(unittest.TestCase):
    def test_ssl_context_requires_verified_certificates(self):
        context = _build_musicbrainz_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(len(context.get_ca_certs()), 1)

    def test_custom_opener_adds_https_handler(self):
        opener = _build_musicbrainz_opener()
        https_handlers = [handler for handler in opener.handlers if handler.__class__.__name__ == "HTTPSHandler"]

        self.assertTrue(https_handlers)

    def test_custom_opener_applies_default_timeout(self):
        inner_opener = unittest.mock.Mock()

        with patch("musorg.services.musicbrainz._ORIGINAL_BUILD_OPENER", return_value=inner_opener):
            opener = _build_musicbrainz_opener()
            opener.open("https://musicbrainz.org/ws/2/release-group")

        inner_opener.open.assert_called_once()
        self.assertEqual(
            inner_opener.open.call_args.kwargs["timeout"],
            MUSICBRAINZ_REQUEST_TIMEOUT_SECONDS,
        )

    def test_safe_musicbrainz_read_clamps_internal_retries(self):
        with patch("musorg.services.musicbrainz._ORIGINAL_SAFE_READ", return_value=b"<xml />") as safe_read_mock:
            result = _safe_musicbrainz_read("opener", "request", body="body", max_retries=8, retry_delay_delta=2.0)

        self.assertEqual(result, b"<xml />")
        safe_read_mock.assert_called_once_with(
            "opener",
            "request",
            body="body",
            max_retries=MUSICBRAINZ_SOCKET_MAX_RETRIES,
            retry_delay_delta=MUSICBRAINZ_SOCKET_RETRY_DELAY_SECONDS,
        )


class MusicBrainzPersistentCacheTests(unittest.TestCase):
    def test_fetch_metadata_bypasses_cache_reads_in_developer_mode_but_still_writes(self):
        release_group = {
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
        }
        release_details = {
            "date": "2020-01-01",
            "id": "release-1",
            "medium-list": [],
        }
        stale = {"album": "Stale"}

        _METADATA_CACHE.clear()
        with (
            patch("musorg.services.musicbrainz.cache_get", side_effect=AssertionError("persistent cache should not be read")),
            patch("musorg.services.musicbrainz.cache_set") as cache_set_mock,
            patch("musorg.services.musicbrainz.search_release_group_with_status", return_value=(None, True)),
            patch("musorg.services.musicbrainz.find_release_by_track_titles_with_status", return_value=((release_group, release_details), True)),
        ):
            _METADATA_CACHE[("artist", "album", 1, ("track 1",), "")] = stale
            with runtime_options(developer_mode=True):
                result = fetch_metadata("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

        self.assertEqual(result["album"], "Album")
        self.assertNotEqual(result, stale)
        cache_set_mock.assert_called()

    def test_fetch_metadata_uses_sqlite_cache_across_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")
            release_group = {
                "title": "Album",
                "primary-type": "album",
                "artist-credit-phrase": "Artist",
            }
            release_details = {
                "date": "2020-01-01",
                "id": "release-1",
                "medium-list": [],
            }

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                _METADATA_CACHE.clear()
                with (
                    patch("musorg.services.musicbrainz.search_release_group_with_status", return_value=(None, True)),
                    patch("musorg.services.musicbrainz.find_release_by_track_titles_with_status", return_value=((release_group, release_details), True)),
                ):
                    first = fetch_metadata("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

                _METADATA_CACHE.clear()
                with (
                    patch("musorg.services.musicbrainz.search_release_group_with_status", side_effect=AssertionError("network path should not be used")),
                    patch("musorg.services.musicbrainz.find_release_by_track_titles_with_status", side_effect=AssertionError("track lookup should not be used")),
                ):
                    second = fetch_metadata("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

            self.assertEqual(first, second)
            self.assertEqual(second["date_iso"], "2020-01-01")


class MusicBrainzSoundtrackLookupTests(unittest.TestCase):
    def setUp(self):
        clear_musicbrainz_caches()

    def test_search_release_group_direct_uses_title_led_soundtrack_rescue(self):
        release_group = {
            "id": "rg-dark-knight",
            "title": "The Dark Knight (Original Motion Picture Soundtrack)",
            "primary-type": "album",
            "artist-credit-phrase": "Hans Zimmer, James Newton Howard",
            "first-release-date": "2008-07-15",
        }
        calls = []

        def fake_musicbrainz_call(_operation, _callable, *args, **kwargs):
            calls.append(kwargs)
            if kwargs.get("releasegroup") == "The Dark Knight" and "artist" not in kwargs:
                return {"release-group-list": [release_group]}
            return {"release-group-list": []}

        with patch("musorg.services.musicbrainz.musicbrainz_call", side_effect=fake_musicbrainz_call):
            result = search_release_group_direct(
                "Hans Zimmer",
                "The Dark Knight (Original Motion Picture Soundtrack)",
                expected_track_count=14,
                preferred_release_type="album",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["id"], "rg-dark-knight")
        self.assertTrue(any(call.get("releasegroup") == "The Dark Knight" and "artist" not in call for call in calls))

    def test_search_release_group_direct_uses_versionless_title_query_variant(self):
        release_group = {
            "id": "rg-minutes",
            "title": "Minutes to Midnight",
            "primary-type": "album",
            "artist-credit-phrase": "Linkin Park",
            "first-release-date": "2007-05-14",
        }
        calls = []

        def fake_musicbrainz_call(_operation, _callable, *args, **kwargs):
            calls.append(kwargs)
            if kwargs.get("releasegroup") == "minutes to midnight":
                return {"release-group-list": [release_group]}
            return {"release-group-list": []}

        with patch("musorg.services.musicbrainz.musicbrainz_call", side_effect=fake_musicbrainz_call):
            result = search_release_group_direct(
                "Linkin Park",
                "Minutes To Midnight (Explicit)",
                expected_track_count=12,
                preferred_release_type="album",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["id"], "rg-minutes")
        self.assertTrue(any(call.get("releasegroup") == "minutes to midnight" for call in calls))

    def test_search_release_group_direct_uses_complete_edition_base_title_variant(self):
        release_group = {
            "id": "rg-teenage-dream",
            "title": "Teenage Dream",
            "primary-type": "album",
            "artist-credit-phrase": "Katy Perry",
            "first-release-date": "2010-08-24",
        }
        calls = []

        def fake_musicbrainz_call(_operation, _callable, *args, **kwargs):
            calls.append(kwargs)
            if kwargs.get("releasegroup") == "teenage dream":
                return {"release-group-list": [release_group]}
            return {"release-group-list": []}

        with patch("musorg.services.musicbrainz.musicbrainz_call", side_effect=fake_musicbrainz_call):
            result = search_release_group_direct(
                "Katy Perry",
                "Teenage Dream: The Complete Confection",
                expected_track_count=19,
                preferred_release_type="album",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["id"], "rg-teenage-dream")
        self.assertTrue(any(call.get("releasegroup") == "teenage dream" for call in calls))

    def test_fetch_metadata_uses_title_first_track_rescue_for_soundtrack(self):
        release_group = {
            "id": "rg-dark-knight-rises",
            "title": "The Dark Knight Rises (Original Motion Picture Soundtrack)",
            "primary-type": "album",
            "artist-credit-phrase": "Hans Zimmer",
        }
        release = {
            "id": "rel-dark-knight-rises",
            "title": "The Dark Knight Rises (Original Motion Picture Soundtrack)",
            "track-count": 18,
        }
        release_details = {
            "id": "rel-dark-knight-rises",
            "title": "The Dark Knight Rises (Original Motion Picture Soundtrack)",
            "date": "2012-07-17",
            "artist-credit": [{"name": "Hans Zimmer", "artist": {"name": "Hans Zimmer"}}],
            "medium-list": [
                {
                    "position": "1",
                    "track-list": [
                        {
                            "position": str(index),
                            "recording": {"title": f"Track {index}"},
                        }
                        for index in range(1, 19)
                    ],
                }
            ],
        }

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.search_release_group_with_status", return_value=(None, True)),
            patch("musorg.services.musicbrainz.resolve_artist_with_status", return_value=(None, True)),
            patch("musorg.services.musicbrainz.release_group_search_results_with_status", return_value=([([release_group], False)], True)),
            patch("musorg.services.musicbrainz.browse_release_group_releases", return_value=[release]),
            patch("musorg.services.musicbrainz.get_release_details", return_value=release_details),
        ):
            result = fetch_metadata(
                "Hans Zimmer",
                "The Dark Knight Rises (Original Motion Picture Soundtrack)",
                expected_track_count=18,
                expected_titles=[f"Track {index}" for index in range(1, 19)],
                preferred_release_type="album",
                use_cache=False,
            )

        self.assertIsNotNone(result)
        self.assertEqual(
            result["album"],
            "The Dark Knight Rises (Original Motion Picture Soundtrack)",
        )
        self.assertEqual(len(result["tracks"]), 18)

    def test_find_release_by_track_titles_with_status_accepts_title_led_rescue_when_artist_is_weak(self):
        release_group = {
            "id": "rg-o-tebe",
            "title": "О тебе",
            "primary-type": "album",
            "artist-credit-phrase": "Jakone",
        }
        release = {
            "id": "rel-o-tebe",
            "title": "О тебе",
            "track-count": 9,
        }
        release_details = {
            "id": "rel-o-tebe",
            "title": "О тебе",
            "date": "2025-02-14",
            "artist-credit": [{"name": "Jakone", "artist": {"name": "Jakone"}}],
            "medium-list": [
                {
                    "position": "1",
                    "track-list": [
                        {
                            "position": str(index),
                            "recording": {"title": f"Track {index}"},
                        }
                        for index in range(1, 10)
                    ],
                }
            ],
        }

        with (
            patch("musorg.services.musicbrainz.resolve_artist_with_status", return_value=(None, True)),
            patch("musorg.services.musicbrainz.release_group_search_results_with_status", return_value=([([release_group], False)], True)),
            patch("musorg.services.musicbrainz.browse_release_group_releases", return_value=[release]),
            patch("musorg.services.musicbrainz.get_release_details", return_value=release_details),
        ):
            match, valid = find_release_by_track_titles_with_status(
                "Jakone",
                "О тебе",
                expected_track_count=9,
                expected_titles=[f"Track {index}" for index in range(1, 10)],
                preferred_release_type="album",
            )

        self.assertTrue(valid)
        self.assertIsNotNone(match)
        self.assertEqual(match[0]["id"], "rg-o-tebe")
        self.assertEqual(match[1]["id"], "rel-o-tebe")

    def test_find_release_by_track_titles_with_status_accepts_locale_title_rescue_from_track_sequence(self):
        release_group = {
            "id": "rg-kagayaki",
            "title": "かがやき",
            "primary-type": "album",
            "artist-credit-phrase": "Takagi Masakatsu",
        }
        release = {
            "id": "rel-kagayaki",
            "title": "かがやき",
            "track-count": 23,
        }
        release_details = {
            "id": "rel-kagayaki",
            "title": "かがやき",
            "date": "2011-11-23",
            "artist-credit": [{"name": "Takagi Masakatsu", "artist": {"name": "Takagi Masakatsu"}}],
            "medium-list": [
                {
                    "position": "1",
                    "track-list": [
                        {
                            "position": str(index),
                            "recording": {"title": f"Track {index}"},
                        }
                        for index in range(1, 24)
                    ],
                }
            ],
        }

        with (
            patch("musorg.services.musicbrainz.resolve_artist_with_status", return_value=({"id": "artist-1", "name": "Takagi Masakatsu"}, True)),
            patch("musorg.services.musicbrainz.browse_artist_release_groups_with_status", return_value=([release_group], True)),
            patch("musorg.services.musicbrainz.release_group_search_results_with_status", return_value=([], True)),
            patch("musorg.services.musicbrainz.browse_release_group_releases", return_value=[release]),
            patch("musorg.services.musicbrainz.get_release_details", return_value=release_details),
        ):
            match, valid = find_release_by_track_titles_with_status(
                "Takagi Masakatsu",
                "Kagayaki",
                expected_track_count=23,
                expected_titles=[f"Track {index}" for index in range(1, 24)],
                preferred_release_type="album",
            )

        self.assertTrue(valid)
        self.assertIsNotNone(match)
        self.assertEqual(match[0]["id"], "rg-kagayaki")

    def test_search_release_group_direct_accepts_compilation_release_group(self):
        release_group = {
            "id": "rg-past-masters",
            "title": "Past Masters",
            "primary-type": "compilation",
            "artist-credit-phrase": "The Beatles",
            "first-release-date": "2009-09-09",
        }

        with patch(
            "musorg.services.musicbrainz.release_group_search_results_with_status",
            return_value=([([release_group], False)], True),
        ):
            result = search_release_group_direct(
                "The Beatles",
                "Past Masters",
                expected_track_count=33,
                preferred_release_type="album",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["id"], "rg-past-masters")

    def test_fetch_metadata_result_classifies_search_failures_as_search_unavailable(self):
        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set") as cache_set_mock,
            patch("musorg.services.musicbrainz.search_release_group_with_status", return_value=(None, False)),
            patch("musorg.services.musicbrainz.find_release_by_track_titles_with_status", return_value=(None, False)),
        ):
            result = fetch_metadata_result(
                "Jakone",
                "О тебе",
                expected_track_count=9,
                expected_titles=[f"Track {index}" for index in range(1, 10)],
                preferred_release_type="album",
                use_cache=True,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "search_unavailable")
        cache_set_mock.assert_not_called()

    def test_fetch_metadata_result_returns_likely_catalog_absence_for_exhausted_empty_search(self):
        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set") as cache_set_mock,
            patch("musorg.services.musicbrainz.search_release_group_with_status", return_value=(None, True)),
            patch("musorg.services.musicbrainz.find_release_by_track_titles_with_status", return_value=(None, True)),
        ):
            result = fetch_metadata_result(
                "Markul",
                "MAKE DEPRESSION GREAT AGAIN",
                expected_track_count=10,
                expected_titles=[f"Track {index}" for index in range(1, 11)],
                preferred_release_type="album",
                use_cache=True,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "likely_catalog_absence")
        cache_set_mock.assert_not_called()


class MusicBrainzOriginalReleaseDateTests(unittest.TestCase):
    def setUp(self):
        clear_musicbrainz_caches()

    def test_fetch_original_release_date_uses_full_first_release_date_without_loading_releases(self):
        release_group = {
            "id": "rg-1",
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
            "first-release-date": "2013-09-27",
        }

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": [release_group]}),
            patch("musorg.services.musicbrainz.resolve_artist", side_effect=AssertionError("artist resolution should not be used")),
            patch("musorg.services.musicbrainz.browse_artist_release_groups", side_effect=AssertionError("artist release groups should not be browsed")),
            patch("musorg.services.musicbrainz.get_release_group_with_releases", side_effect=AssertionError("release group should not be loaded")),
            patch("musorg.services.musicbrainz.browse_release_group_releases", side_effect=AssertionError("releases should not be browsed")),
        ):
            result = fetch_original_release_date("Artist", "Album", expected_track_count=3, expected_titles=["Track 1"])

        self.assertEqual(
            result,
            {
                "date": "27-09-2013",
                "date_iso": "2013-09-27",
                "expected_track_count": 3,
                "year": "2013",
            },
        )

    def test_fetch_original_release_date_browses_releases_when_search_result_only_has_year(self):
        search_result = {
            "id": "rg-1",
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
            "first-release-date": "2013",
        }
        release_group = {
            "id": "rg-1",
            "title": "Album",
            "release-list": [],
        }
        browsed_releases = [
            {"title": "Album", "status": "Official", "date": "2013-09-27"},
            {"title": "Album", "status": "Official", "date": "2017-09-08"},
        ]

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": [search_result]}),
            patch("musorg.services.musicbrainz.resolve_artist", side_effect=AssertionError("artist resolution should not be used")),
            patch("musorg.services.musicbrainz.browse_artist_release_groups", side_effect=AssertionError("artist release groups should not be browsed")),
            patch("musorg.services.musicbrainz.get_release_group_with_releases", return_value=release_group),
            patch("musorg.services.musicbrainz.browse_release_group_releases", return_value=browsed_releases),
        ):
            result = fetch_original_release_date("Artist", "Album", expected_track_count=3)

        self.assertEqual(result["date_iso"], "2013-09-27")
        self.assertEqual(result["date"], "27-09-2013")
        self.assertEqual(result["year"], "2013")

    def test_fetch_original_release_date_falls_back_to_artist_browse_when_direct_search_misses(self):
        release_group = {
            "id": "rg-1",
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
            "first-release-date": "2013-09-27",
        }

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": []}),
            patch("musorg.services.musicbrainz.search_release_group", return_value=(release_group, False)) as fallback_search_mock,
        ):
            result = fetch_original_release_date("Artist", "Album", expected_track_count=3)

        fallback_search_mock.assert_called_once()
        self.assertEqual(result["date_iso"], "2013-09-27")

    def test_fetch_original_release_date_reuses_direct_match_cache_for_equivalent_inputs(self):
        release_group = {
            "id": "rg-1",
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
            "first-release-date": "2013-09-27",
        }

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": [release_group]}) as musicbrainz_call_mock,
        ):
            first = fetch_original_release_date("Artist", "Album", expected_track_count=1)
            first_call_count = musicbrainz_call_mock.call_count
            _ORIGINAL_RELEASE_DATE_CACHE.clear()
            second = fetch_original_release_date("Artist", " Album!!! ", expected_track_count=1)

        self.assertEqual(first, second)
        self.assertEqual(musicbrainz_call_mock.call_count, first_call_count)

    def test_fetch_original_release_date_records_direct_hit_metrics(self):
        from musorg.core.run_report import RunReport

        report = RunReport("/tmp/music", dry_run=True)
        release_group = {
            "id": "rg-1",
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
            "first-release-date": "2013-09-27",
        }

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": [release_group]}),
        ):
            fetch_original_release_date("Artist", "Album", expected_track_count=1, run_report=report)

        metrics = report.profiling_summary()["metrics"]
        self.assertEqual(metrics["metadata_musicbrainz_date_direct_hit"]["count"], 1)
        self.assertNotIn("metadata_musicbrainz_date_artist_fallback", metrics)

    def test_fetch_original_release_date_records_fallback_metrics(self):
        from musorg.core.run_report import RunReport

        report = RunReport("/tmp/music", dry_run=True)
        release_group = {
            "id": "rg-1",
            "title": "Album",
            "primary-type": "album",
            "artist-credit-phrase": "Artist",
            "first-release-date": "2013-09-27",
        }

        with (
            patch("musorg.services.musicbrainz.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.musicbrainz.cache_set"),
            patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": []}),
            patch("musorg.services.musicbrainz.search_release_group", return_value=(release_group, False)),
        ):
            fetch_original_release_date("Artist", "Album", expected_track_count=1, run_report=report)

        metrics = report.profiling_summary()["metrics"]
        self.assertEqual(metrics["metadata_musicbrainz_date_direct_miss"]["count"], 1)
        self.assertEqual(metrics["metadata_musicbrainz_date_artist_fallback"]["count"], 1)

    def test_fetch_original_release_date_uses_sqlite_cache_across_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")
            release_group = {
                "id": "rg-1",
                "title": "Album",
                "primary-type": "album",
                "artist-credit-phrase": "Artist",
                "first-release-date": "2013-09-27",
            }

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                clear_musicbrainz_caches()
                with patch("musorg.services.musicbrainz.musicbrainz_call", return_value={"release-group-list": [release_group]}):
                    first = fetch_original_release_date("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

                clear_musicbrainz_caches()
                with patch("musorg.services.musicbrainz.musicbrainz_call", side_effect=AssertionError("network path should not be used")):
                    second = fetch_original_release_date("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

            self.assertEqual(first, second)
            self.assertEqual(second["date_iso"], "2013-09-27")


if __name__ == "__main__":
    unittest.main()
