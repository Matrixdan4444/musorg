import unittest

from musorg.filesystem import tagging
from musorg.filesystem.tagging import (
    clear_comment_tags,
    default_metadata_preservation_settings,
    normalize_metadata_preservation_settings,
    read_existing_flac_pictures,
    remove_cover_art,
    reset_cover_download_cache,
    restore_flac_pictures,
)


class MetadataPreservationSettingsTests(unittest.TestCase):
    def test_none_returns_defaults(self):
        self.assertEqual(
            normalize_metadata_preservation_settings(None),
            default_metadata_preservation_settings(),
        )

    def test_partial_override_merges_only_booleans(self):
        merged = normalize_metadata_preservation_settings(
            {
                "artwork": {"saveCoverJpg": True, "embedArtwork": "yes"},
                "unknownSection": {"x": True},
            }
        )
        # Boolean override applied.
        self.assertTrue(merged["artwork"]["saveCoverJpg"])
        # Non-boolean value ignored -> default kept.
        self.assertTrue(merged["artwork"]["embedArtwork"])
        # Unknown section dropped; known sections still present.
        self.assertNotIn("unknownSection", merged)
        self.assertIn("core", merged)

    def test_returns_independent_copy(self):
        first = normalize_metadata_preservation_settings(None)
        first["core"]["trackTitle"] = False
        second = normalize_metadata_preservation_settings(None)
        self.assertTrue(second["core"]["trackTitle"])


class GracefulFailureTests(unittest.TestCase):
    """The write/read helpers must never raise on a missing or unreadable path."""

    def test_clear_comment_tags_on_missing_file_does_not_raise(self):
        clear_comment_tags("/no/such/file.flac")

    def test_remove_cover_art_on_missing_file_does_not_raise(self):
        remove_cover_art("/no/such/file.flac")

    def test_restore_flac_pictures_with_no_pictures_is_noop(self):
        restore_flac_pictures("/no/such/file.flac", [])

    def test_read_existing_flac_pictures_on_missing_file_returns_empty(self):
        self.assertEqual(read_existing_flac_pictures("/no/such/file.flac"), [])


class CoverDownloadCacheTests(unittest.TestCase):
    def test_reset_clears_cache(self):
        tagging._COVER_DOWNLOAD_CACHE["http://example/cover.jpg"] = (b"x", "image/jpeg")
        reset_cover_download_cache()
        self.assertEqual(tagging._COVER_DOWNLOAD_CACHE, {})


if __name__ == "__main__":
    unittest.main()
