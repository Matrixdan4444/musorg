import unittest

from musorg.metadata.normalizer import strip_edition_suffixes, strip_version_suffixes
from musorg.services.album_match import track_title_sequence_score_from_titles


class StripEditionSuffixesTests(unittest.TestCase):
    def test_keeps_recording_variants(self):
        # Remix/live/acoustic denote a different recording -> preserved.
        self.assertIn("remix", strip_edition_suffixes("Angel (Mad Professor Remix)").lower())
        self.assertIn("live", strip_edition_suffixes("Teardrop (Live)").lower())
        self.assertIn("acoustic", strip_edition_suffixes("Song (Acoustic Version)").lower())

    def test_strips_edition_markers(self):
        # Edition markers are removed just like strip_version_suffixes.
        self.assertEqual(strip_edition_suffixes("Mezzanine (Deluxe Edition)").strip(), "Mezzanine")
        self.assertEqual(strip_edition_suffixes("Song (2019 Remaster)").strip(), "Song")

    def test_contrast_with_strip_version_suffixes(self):
        # The old stripper erases the remix marker; the new one keeps it.
        self.assertNotIn("remix", strip_version_suffixes("Angel (Mad Professor Remix)").lower())
        self.assertIn("remix", strip_edition_suffixes("Angel (Mad Professor Remix)").lower())


class TrackTitleSequenceScoreTests(unittest.TestCase):
    def test_remix_album_scores_low(self):
        score = track_title_sequence_score_from_titles(
            ["Angel", "Risingson", "Teardrop"],
            ["Angel (Mad Professor Remix)", "Risingson (Underdog Mix)", "Teardrop (Mazaru Remix)"],
        )
        self.assertLess(score, 60)

    def test_remaster_album_still_scores_high(self):
        score = track_title_sequence_score_from_titles(
            ["Angel", "Risingson", "Teardrop"],
            ["Angel (2019 Remaster)", "Risingson (2019 Remaster)", "Teardrop (2019 Remaster)"],
        )
        self.assertGreaterEqual(score, 90)

    def test_identical_titles_score_perfect(self):
        score = track_title_sequence_score_from_titles(
            ["Angel", "Risingson"],
            ["Angel", "Risingson"],
        )
        self.assertEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
