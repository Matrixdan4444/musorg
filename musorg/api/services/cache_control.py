from __future__ import annotations

from musorg.api.schemas.music import ClearCacheResponse
from musorg.services.cache import cache_clear_namespaces
from musorg.services.deezer import _ALBUM_DATA_CACHE_NAMESPACE, clear_deezer_cache
from musorg.services.musicbrainz import (
    _METADATA_CACHE_NAMESPACE,
    _ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE,
    clear_musicbrainz_caches,
)
from musorg.utils.debug import log


def clear_pipeline_cache() -> ClearCacheResponse:
    clear_deezer_cache()
    clear_musicbrainz_caches()
    cleared_entries = cache_clear_namespaces(
        _ALBUM_DATA_CACHE_NAMESPACE,
        _METADATA_CACHE_NAMESPACE,
        _ORIGINAL_RELEASE_DATE_CACHE_NAMESPACE,
    )

    log("Developer", "[DEV MODE] Metadata cache cleared", "🧪")
    log("Developer", "[DEV MODE] Processing state cleared", "🧪")
    log("Developer", "[DEV MODE] Cache cleared", "🧪")

    return ClearCacheResponse(
        cleared=True,
        metadataEntriesCleared=cleared_entries,
        processingStateCleared=True,
    )
