from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from musorg.api.services.cache_control import clear_pipeline_cache
from musorg.services.cache import cache_get, cache_set, serialize_cache_key, _CACHE_MISS
from musorg.services.deezer import _ALBUM_DATA_CACHE, _ALBUM_DATA_CACHE_NAMESPACE
from musorg.services.musicbrainz import (
    _ARTIST_CACHE,
    _ARTIST_RELEASE_GROUP_CACHE,
    _METADATA_CACHE,
    _METADATA_CACHE_NAMESPACE,
    _ORIGINAL_RELEASE_DATE_CACHE,
    _ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE,
)


class CacheControlTests(unittest.TestCase):
    def test_clear_pipeline_cache_clears_provider_in_memory_and_persistent_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.sqlite3")
            deezer_key = serialize_cache_key(("artist", "album", 1, ("Track 1",), ""))
            musicbrainz_key = serialize_cache_key(("artist", "album", 1, ("track 1",), ""))

            with patch.dict("os.environ", {"MUSORG_CACHE_DB": cache_path}, clear=False):
                _ALBUM_DATA_CACHE.clear()
                _METADATA_CACHE.clear()
                _ORIGINAL_RELEASE_DATE_CACHE.clear()
                _ARTIST_CACHE.clear()
                _ARTIST_RELEASE_GROUP_CACHE.clear()

                _ALBUM_DATA_CACHE[("artist", "album", 1, ("Track 1",), "")] = {"album": "deezer"}
                _METADATA_CACHE[("artist", "album", 1, ("track 1",), "")] = {"album": "musicbrainz"}
                _ORIGINAL_RELEASE_DATE_CACHE[("artist", "album", 1, ("track 1",), "")] = {"date_iso": "2013-09-27"}
                _ARTIST_CACHE["artist"] = {"id": "artist-id"}
                _ARTIST_RELEASE_GROUP_CACHE["artist-id"] = [{"id": "rg-id"}]
                cache_set(_ALBUM_DATA_CACHE_NAMESPACE, deezer_key, {"album": "deezer"})
                cache_set(_METADATA_CACHE_NAMESPACE, musicbrainz_key, {"album": "musicbrainz"})
                cache_set(_ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE, musicbrainz_key, {"date_iso": "2013-09-27"})

                with patch("musorg.api.services.cache_control.log") as log_mock:
                    result = clear_pipeline_cache()

                self.assertTrue(result.cleared)
                self.assertTrue(result.processingStateCleared)
                self.assertGreaterEqual(result.metadataEntriesCleared, 2)
                self.assertEqual(_ALBUM_DATA_CACHE, {})
                self.assertEqual(_METADATA_CACHE, {})
                self.assertEqual(_ORIGINAL_RELEASE_DATE_CACHE, {})
                self.assertEqual(_ARTIST_CACHE, {})
                self.assertEqual(_ARTIST_RELEASE_GROUP_CACHE, {})
                self.assertIs(cache_get(_ALBUM_DATA_CACHE_NAMESPACE, deezer_key), _CACHE_MISS)
                self.assertIs(cache_get(_METADATA_CACHE_NAMESPACE, musicbrainz_key), _CACHE_MISS)
                self.assertEqual(log_mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
