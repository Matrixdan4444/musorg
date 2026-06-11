import os
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

import requests

from musorg.core.runtime_state import runtime_options
from musorg.core.stages.metadata_read import apply_deezer_metadata
from musorg.services.cache import cache_get, serialize_cache_key
from musorg.services.deezer import (
    _ALBUM_DATA_CACHE,
    _CACHE_MISS,
    ALBUM_SEARCH_QUERY_BUDGET,
    TRACK_SEARCH_QUERY_BUDGET,
    _ALBUM_DATA_CACHE_NAMESPACE,
    album_search_queries,
    album_details_match,
    album_query_variants,
    album_titles_match,
    artist_match,
    artist_query_variants,
    canonical_album_artist,
    contributor_artist_names,
    format_tracks,
    get_album,
    get_album_data,
    get_json,
    hydrate_album_track_pages,
    deezer_track_count_matches_expected,
    deezer_failure_is_cacheable,
    deezer_resolution_metadata,
    exact_album_search_queries,
    extract_deezer_page_release_date,
    fallback_album_data_from_candidate,
    generic_track_probe_title,
    pick_album_candidate,
    pick_album_from_track_candidates,
    representative_track_titles,
    search_album_candidates,
    search_album_candidates_with_status,
    search_track_candidates,
    request_with_retry,
)


class ContributorArtistNamesTests(unittest.TestCase):
    def test_splits_composite_main_artist_credit(self):
        track_data = {
            "artist": {"name": "SALUKI, 104"},
        }

        self.assertEqual(
            contributor_artist_names(track_data),
            "SALUKI, 104",
        )

    def test_ignores_album_level_contributors_for_track_credit(self):
        track_data = {
            "artist": {"name": "FRIENDLY THUG 52 NGG"},
        }
        album_data = {
            "contributors": [
                {"name": "FRIENDLY THUG 52 NGG"},
                {"name": "SALUKI"},
                {"name": "LOCO OG ROCKA"},
            ],
        }

        self.assertEqual(
            contributor_artist_names(track_data, album_data),
            "FRIENDLY THUG 52 NGG",
        )

    def test_keeps_distinct_track_level_contributors(self):
        track_data = {
            "artist": {"name": "FRIENDLY THUG 52 NGG"},
            "contributors": [
                {"name": "FRIENDLY THUG 52 NGG"},
                {"name": "SALUKI"},
            ],
        }

        self.assertEqual(
            contributor_artist_names(track_data),
            "FRIENDLY THUG 52 NGG, SALUKI",
        )


class DeezerPageReleaseDateTests(unittest.TestCase):
    def test_extract_deezer_page_release_date_prefers_music_release_date_meta(self):
        html = """
        <html>
          <head>
            <meta property="music:release_date" content="2013-09-27">
            <meta name="description" content="Album - release date: 9/8/17">
          </head>
        </html>
        """

        self.assertEqual(extract_deezer_page_release_date(html), "2013-09-27")

    def test_extract_deezer_page_release_date_falls_back_to_seo_description(self):
        html = """
        <html>
          <head>
            <meta name="description" content="Listen to Album by Artist on Deezer — Number of tracks: 3 | Length: 07:04 | Release date: 9/27/13.">
          </head>
        </html>
        """

        self.assertEqual(extract_deezer_page_release_date(html), "2013-09-27")


class DeezerArtistMatchingTests(unittest.TestCase):
    def test_album_titles_match_latin_request_to_cyrillic_deezer_title(self):
        self.assertTrue(
            album_titles_match("СТЫД ИЛИ СЛАВА", "STYD ILI SLAVA")
        )

    def test_album_titles_match_ignores_leading_article(self):
        self.assertTrue(
            album_titles_match("Lion and the Cobra", "The Lion and the Cobra")
        )

    def test_album_titles_match_ignores_producer_like_suffix(self):
        self.assertTrue(
            album_titles_match("моими глазами (prod. by xmindmemories)", "моими глазами")
        )

    def test_album_titles_match_accepts_parenthetical_subtitle_same_work(self):
        self.assertTrue(
            album_titles_match("Holy Wood", "Holy Wood (In the Shadow of the Valley of Death)")
        )

    def test_album_query_variants_include_articleless_form(self):
        self.assertIn(
            "lion and the cobra",
            album_query_variants("The Lion and the Cobra"),
        )

    def test_album_query_variants_strip_generic_bracketed_media_hint(self):
        self.assertIn(
            "pawn shoppe heart",
            album_query_variants("Pawn Shoppe Heart (DMD Album)"),
        )

    def test_album_query_variants_include_soundtrack_base_title(self):
        self.assertIn(
            "dark knight",
            album_query_variants("The Dark Knight (Original Motion Picture Soundtrack)"),
        )

    def test_matches_latinized_deezer_artist_to_cyrillic_request(self):
        matched, score = artist_match("Skryptonite", "Скриптонит")

        self.assertTrue(matched)
        self.assertGreaterEqual(score, 85)

    def test_matches_written_number_artist_to_numeric_request(self):
        matched, score = artist_match("Thirty Seconds To Mars", "30 Seconds To Mars")

        self.assertTrue(matched)
        self.assertGreaterEqual(score, 85)

    def test_adds_latin_transliteration_query_variants(self):
        self.assertIn("skryptonit", artist_query_variants("Скриптонит"))

    def test_exact_artist_query_variants_skip_transliteration(self):
        self.assertEqual(
            artist_query_variants("Скриптонит", include_transliteration=False),
            ["Скриптонит"],
        )

    def test_exact_artist_query_variants_keep_collaboration_credit_exact(self):
        self.assertEqual(
            artist_query_variants("Индаблэк & Скриптонит & qurt", include_transliteration=False),
            ["Индаблэк & Скриптонит & qurt"],
        )

    def test_prefers_requested_cyrillic_artist_for_latinized_deezer_page(self):
        self.assertEqual(
            canonical_album_artist("Skryptonite", "Скриптонит"),
            "Скриптонит",
        )

    def test_album_search_queries_keep_broad_album_lookup_last(self):
        queries = album_search_queries(
            "Индаблэк & Скриптонит & qurt",
            "Плохие привычки",
            artist_query_mode="exact",
            include_album_only_queries=True,
        )

        self.assertTrue(queries[-1].endswith("Плохие привычки"))
        self.assertIn('artist:"Индаблэк & Скриптонит & qurt" album:"Плохие привычки"', queries[0])
        self.assertNotIn('"Индаблэк & Скриптонит & qurt" "Плохие привычки"', queries)

    def test_album_search_queries_include_loose_artist_album_query_before_album_only_fallback(self):
        queries = album_search_queries(
            "The Von Bondies",
            "Pawn Shoppe Heart (DMD Album)",
        )

        self.assertIn("The Von Bondies pawn shoppe heart", queries)
        self.assertLess(
            queries.index("The Von Bondies pawn shoppe heart"),
            queries.index("pawn shoppe heart"),
        )

    def test_album_search_queries_include_split_credit_rescue_queries_for_collaborations(self):
        queries = album_search_queries(
            "104 & Truwer",
            "Сафари",
        )

        self.assertIn('artist:"Truwer" album:"Сафари"', queries)
        self.assertIn("Truwer Сафари", queries)

    def test_exact_album_search_queries_include_normalized_album_variant(self):
        queries = exact_album_search_queries(
            "The Von Bondies",
            "Pawn Shoppe Heart (DMD Album)",
        )

        self.assertIn(
            'artist:"The Von Bondies" album:"pawn shoppe heart"',
            queries,
        )

    def test_search_album_candidates_stays_within_query_budget_for_collaboration_credit(self):
        queries = []

        def fake_load_search_query_results(_url, query):
            queries.append(query)
            return [], True, (query, "empty", 0)

        with patch("musorg.services.deezer.load_search_query_results", side_effect=fake_load_search_query_results):
            results = search_album_candidates(
                "Индаблэк & Скриптонит & qurt",
                "Плохие привычки",
                artist_query_mode="exact",
                include_album_only_queries=False,
            )

        self.assertEqual(results, [])
        self.assertLessEqual(len(queries), ALBUM_SEARCH_QUERY_BUDGET)

    def test_search_album_candidates_with_status_keeps_later_better_track_count_match(self):
        base = {
            "id": 763788401,
            "title": "Dream Machine",
            "record_type": "album",
            "artist": {"name": "Des Rocs"},
            "nb_tracks": 9,
        }
        expanded = {
            "id": 763862411,
            "title": "Dream Machine (The Lucid Edition)",
            "record_type": "album",
            "artist": {"name": "Des Rocs"},
            "nb_tracks": 15,
        }

        with patch(
            "musorg.services.deezer.load_search_query_results",
            side_effect=lambda _url, query: ([base, expanded], True, (query, "results", 2)),
        ):
            results, valid, _attempts = search_album_candidates_with_status("Des Rocs", "Dream Machine")

        self.assertTrue(valid)
        self.assertEqual([item["id"] for item in results], [763788401, 763862411])

    def test_search_album_candidates_with_status_treats_error_payload_as_search_unavailable(self):
        with patch("musorg.services.deezer.request_with_retry") as request_mock:
            response = unittest.mock.Mock()
            response.json.return_value = {"error": {"type": "Exception", "message": "Oops"}}
            request_mock.return_value = response

            results, valid, attempts = search_album_candidates_with_status("The Hatters", "Golden Hits")

        self.assertEqual(results, [])
        self.assertFalse(valid)
        self.assertEqual(attempts[0], ('artist:"The Hatters" album:"Golden Hits"', "error payload", None))

    def test_search_track_candidates_stays_within_query_budget(self):
        queries = []

        def fake_load_search_query_results(_url, query):
            queries.append(query)
            return [], True, (query, "empty", 0)

        with patch("musorg.services.deezer.load_search_query_results", side_effect=fake_load_search_query_results):
            results = search_track_candidates(
                "Скриптонит",
                ["Плохие привычки"],
                artist_query_mode="exact",
            )

        self.assertEqual(results, [])
        self.assertLessEqual(len(queries), TRACK_SEARCH_QUERY_BUDGET)

    def test_generic_track_probe_title_identifies_short_generic_titles(self):
        self.assertTrue(generic_track_probe_title("Intro"))
        self.assertTrue(generic_track_probe_title("Outro"))
        self.assertFalse(generic_track_probe_title("Плохие привычки"))

    def test_representative_track_titles_skip_generic_titles_and_pick_diverse_titles(self):
        titles = representative_track_titles(
            [
                "Intro",
                "Плохие привычки",
                "Интро",
                "Танцуй сама",
                "Outro",
                "Тихий океан",
                "Плохие привычки",
                "Ночной рейс",
            ]
        )

        self.assertLessEqual(len(titles), 4)
        self.assertNotIn("Intro", titles)
        self.assertNotIn("Outro", titles)
        self.assertIn("Плохие привычки", titles)
        self.assertIn("Тихий океан", titles)

    def test_album_details_match_checks_album_contributors(self):
        self.assertTrue(
            album_details_match(
                {
                    "title": "On the Run",
                    "record_type": "single",
                    "artist": {"name": "Primary Artist"},
                    "contributors": [{"name": "ALBLAK 52", "role": "Main"}],
                },
                "ALBLAK 52",
                "On the Run",
            )
        )

    def test_album_details_match_splits_composite_album_artist_credit(self):
        self.assertTrue(
            album_details_match(
                {
                    "title": "STYD ILI SLAVA",
                    "record_type": "album",
                    "artist": {"name": "SALUKI, 104"},
                },
                "SALUKI",
                "STYD ILI SLAVA",
            )
        )

    def test_album_details_match_accepts_transliterated_album_request(self):
        self.assertTrue(
            album_details_match(
                {
                    "title": "СТЫД ИЛИ СЛАВА",
                    "record_type": "album",
                    "artist": {"name": "SALUKI"},
                    "contributors": [{"name": "104", "role": "Main"}],
                },
                "SALUKI",
                "STYD ILI SLAVA",
            )
        )

    def test_album_details_match_accepts_missing_deezer_leading_article(self):
        self.assertTrue(
            album_details_match(
                {
                    "title": "Lion and the Cobra",
                    "record_type": "album",
                    "artist": {"name": "Sinéad O'Connor"},
                },
                "Sinead O Connor",
                "The Lion and the Cobra",
            )
        )

    def test_album_details_match_accepts_written_number_artist_name(self):
        self.assertTrue(
            album_details_match(
                {
                    "title": "A Beautiful Lie",
                    "record_type": "album",
                    "artist": {"name": "Thirty Seconds To Mars"},
                },
                "30 Seconds To Mars",
                "A Beautiful Lie",
            )
        )

    def test_pick_album_candidate_hydrates_exact_title_for_contributor_match(self):
        candidate = {
            "id": 123,
            "title": "On the Run",
            "record_type": "single",
            "artist": {"name": "Primary Artist"},
            "nb_tracks": 1,
        }
        album_data = {
            **candidate,
            "contributors": [{"name": "ALBLAK 52", "role": "Main"}],
        }

        with patch("musorg.services.deezer.get_album", return_value=album_data):
            picked = pick_album_candidate([candidate], "ALBLAK 52", "On the Run")

        self.assertIs(picked, candidate)
        self.assertIs(picked["_album_data"], album_data)

    def test_pick_album_candidate_rejects_one_track_remix_when_searching_full_album(self):
        candidate = {
            "id": 123,
            "title": "Lust For Life (BloodPop Remix)",
            "record_type": "single",
            "artist": {"name": "Lana Del Rey"},
            "nb_tracks": 1,
        }

        picked = pick_album_candidate(
            [candidate],
            "Lana Del Rey",
            "Lust For Life",
            expected_track_count=16,
        )

        self.assertIsNone(picked)

    def test_pick_album_candidate_prefers_exact_track_count_for_expanded_edition(self):
        base = {
            "id": 103248,
            "title": "The Eminem Show",
            "record_type": "album",
            "artist": {"name": "Eminem"},
            "nb_tracks": 20,
        }
        expanded = {
            "id": 320098917,
            "title": "The Eminem Show (Expanded Edition)",
            "record_type": "album",
            "artist": {"name": "Eminem"},
            "nb_tracks": 38,
        }

        picked = pick_album_candidate(
            [expanded, base],
            "Eminem",
            "The Eminem Show",
            expected_track_count=38,
        )

        self.assertIs(picked, expanded)

    def test_pick_album_candidate_prefers_lucid_edition_when_track_count_matches(self):
        base = {
            "id": 763788401,
            "title": "Dream Machine",
            "record_type": "album",
            "artist": {"name": "Des Rocs"},
            "nb_tracks": 9,
        }
        expanded = {
            "id": 763862411,
            "title": "Dream Machine (The Lucid Edition)",
            "record_type": "album",
            "artist": {"name": "Des Rocs"},
            "nb_tracks": 15,
        }

        picked = pick_album_candidate(
            [base, expanded],
            "Des Rocs",
            "Dream Machine",
            expected_track_count=15,
        )

        self.assertIs(picked, expanded)

    def test_pick_album_candidate_prefers_hydrated_candidate_with_exact_track_count(self):
        shallow_base = {
            "id": 763788401,
            "title": "Dream Machine",
            "record_type": "album",
            "artist": {"name": "Des Rocs"},
            "nb_tracks": 15,
        }
        shallow_expanded = {
            "id": 763862411,
            "title": "Dream Machine (The Lucid Edition)",
            "record_type": "album",
            "artist": {"name": "Des Rocs"},
            "nb_tracks": 9,
        }
        hydrated_base = dict(shallow_base, nb_tracks=9)
        hydrated_expanded = dict(shallow_expanded, nb_tracks=15)

        with patch(
            "musorg.services.deezer.get_album",
            side_effect=[hydrated_base, hydrated_expanded],
        ):
            picked = pick_album_candidate(
                [shallow_base, shallow_expanded],
                "Des Rocs",
                "Dream Machine",
                expected_track_count=15,
                hydrate_candidates=True,
            )

        self.assertIs(picked, shallow_expanded)
        self.assertEqual(picked["_album_data"]["nb_tracks"], 15)

    def test_pick_album_candidate_prefers_soundtrack_variant_with_exact_track_count(self):
        base = {
            "id": 1,
            "title": "Blade Runner 2049",
            "record_type": "album",
            "artist": {"name": "Hans Zimmer"},
            "nb_tracks": 12,
        }
        soundtrack = {
            "id": 2,
            "title": "Blade Runner 2049 (Original Motion Picture Soundtrack)",
            "record_type": "album",
            "artist": {"name": "Hans Zimmer"},
            "nb_tracks": 24,
        }

        picked = pick_album_candidate(
            [base, soundtrack],
            "Hans Zimmer",
            "Blade Runner 2049 (Original Motion Picture Soundtrack)",
            expected_track_count=24,
        )

        self.assertIs(picked, soundtrack)

    def test_pick_album_candidate_accepts_hydrated_collaboration_candidate(self):
        candidate = {
            "id": 777,
            "title": "Сафари",
            "record_type": "album",
            "artist": {"name": "104"},
            "nb_tracks": 12,
        }
        hydrated = {
            "id": 777,
            "title": "Сафари",
            "record_type": "album",
            "artist": {"name": "104"},
            "contributors": [{"name": "Truwer"}],
            "nb_tracks": 12,
            "tracks": {"data": [{"title": f"Track {index}"} for index in range(1, 13)]},
        }

        with patch("musorg.services.deezer.get_album", return_value=hydrated):
            picked = pick_album_candidate(
                [candidate],
                "104 & Truwer",
                "Сафари",
                expected_track_count=12,
                expected_titles=[f"Track {index}" for index in range(1, 13)],
                hydrate_candidates=True,
            )

        self.assertIs(picked, candidate)
        self.assertEqual(picked["_album_data"]["contributors"][0]["name"], "Truwer")

    def test_pick_album_candidate_rechecks_title_cluster_candidate_after_hydration(self):
        candidate = {
            "id": 919,
            "title": "Infest The Rats' Nest",
            "record_type": "album",
            "artist": {"name": "King Gizzard"},
            "nb_tracks": 9,
        }
        hydrated = {
            "id": 919,
            "title": "Infest The Rats' Nest",
            "record_type": "album",
            "artist": {"name": "King Gizzard"},
            "contributors": [{"name": "King Gizzard & The Lizard Wizard"}],
            "nb_tracks": 9,
            "tracks": {"data": [{"title": f"Track {index}"} for index in range(1, 10)]},
        }

        with patch("musorg.services.deezer.get_album", return_value=hydrated):
            picked = pick_album_candidate(
                [candidate],
                "King Gizzard & The Lizard Wizard",
                "Infest The Rats' Nest",
                expected_track_count=9,
                expected_titles=[f"Track {index}" for index in range(1, 10)],
                hydrate_candidates=True,
            )

        self.assertIs(picked, candidate)
        self.assertEqual(
            picked["_album_data"]["contributors"][0]["name"],
            "King Gizzard & The Lizard Wizard",
        )

    def test_pick_album_candidate_accepts_credit_like_album_suffix(self):
        candidate = {
            "id": 952991621,
            "title": "моими глазами (prod. by xmindmemories)",
            "record_type": "album",
            "artist": {"name": "Cold Carti"},
            "nb_tracks": 8,
        }

        picked = pick_album_candidate(
            [candidate],
            "Cold Carti",
            "моими глазами",
            expected_track_count=8,
        )

        self.assertIs(picked, candidate)

    def test_pick_album_candidate_accepts_colon_vs_parenthetical_same_work_variant(self):
        candidate = {
            "id": 991,
            "title": "Lest We Forget: The Best Of",
            "record_type": "album",
            "artist": {"name": "Marilyn Manson"},
            "nb_tracks": 19,
        }

        picked = pick_album_candidate(
            [candidate],
            "Marilyn Manson",
            "Lest We Forget (The Best Of)",
            expected_track_count=19,
        )

        self.assertIs(picked, candidate)

    def test_pick_album_candidate_prefers_strict_title_when_track_count_is_ambiguous(self):
        base = {
            "id": 103248,
            "title": "The Eminem Show",
            "record_type": "album",
            "artist": {"name": "Eminem"},
            "nb_tracks": 20,
        }
        expanded = {
            "id": 320098917,
            "title": "The Eminem Show (Expanded Edition)",
            "record_type": "album",
            "artist": {"name": "Eminem"},
            "nb_tracks": 38,
        }

        picked = pick_album_candidate(
            [expanded, base],
            "Eminem",
            "The Eminem Show",
            expected_track_count=25,
        )

        self.assertIs(picked, base)

    def test_pick_album_candidate_accepts_written_number_artist_name(self):
        candidate = {
            "id": 123,
            "title": "A Beautiful Lie",
            "record_type": "album",
            "artist": {"name": "Thirty Seconds To Mars"},
            "nb_tracks": 12,
        }

        picked = pick_album_candidate(
            [candidate],
            "30 Seconds To Mars",
            "A Beautiful Lie",
            expected_track_count=12,
        )

        self.assertIs(picked, candidate)

    def test_pick_album_from_track_candidates_uses_track_contributors(self):
        track = {
            "id": 456,
            "title": "On the Run",
            "artist": {"name": "Primary Artist"},
            "contributors": [{"name": "ALBLAK 52"}],
            "album": {"id": 123},
        }
        album_data = {
            "id": 123,
            "title": "On the Run",
            "record_type": "single",
            "artist": {"name": "Primary Artist"},
            "nb_tracks": 1,
        }

        with (
            patch("musorg.services.deezer.get_track", return_value=track),
            patch("musorg.services.deezer.get_album", return_value=album_data),
        ):
            picked = pick_album_from_track_candidates([{"id": 456}], "ALBLAK 52", "On the Run", ["On the Run"])

        self.assertEqual(picked["id"], 123)
        self.assertIs(picked["_album_data"], album_data)
        self.assertTrue(picked["_matched_by_track"])

    def test_pick_album_from_track_candidates_rejects_wrong_backing_album(self):
        track = {
            "id": 456,
            "title": "Winter Shiettt",
            "artist": {"name": "ALBLAK 52"},
            "contributors": [{"name": "ALBLAK 52"}],
            "album": {"id": 123},
        }
        album_data = {
            "id": 123,
            "title": "Winter Shiettt",
            "record_type": "single",
            "artist": {"name": "ALBLAK 52"},
            "nb_tracks": 1,
        }

        with (
            patch("musorg.services.deezer.get_track", return_value=track),
            patch("musorg.services.deezer.get_album", return_value=album_data),
        ):
            picked = pick_album_from_track_candidates(
                [{"id": 456}],
                "ALBLAK 52",
                "On the Run",
                ["On the Run", "Winter Shiettt"],
            )

        self.assertIsNone(picked)


class DeezerMetadataMergeTests(unittest.TestCase):
    def test_deezer_metadata_updates_discnumber(self):
        track = {
            "artist": "Nine Inch Nails",
            "albumartist": "Nine Inch Nails",
            "title": "Track",
            "tracknumber": 1,
            "discnumber": 3,
        }
        deezer_data = {
            "tracks": [
                {
                    "artist": "Nine Inch Nails",
                    "title": "Track",
                    "tracknumber": 1,
                    "discnumber": 2,
                }
            ],
            "expected_track_count": 1,
        }

        apply_deezer_metadata(track, deezer_data)

        self.assertEqual(track["discnumber"], 2)

    def test_deezer_metadata_clamps_unmatched_bonus_track_discnumber_to_album_max(self):
        track = {
            "artist": "Nine Inch Nails",
            "albumartist": "Nine Inch Nails",
            "title": "10 Miles High",
            "tracknumber": 17,
            "discnumber": 3,
        }
        deezer_data = {
            "tracks": [
                {
                    "artist": "Nine Inch Nails",
                    "title": "Somewhat Damaged",
                    "tracknumber": 1,
                    "discnumber": 1,
                },
                {
                    "artist": "Nine Inch Nails",
                    "title": "Ripe (With Decay)",
                    "tracknumber": 11,
                    "discnumber": 2,
                },
            ],
            "expected_track_count": 25,
            "max_discnumber": 2,
        }

        apply_deezer_metadata(track, deezer_data)

        self.assertEqual(track["discnumber"], 2)

    def test_preserved_track_artist_still_picks_up_missing_guest(self):
        track = {
            "artist": "FRIENDLY THUG 52 NGG",
            "albumartist": "FRIENDLY THUG 52 NGG",
            "title": "Track",
            "tracknumber": 1,
        }
        deezer_data = {
            "tracks": [
                {
                    "artist": "FRIENDLY THUG 52 NGG, SALUKI",
                    "title": "Track",
                    "tracknumber": 1,
                }
            ],
            "expected_track_count": 1,
        }

        apply_deezer_metadata(track, deezer_data, preserve_track_artist=True)

        self.assertEqual(track["artist"], "FRIENDLY THUG 52 NGG, SALUKI")

    def test_preserved_track_artist_ignores_album_artist_only_deezer_credit(self):
        track = {
            "artist": "FRIENDLY THUG 52 NGG",
            "albumartist": "FRIENDLY THUG 52 NGG",
            "title": "Track",
            "tracknumber": 1,
        }
        deezer_data = {
            "tracks": [
                {
                    "artist": "FRIENDLY THUG 52 NGG",
                    "title": "Track",
                    "tracknumber": 1,
                }
            ],
            "expected_track_count": 1,
        }

        apply_deezer_metadata(track, deezer_data, preserve_track_artist=True)

        self.assertEqual(track["artist"], "FRIENDLY THUG 52 NGG")


class DeezerTrackFormattingTests(unittest.TestCase):
    def test_format_tracks_prefers_album_disc_layout_when_track_details_disagree(self):
        album_data = {
            "tracks": {
                "data": [
                    {"id": 1, "title": "Track 1"},
                    {"id": 2, "title": "Track 2"},
                ],
            },
        }

        with patch(
            "musorg.services.deezer.get_track",
            side_effect=[
                {"title": "Track 1", "track_position": 1, "disk_number": 1, "artist": {"name": "Eminem"}},
                {"title": "Track 2", "track_position": 2, "disk_number": 2, "artist": {"name": "Eminem"}},
            ],
        ):
            tracks = format_tracks(album_data)

        self.assertEqual(tracks[0]["tracknumber"], 1)
        self.assertEqual(tracks[1]["tracknumber"], 2)
        self.assertIsNone(tracks[0]["discnumber"])
        self.assertIsNone(tracks[1]["discnumber"])

    def test_format_tracks_falls_back_to_sequential_positions_when_album_omits_them(self):
        album_data = {
            "tracks": {
                "data": [
                    {"id": 1, "title": "Track 1"},
                    {"id": 2, "title": "Track 2"},
                ],
            },
        }

        with patch(
            "musorg.services.deezer.get_track",
            side_effect=[
                {"title": "Track 1", "artist": {"name": "Eminem"}},
                {"title": "Track 2", "artist": {"name": "Eminem"}},
            ],
        ):
            tracks = format_tracks(album_data)

        self.assertEqual([track["tracknumber"] for track in tracks], [1, 2])


class DeezerAlbumFetchTests(unittest.TestCase):
    def test_get_album_hydrates_paginated_track_list(self):
        album_payload = {
            "id": 320098917,
            "title": "The Eminem Show (Expanded Edition)",
            "tracks": {
                "data": [{"id": 1, "title": "Track 1"}],
                "next": "https://api.deezer.com/album/320098917/tracks?index=1",
            },
        }
        second_page = {
            "data": [{"id": 2, "title": "Track 2"}],
            "next": "https://api.deezer.com/album/320098917/tracks?index=2",
        }
        third_page = {
            "data": [{"id": 3, "title": "Track 3"}],
        }

        with patch(
            "musorg.services.deezer.get_json",
            side_effect=[album_payload, second_page, third_page],
        ):
            album = get_album(320098917)

        self.assertEqual(
            [track["id"] for track in album["tracks"]["data"]],
            [1, 2, 3],
        )
        self.assertNotIn("next", album["tracks"])

    def test_hydrate_album_track_pages_falls_back_to_page_tracks_when_api_is_short(self):
        album_payload = {
            "id": 320098917,
            "nb_tracks": 38,
            "tracks": {
                "data": [{"id": 1, "title": "Track 1"} for _ in range(25)],
            },
        }
        page_tracks = [
            {"id": 100 + idx, "title": f"Track {idx}", "track_position": idx, "disk_number": 1}
            for idx in range(1, 39)
        ]

        with patch(
            "musorg.services.deezer.page_album_tracks",
            return_value=page_tracks,
        ):
            album = hydrate_album_track_pages(album_payload)

        self.assertEqual(len(album["tracks"]["data"]), 38)
        self.assertEqual(album["tracks"]["data"][0]["id"], 101)
        self.assertEqual(album["tracks"]["data"][-1]["id"], 138)


class DeezerRetryTests(unittest.TestCase):
    @patch("musorg.services.deezer.time.sleep")
    @patch("musorg.services.deezer.request_session")
    def test_request_with_retry_retries_timeout_with_exponential_backoff(self, request_session_mock, sleep_mock):
        response = unittest.mock.Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        session = unittest.mock.Mock()
        session.get.side_effect = [
            requests.Timeout("timeout"),
            requests.Timeout("timeout"),
            response,
        ]
        request_session_mock.return_value = session

        result = request_with_retry("https://api.deezer.com/test")

        self.assertIs(result, response)
        self.assertEqual(sleep_mock.call_args_list[0].args[0], 0.75)
        self.assertEqual(sleep_mock.call_args_list[1].args[0], 1.5)

    @patch("musorg.services.deezer.time.sleep")
    @patch("musorg.services.deezer.request_session")
    def test_request_with_retry_honors_retry_after_for_rate_limits(self, request_session_mock, sleep_mock):
        rate_limited = unittest.mock.Mock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "3"}

        ok_response = unittest.mock.Mock()
        ok_response.status_code = 200
        ok_response.headers = {}
        ok_response.raise_for_status.return_value = None

        session = unittest.mock.Mock()
        session.get.side_effect = [rate_limited, ok_response]
        request_session_mock.return_value = session

        result = request_with_retry("https://api.deezer.com/test")

        self.assertIs(result, ok_response)
        self.assertEqual(sleep_mock.call_args_list[0].args[0], 3.0)

    @patch("musorg.services.deezer.warning")
    @patch("musorg.services.deezer.request_session")
    def test_get_json_returns_none_after_non_retriable_http_error(self, request_session_mock, warning_mock):
        response = unittest.mock.Mock()
        response.status_code = 404
        response.raise_for_status.side_effect = requests.HTTPError("not found", response=response)
        session = unittest.mock.Mock()
        session.get.return_value = response
        request_session_mock.return_value = session

        result = get_json("https://api.deezer.com/test")

        self.assertIsNone(result)
        warning_mock.assert_called_once()


class DeezerPersistentCacheTests(unittest.TestCase):
    def test_transient_album_details_failure_is_not_cacheable(self):
        self.assertFalse(
            deezer_failure_is_cacheable(
                {"success": False, "metadata": None, "reason": "album_details_unavailable", "terminal": True}
            )
        )

    def test_negative_match_failures_are_not_cacheable(self):
        for reason in ("no_candidates", "no_acceptable_candidate", "track_count_mismatch", "search_unavailable"):
            with self.subTest(reason=reason):
                self.assertFalse(
                    deezer_failure_is_cacheable(
                        {"success": False, "metadata": None, "reason": reason, "terminal": True}
                    )
                )

    def test_fallback_album_data_uses_album_page_tracks(self):
        candidate = {
            "id": 100,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "nb_tracks": 2,
            "cover_xl": "cover-xl",
        }
        with patch(
            "musorg.services.deezer.page_album_tracks",
            return_value=[
                {"id": 1, "title": "Track 1", "track_position": 1, "disk_number": 1, "artist": {"name": "Artist"}},
                {"id": 2, "title": "Track 2", "track_position": 2, "disk_number": 1, "artist": {"name": "Artist"}},
            ],
        ):
            result = fallback_album_data_from_candidate(candidate)

        self.assertEqual(result["title"], "Album")
        self.assertEqual(result["nb_tracks"], 2)
        self.assertEqual(len(result["tracks"]["data"]), 2)

    def test_get_album_data_bypasses_cache_reads_in_developer_mode_but_still_writes(self):
        candidate = {
            "id": 123,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "nb_tracks": 1,
        }
        album_data = {
            "id": 123,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "tracks": {"data": [{"title": "Track 1", "track_position": 1}]},
            "release_date": "2020-01-01",
            "cover_xl": None,
            "cover_big": None,
        }
        stale = {"album": "Stale"}

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", side_effect=AssertionError("persistent cache should not be read")),
            patch("musorg.services.deezer.cache_set") as cache_set_mock,
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
            patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
            patch("musorg.services.deezer.get_album", return_value=album_data),
            patch("musorg.services.deezer.format_tracks", return_value=[{"title": "Track 1", "tracknumber": 1, "discnumber": None, "artist": "Artist"}]),
        ):
            _ALBUM_DATA_CACHE[("artist", "album", 1, ("Track 1",), "", "expanded", True, True)] = stale
            with runtime_options(developer_mode=True):
                result = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

        self.assertEqual(deezer_resolution_metadata(result)["album"], "Album")
        self.assertNotEqual(result, stale)
        cache_set_mock.assert_called()

    def test_deezer_track_count_matches_expected_requires_exact_match(self):
        self.assertTrue(
            deezer_track_count_matches_expected(
                [{"tracknumber": 1}, {"tracknumber": 2}],
                2,
            )
        )
        self.assertFalse(
            deezer_track_count_matches_expected(
                [{"tracknumber": 1}, {"tracknumber": 2}],
                3,
            )
        )

    def test_get_album_data_rejects_mismatched_track_count_and_warns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")
            candidate = {
                "id": 123,
                "title": "Album",
                "record_type": "album",
                "artist": {"name": "Artist"},
                "nb_tracks": 9,
            }
            album_data = {
                "id": 123,
                "title": "Album",
                "record_type": "album",
                "artist": {"name": "Artist"},
                "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 10)]},
                "release_date": "2020-01-01",
                "cover_xl": None,
                "cover_big": None,
            }

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                _ALBUM_DATA_CACHE.clear()
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
                    patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
                    patch("musorg.services.deezer.get_album", return_value=album_data),
                    patch(
                        "musorg.services.deezer.format_tracks",
                        return_value=[{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Artist"} for index in range(1, 10)],
                    ),
                    patch("musorg.services.deezer.warning") as warning_mock,
                ):
                    result = get_album_data("Artist", "Album", expected_track_count=8, expected_titles=["Track 1"])

            self.assertIsNone(deezer_resolution_metadata(result))
            self.assertEqual(result["reason"], "track_count_mismatch")
            warning_mock.assert_called_once_with(
                "Deezer",
                "Deezer rejected: track count mismatch (local=8, deezer=9), falling back to MusicBrainz",
            )

    def test_get_album_data_uses_exact_query_rescue_after_empty_album_search(self):
        candidate = {
            "id": 266733242,
            "title": "Golden Hits",
            "record_type": "album",
            "artist": {"name": "The Hatters"},
            "nb_tracks": 11,
        }
        album_data = {
            "id": 266733242,
            "title": "Golden Hits",
            "record_type": "album",
            "artist": {"name": "The Hatters"},
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 12)]},
            "release_date": "2021-12-03",
            "cover_xl": None,
            "cover_big": None,
        }

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.cache_set"),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [('The Hatters Golden Hits', "empty", 0)])),
            patch(
                "musorg.services.deezer.search_exact_album_candidates_with_status",
                return_value=([candidate], True, [('artist:"The Hatters" album:"Golden Hits"', "results", 1)]),
            ),
            patch("musorg.services.deezer.format_tracks", return_value=[{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "The Hatters"} for index in range(1, 12)]),
            patch("musorg.services.deezer.get_album", return_value=album_data),
        ):
            result = get_album_data("The Hatters", "Golden Hits", expected_track_count=11, warn_on_miss=False)

        self.assertEqual(deezer_resolution_metadata(result)["album_id"], 266733242)

    def test_get_album_data_uses_representative_track_probes_for_track_fallback(self):
        _ALBUM_DATA_CACHE.clear()
        captured_titles = []

        def fake_track_search(_artist, titles, **_kwargs):
            captured_titles.extend(titles)
            return [], True, []

        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_track_candidates_with_status", side_effect=fake_track_search),
        ):
            result = get_album_data(
                "Artist",
                "Album",
                expected_track_count=8,
                expected_titles=["Intro", "Track Alpha", "Outro", "Track Beta", "Track Gamma", "Track Delta"],
                warn_on_miss=False,
            )

        self.assertEqual(result["reason"], "no_candidates")
        self.assertLessEqual(len(captured_titles), 4)
        self.assertNotIn("Intro", captured_titles)
        self.assertNotIn("Outro", captured_titles)
        self.assertIn("Track Alpha", captured_titles)

    def test_get_album_data_recovers_from_track_count_mismatch_with_deezer_rescue(self):
        base = {
            "id": 100,
            "title": "Русские песни. Послесловие",
            "record_type": "album",
            "artist": {"name": "Аффинаж"},
            "nb_tracks": 15,
        }
        expanded = {
            "id": 101,
            "title": "Русские песни. Послесловие (Deluxe)",
            "record_type": "album",
            "artist": {"name": "Аффинаж"},
            "nb_tracks": 18,
        }
        base_album_data = {
            **base,
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 16)]},
            "release_date": "2020-01-01",
            "cover_xl": None,
            "cover_big": None,
        }
        expanded_album_data = {
            **expanded,
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 19)]},
            "release_date": "2020-01-01",
            "cover_xl": None,
            "cover_big": None,
        }

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.cache_set"),
            patch(
                "musorg.services.deezer.search_album_candidates_with_status",
                side_effect=[
                    ([base], True, [('artist:"Аффинаж" album:"Русские песни. Послесловие"', "results", 1)]),
                    ([base, expanded], True, [('artist:"Аффинаж" album:"Русские песни. Послесловие"', "results", 2)]),
                ],
            ),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_track_candidates_with_status", return_value=([], True, [])),
            patch(
                "musorg.services.deezer.get_album",
                side_effect=lambda album_id: {
                    100: base_album_data,
                    101: expanded_album_data,
                }[album_id],
            ),
            patch(
                "musorg.services.deezer.format_tracks",
                side_effect=[
                    [{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Аффинаж"} for index in range(1, 16)],
                    [{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Аффинаж"} for index in range(1, 19)],
                ],
            ),
        ):
            result = get_album_data(
                "Аффинаж",
                "Русские песни. Послесловие",
                expected_track_count=18,
                expected_titles=[f"Track {index}" for index in range(1, 19)],
                warn_on_miss=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(deezer_resolution_metadata(result)["album_id"], 101)

    def test_get_album_data_recovers_marilyn_manson_best_of_same_work_variant(self):
        mismatch_candidate = {
            "id": 301,
            "title": "Lest We Forget",
            "record_type": "album",
            "artist": {"name": "Marilyn Manson"},
            "nb_tracks": 18,
        }
        rescued_candidate = {
            "id": 302,
            "title": "Lest We Forget: The Best Of",
            "record_type": "album",
            "artist": {"name": "Marilyn Manson"},
            "nb_tracks": 19,
        }
        mismatch_album_data = {
            **mismatch_candidate,
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 19)]},
            "release_date": "2004-09-25",
            "cover_xl": None,
            "cover_big": None,
        }
        rescued_album_data = {
            **rescued_candidate,
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 20)]},
            "release_date": "2004-09-25",
            "cover_xl": None,
            "cover_big": None,
        }

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.cache_set"),
            patch(
                "musorg.services.deezer.search_album_candidates_with_status",
                side_effect=[
                    ([mismatch_candidate], True, []),
                    ([mismatch_candidate, rescued_candidate], True, []),
                ],
            ),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_track_candidates_with_status", return_value=([], True, [])),
            patch(
                "musorg.services.deezer.get_album",
                side_effect=lambda album_id: {
                    301: mismatch_album_data,
                    302: rescued_album_data,
                }[album_id],
            ),
            patch(
                "musorg.services.deezer.format_tracks",
                side_effect=[
                    [{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Marilyn Manson"} for index in range(1, 19)],
                    [{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Marilyn Manson"} for index in range(1, 20)],
                ],
            ),
        ):
            result = get_album_data(
                "Marilyn Manson",
                "Lest We Forget (The Best Of)",
                expected_track_count=19,
                expected_titles=[f"Track {index}" for index in range(1, 20)],
                warn_on_miss=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(deezer_resolution_metadata(result)["album_id"], 302)

    def test_get_album_data_accepts_locale_title_via_track_sequence_rescue(self):
        candidate = {
            "id": 201,
            "title": "Дочери",
            "record_type": "album",
            "artist": {"name": "Shortparis"},
            "nb_tracks": 10,
        }
        album_data = {
            "id": 201,
            "title": "Дочери",
            "record_type": "album",
            "artist": {"name": "Shortparis"},
            "nb_tracks": 10,
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 11)]},
            "release_date": "2013-04-07",
            "cover_xl": None,
            "cover_big": None,
        }
        formatted_tracks = [
            {"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Shortparis"}
            for index in range(1, 11)
        ]

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.cache_set"),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.get_album", return_value=album_data),
            patch("musorg.services.deezer.format_tracks", return_value=formatted_tracks),
        ):
            result = get_album_data(
                "Shortparis",
                "The Daughters",
                expected_track_count=10,
                expected_titles=[f"Track {index}" for index in range(1, 11)],
                warn_on_miss=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(deezer_resolution_metadata(result)["album"], "Дочери")

    def test_pick_album_from_track_candidates_accepts_locale_title_via_track_sequence_rescue(self):
        track_candidate = {
            "id": 301,
            "title": "Track 1",
            "artist": {"name": "Shortparis"},
            "album": {"id": 419347727},
        }
        album_data = {
            "id": 419347727,
            "title": "Дочери",
            "record_type": "album",
            "artist": {"name": "Shortparis"},
            "nb_tracks": 10,
            "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 11)]},
        }

        with (
            patch("musorg.services.deezer.get_track", return_value=track_candidate),
            patch("musorg.services.deezer.get_album", return_value=album_data),
        ):
            candidate = pick_album_from_track_candidates(
                [track_candidate],
                "Shortparis",
                "The Daughters",
                ["Track 1", "Track 5", "Track 10"],
                expected_track_count=10,
                expected_titles=[f"Track {index}" for index in range(1, 11)],
                preferred_release_type="album",
            )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["id"], 419347727)
        self.assertTrue(candidate["_title_rescued_by_sequence"])

    def test_get_album_data_returns_no_candidates_when_primary_and_rescue_searches_are_empty(self):
        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.cache_set"),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [('The Hatters Golden Hits', "empty", 0)])),
            patch(
                "musorg.services.deezer.search_exact_album_candidates_with_status",
                return_value=([], True, [('artist:"The Hatters" album:"Golden Hits"', "empty", 0)]),
            ),
        ):
            result = get_album_data("The Hatters", "Golden Hits", expected_track_count=11, warn_on_miss=False)

        self.assertIsNone(deezer_resolution_metadata(result))
        self.assertEqual(result["reason"], "no_candidates")

    def test_get_album_data_does_not_cache_mismatched_track_count_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")
            candidate = {
                "id": 123,
                "title": "Album",
                "record_type": "album",
                "artist": {"name": "Artist"},
                "nb_tracks": 9,
            }
            album_data = {
                "id": 123,
                "title": "Album",
                "record_type": "album",
                "artist": {"name": "Artist"},
                "tracks": {"data": [{"title": f"Track {index}", "track_position": index} for index in range(1, 10)]},
                "release_date": "2020-01-01",
                "cover_xl": None,
                "cover_big": None,
            }

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                _ALBUM_DATA_CACHE.clear()
                search_mock = mock.Mock(return_value=([candidate], True, []))
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", search_mock),
                    patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
                    patch("musorg.services.deezer.get_album", return_value=album_data),
                    patch(
                        "musorg.services.deezer.format_tracks",
                        return_value=[{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Artist"} for index in range(1, 10)],
                    ),
                ):
                    first = get_album_data("Artist", "Album", expected_track_count=8, expected_titles=["Track 1"])

                _ALBUM_DATA_CACHE.clear()
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", search_mock),
                    patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
                    patch("musorg.services.deezer.get_album", return_value=album_data),
                    patch(
                        "musorg.services.deezer.format_tracks",
                        return_value=[{"title": f"Track {index}", "tracknumber": index, "discnumber": None, "artist": "Artist"} for index in range(1, 10)],
                    ),
                ):
                    second = get_album_data("Artist", "Album", expected_track_count=8, expected_titles=["Track 1"])

            self.assertIsNone(deezer_resolution_metadata(first))
            self.assertIsNone(deezer_resolution_metadata(second))
            self.assertEqual(first["reason"], "track_count_mismatch")
            self.assertEqual(second["reason"], "track_count_mismatch")
            self.assertEqual(search_mock.call_count, 4)

    def test_get_album_data_does_not_persist_no_candidates_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                _ALBUM_DATA_CACHE.clear()
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [])),
                    patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
                    patch("musorg.services.deezer.search_track_candidates_with_status", return_value=([], True, [])),
                ):
                    first = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

                _ALBUM_DATA_CACHE.clear()
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [])),
                    patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
                    patch("musorg.services.deezer.search_track_candidates_with_status", return_value=([], True, [])),
                ):
                    second = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

                key = serialize_cache_key(("artist", "album", 1, ("Track 1",), "", "expanded", True, True))
                self.assertIs(cache_get(_ALBUM_DATA_CACHE_NAMESPACE, key), _CACHE_MISS)

            self.assertEqual(first["reason"], "no_candidates")
            self.assertEqual(second["reason"], "no_candidates")

    def test_get_album_data_returns_search_unavailable_when_album_search_fails(self):
        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], False, [])),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], False, [])),
        ):
            result = get_album_data(
                "Artist",
                "Album",
                expected_track_count=1,
                expected_titles=["Track 1"],
                include_track_title_fallback=False,
                warn_on_miss=False,
            )

        self.assertEqual(result["reason"], "search_unavailable")

    def test_get_album_data_accepts_credit_like_album_suffix_from_deezer(self):
        candidate = {
            "id": 952991621,
            "title": "моими глазами (prod. by xmindmemories)",
            "record_type": "album",
            "artist": {"name": "Cold Carti"},
            "nb_tracks": 8,
        }
        album_data = {
            "id": 952991621,
            "title": "моими глазами (prod. by xmindmemories)",
            "record_type": "album",
            "artist": {"name": "Cold Carti"},
            "contributors": [{"name": "Cold Carti"}],
            "tracks": {
                "data": [
                    {"title": f"Track {index}", "track_position": index}
                    for index in range(1, 9)
                ]
            },
            "release_date": "2025-04-18",
            "cover_xl": None,
            "cover_big": None,
        }

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
            patch("musorg.services.deezer.get_album", return_value=album_data),
            patch(
                "musorg.services.deezer.format_tracks",
                return_value=[
                    {
                        "title": f"Track {index}",
                        "tracknumber": index,
                        "discnumber": None,
                        "artist": "Cold Carti",
                    }
                    for index in range(1, 9)
                ],
            ),
        ):
            result = get_album_data(
                "Cold Carti",
                "моими глазами",
                expected_track_count=8,
                expected_titles=["Track 1"],
                warn_on_miss=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(
            deezer_resolution_metadata(result)["album"],
            "моими глазами (prod. by xmindmemories)",
        )

    def test_get_album_data_accepts_soundtrack_suffix_from_deezer(self):
        candidate = {
            "id": 4123456,
            "title": "No Time To Die (Original Motion Picture Soundtrack)",
            "record_type": "album",
            "artist": {"name": "Hans Zimmer"},
            "nb_tracks": 21,
        }
        album_data = {
            "id": 4123456,
            "title": "No Time To Die (Original Motion Picture Soundtrack)",
            "record_type": "album",
            "artist": {"name": "Hans Zimmer"},
            "contributors": [{"name": "Hans Zimmer"}],
            "tracks": {
                "data": [
                    {"title": f"Track {index}", "track_position": index}
                    for index in range(1, 22)
                ]
            },
            "release_date": "2021-10-01",
            "cover_xl": None,
            "cover_big": None,
        }

        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
            patch("musorg.services.deezer.get_album", return_value=album_data),
            patch(
                "musorg.services.deezer.format_tracks",
                return_value=[
                    {
                        "title": f"Track {index}",
                        "tracknumber": index,
                        "discnumber": None,
                        "artist": "Hans Zimmer",
                    }
                    for index in range(1, 22)
                ],
            ),
        ):
            result = get_album_data(
                "Hans Zimmer",
                "No Time To Die",
                expected_track_count=21,
                expected_titles=["Track 1"],
                warn_on_miss=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(
            deezer_resolution_metadata(result)["album"],
            "No Time To Die (Original Motion Picture Soundtrack)",
        )

    def test_get_album_data_ignores_stale_transient_cache_failure(self):
        candidate = {
            "id": 123,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "nb_tracks": 1,
        }
        album_data = {
            "id": 123,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "tracks": {"data": [{"title": "Track 1", "track_position": 1}]},
            "release_date": "2020-01-01",
            "cover_xl": None,
            "cover_big": None,
        }

        _ALBUM_DATA_CACHE.clear()
        _ALBUM_DATA_CACHE[("artist", "album", 1, ("Track 1",), "", "expanded", True, True)] = {
            "success": False,
            "metadata": None,
            "reason": "album_details_unavailable",
            "terminal": True,
        }
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
            patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
            patch("musorg.services.deezer.get_album", return_value=album_data),
            patch("musorg.services.deezer.format_tracks", return_value=[{"title": "Track 1", "tracknumber": 1, "discnumber": None, "artist": "Artist"}]),
        ):
            result = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

        self.assertEqual(deezer_resolution_metadata(result)["album"], "Album")

    def test_get_album_data_falls_back_to_album_page_tracks_when_api_album_fails(self):
        candidate = {
            "id": 123,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "nb_tracks": 2,
            "cover_xl": None,
            "cover_big": None,
        }
        page_album_data = {
            "id": 123,
            "title": "Album",
            "record_type": "album",
            "artist": {"name": "Artist"},
            "tracks": {
                "data": [
                    {"id": 1, "title": "Track 1", "track_position": 1, "disk_number": 1, "artist": {"name": "Artist"}},
                    {"id": 2, "title": "Track 2", "track_position": 2, "disk_number": 1, "artist": {"name": "Artist"}},
                ]
            },
        }
        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
            patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
            patch("musorg.services.deezer.get_album", return_value=None),
            patch("musorg.services.deezer.fallback_album_data_from_candidate", return_value=page_album_data),
            patch(
                "musorg.services.deezer.format_tracks",
                return_value=[
                    {"title": "Track 1", "tracknumber": 1, "discnumber": 1, "artist": "Artist"},
                    {"title": "Track 2", "tracknumber": 2, "discnumber": 1, "artist": "Artist"},
                ],
            ),
        ):
            result = get_album_data("Artist", "Album", expected_track_count=2, expected_titles=["Track 1", "Track 2"])

        self.assertTrue(result["success"])
        self.assertEqual(deezer_resolution_metadata(result)["album"], "Album")

    def test_get_album_data_uses_sqlite_cache_across_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")
            candidate = {
                "id": 123,
                "title": "Album",
                "record_type": "album",
                "artist": {"name": "Artist"},
                "nb_tracks": 1,
            }
            album_data = {
                "id": 123,
                "title": "Album",
                "record_type": "album",
                "artist": {"name": "Artist"},
                "tracks": {"data": [{"title": "Track 1", "track_position": 1}]},
                "release_date": "2020-01-01",
                "cover_xl": None,
                "cover_big": None,
            }

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                _ALBUM_DATA_CACHE.clear()
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([candidate], True, [])),
                    patch("musorg.services.deezer.pick_album_candidate", return_value=candidate),
                    patch("musorg.services.deezer.get_album", return_value=album_data),
                    patch("musorg.services.deezer.format_tracks", return_value=[{"title": "Track 1", "tracknumber": 1, "discnumber": None, "artist": "Artist"}]),
                ):
                    first = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

                _ALBUM_DATA_CACHE.clear()
                with (
                    patch("musorg.services.deezer.search_album_candidates_with_status", side_effect=AssertionError("search should not be used")),
                    patch("musorg.services.deezer.pick_album_candidate", side_effect=AssertionError("pick should not be used")),
                    patch("musorg.services.deezer.get_album", side_effect=AssertionError("album fetch should not be used")),
                ):
                    second = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

            self.assertEqual(first, second)
            self.assertEqual(deezer_resolution_metadata(second)["date_iso"], "2020-01-01")

    def test_get_album_data_no_candidates_warns_with_fallback_text(self):
        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_track_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.warning") as warning_mock,
        ):
            result = get_album_data("Artist", "Album", expected_track_count=1, expected_titles=["Track 1"])

        self.assertEqual(result["reason"], "no_candidates")
        warning_mock.assert_called_once_with(
            "Deezer",
            "No album candidates found for Artist - Album, falling back to MusicBrainz",
        )

    def test_get_album_data_without_track_fallback_returns_failure_without_crashing(self):
        _ALBUM_DATA_CACHE.clear()
        with (
            patch("musorg.services.deezer.cache_get", return_value=_CACHE_MISS),
            patch("musorg.services.deezer.search_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.search_exact_album_candidates_with_status", return_value=([], True, [])),
            patch("musorg.services.deezer.warning") as warning_mock,
        ):
            result = get_album_data(
                "Artist",
                "Album",
                expected_track_count=1,
                expected_titles=["Track 1"],
                include_track_title_fallback=False,
            )

        self.assertEqual(result["reason"], "no_candidates")
        warning_mock.assert_called_once_with(
            "Deezer",
            "No album candidates found for Artist - Album, falling back to MusicBrainz",
        )


if __name__ == "__main__":
    unittest.main()
