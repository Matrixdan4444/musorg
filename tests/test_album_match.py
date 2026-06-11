import unittest

from musorg.services.album_match import (
    LookupInput,
    album_titles_match,
    build_candidate_evidence,
    build_deezer_album_query_plan,
    evidence_confidence,
    locale_track_sequence_title_rescue,
    normalize_album_title,
    russian_transliteration_variant,
    select_preferred_metadata_provider,
)


class AlbumMatchEngineTests(unittest.TestCase):
    def test_normalize_album_title_strips_credit_like_suffix(self):
        self.assertEqual(
            normalize_album_title("моими глазами (prod. by xmindmemories)"),
            "моими глазами",
        )

    def test_normalize_album_title_strips_soundtrack_suffix(self):
        self.assertEqual(
            normalize_album_title("The Dark Knight (Original Motion Picture Soundtrack)"),
            "dark knight",
        )

    def test_normalize_album_title_strips_explicit_suffix(self):
        self.assertEqual(
            normalize_album_title("Minutes To Midnight (Explicit)"),
            "minutes to midnight",
        )

    def test_album_titles_match_handles_transliteration(self):
        self.assertTrue(album_titles_match("СТЫД ИЛИ СЛАВА", "STYD ILI SLAVA"))

    def test_album_titles_match_accepts_base_title_before_colon_suffix(self):
        self.assertTrue(
            album_titles_match("Teenage Dream", "Teenage Dream: The Complete Confection")
        )

    def test_album_titles_match_accepts_parenthetical_subtitle_same_work(self):
        self.assertTrue(
            album_titles_match("Holy Wood", "Holy Wood (In the Shadow of the Valley of Death)")
        )

    def test_album_titles_match_accepts_parenthetical_and_colon_subtitle_variants(self):
        self.assertTrue(
            album_titles_match("Lest We Forget (The Best Of)", "Lest We Forget: The Best Of")
        )

    def test_album_titles_match_accepts_multilingual_gloss_in_parentheses(self):
        self.assertTrue(
            album_titles_match("Yoshu Fukushu", "予襲復讐 (Yoshu Fukushu)")
        )

    def test_album_titles_match_does_not_fuzz_unrelated_titles(self):
        self.assertFalse(album_titles_match("Holy Wood", "Hollywood"))

    def test_russian_transliteration_variant_preserves_parenthetical_content(self):
        self.assertEqual(
            russian_transliteration_variant("STYD ILI SLAVA (Live)"),
            "СТЫД ИЛИ СЛАВА (Live)",
        )

    def test_build_deezer_album_query_plan_orders_strong_queries_first(self):
        plan = build_deezer_album_query_plan("The Hatters", "Golden Hits")

        self.assertEqual(plan[0].phase, "strong")
        self.assertEqual(plan[0].query, 'artist:"The Hatters" album:"Golden Hits"')
        self.assertEqual(plan[-1].strength, "album-only")

    def test_candidate_evidence_prefers_exact_track_count_and_strict_title(self):
        evidence = build_candidate_evidence(
            candidate_artists=["Des Rocs"],
            requested_artist="Des Rocs",
            candidate_title="Dream Machine",
            requested_album="Dream Machine",
            record_type="album",
            candidate_track_count=15,
            expected_track_count=15,
            preferred_release_type="album",
            track_title_sequence_score=100.0,
            completeness_score=5,
        )

        self.assertTrue(evidence.exact_track_count)
        self.assertTrue(evidence.strict_title_match)
        self.assertEqual(evidence_confidence(evidence), "high")

    def test_locale_track_sequence_title_rescue_accepts_exact_count_and_strong_track_evidence(self):
        evidence = build_candidate_evidence(
            candidate_artists=["Shortparis"],
            requested_artist="Shortparis",
            candidate_title="Дочери",
            requested_album="The Daughters",
            record_type="album",
            candidate_track_count=10,
            expected_track_count=10,
            preferred_release_type="album",
            track_title_sequence_score=100.0,
            completeness_score=5,
        )

        self.assertTrue(locale_track_sequence_title_rescue(evidence))

    def test_select_preferred_metadata_provider_can_choose_musicbrainz(self):
        lookup = LookupInput(
            artist="Artist",
            album="Album",
            expected_track_count=2,
            expected_titles=("Track 1", "Track 2"),
            preferred_release_type="album",
        )
        deezer = {
            "albumartist": "Artist",
            "album": "Album",
            "releasetype": "album",
            "tracks": [{"title": "Wrong 1"}, {"title": "Wrong 2"}],
            "expected_track_count": 2,
        }
        musicbrainz = {
            "albumartist": "Artist",
            "album": "Album",
            "releasetype": "album",
            "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
            "expected_track_count": 2,
        }

        self.assertEqual(
            select_preferred_metadata_provider(deezer, musicbrainz, lookup),
            "musicbrainz",
        )


if __name__ == "__main__":
    unittest.main()
