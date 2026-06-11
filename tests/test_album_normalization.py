import unittest

from musorg.metadata.normalizer import normalize_lookup_text_for_matching, strip_version_suffixes
from musorg.core.stages.metadata_read import (
    apply_musicbrainz_canonical_album_title,
    should_use_canonical_album_title,
)
from musorg.services.deezer import normalize_album_title
from musorg.services.musicbrainz import title_variants


class AlbumNormalizationTests(unittest.TestCase):
    def test_normalize_lookup_text_for_matching_converts_number_words(self):
        self.assertEqual(
            normalize_lookup_text_for_matching("Thirty Seconds To Mars"),
            "30 seconds to mars",
        )

    def test_normalize_lookup_text_for_matching_keeps_existing_digits_stable(self):
        self.assertEqual(
            normalize_lookup_text_for_matching("30 Seconds To Mars"),
            "30 seconds to mars",
        )

    def test_strip_version_suffixes_removes_exclusive_suffix(self):
        self.assertEqual(
            strip_version_suffixes("Album Name (Exclusive)"),
            "Album Name",
        )

    def test_normalize_album_title_removes_exclusive_word(self):
        self.assertEqual(
            normalize_album_title("Album Name (Exclusive)"),
            "album name",
        )

    def test_normalize_album_title_removes_producer_like_suffix(self):
        self.assertEqual(
            normalize_album_title("моими глазами (prod. by xmindmemories)"),
            "моими глазами",
        )

    def test_strip_version_suffixes_removes_cover_suffix(self):
        self.assertEqual(
            strip_version_suffixes("Нике (Её холодные пальцы cover)"),
            "Нике",
        )

    def test_musicbrainz_title_variants_ignore_cover_suffix(self):
        self.assertIn(
            "нике",
            title_variants("Нике (Её холодные пальцы cover)"),
        )

    def test_prefers_canonical_album_title_for_case_only_difference(self):
        self.assertTrue(
            should_use_canonical_album_title(
                "Houses Of The Holy",
                "Houses of the Holy",
            )
        )

    def test_applies_musicbrainz_canonical_album_title_for_case_only_difference(self):
        track = {"album": "Houses Of The Holy"}

        apply_musicbrainz_canonical_album_title(
            track,
            {"album": "Houses of the Holy", "use_canonical_album_title": False},
        )

        self.assertEqual(track["album"], "Houses of the Holy")


if __name__ == "__main__":
    unittest.main()
