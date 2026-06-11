from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from musorg.api.services.library import _encode_album_id, get_album_detail_payload_for_root, list_albums_for_root
from musorg.core.library_preview import AlbumDetail, AlbumPreview


class LibraryMetadataIntelligenceTests(unittest.TestCase):
    def test_album_detail_rehydrates_metadata_intelligence_from_latest_summary(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            album_dir = root / "Artist" / "Album"
            album_dir.mkdir(parents=True)
            (root / ".musorg" / "runs").mkdir(parents=True)
            summary_path = root / ".musorg" / "runs" / "run.json"
            summary_path.write_text(json.dumps({
                "changed_albums": [{
                    "source_dir": str(album_dir),
                    "output_dir": None,
                    "metadata_intelligence": {
                        "before": {"albumartist": "Unknown artist"},
                        "after": {"albumartist": "Artist"},
                        "diff": [],
                        "cleanupActions": [],
                        "providerDecisions": {"metadataProvider": "musicbrainz", "artworkProvider": None, "winner": "musicbrainz", "path": "musicbrainz-fallback", "rejectedProviders": []},
                        "matchReasoning": [],
                        "confidence": {"score": 72, "level": "medium", "label": "Medium confidence", "reasons": ["fallback"], "signals": []},
                        "suspiciousMetadata": [{"id": "provider-disagreement", "label": "Provider disagreement", "severity": "warning", "message": "Providers disagreed."}],
                    },
                }],
            }), encoding="utf-8")

            detail = AlbumDetail(
                album_title="Album",
                artist_name="Artist",
                folder_path=str(album_dir),
                status="Ready",
                tracks=[],
                album_artist="Artist",
                release_year="2018",
                genre="Rap",
                disc_number="1",
                issues=(),
            )
            with patch("musorg.api.services.library.load_album_detail", return_value=detail):
                payload = get_album_detail_payload_for_root(_encode_album_id(str(album_dir)), str(root))

        self.assertEqual(payload.album.provider, "musicbrainz")
        self.assertEqual(payload.album.confidenceLevel, "medium")
        self.assertFalse(payload.album.lowConfidence)
        self.assertIsNotNone(payload.album.metadataIntelligence)
        self.assertTrue(any(issue.id == "provider-disagreement" for issue in payload.album.issues))
        warning_metric = next(metric for metric in payload.album.metrics if metric.id == "warning")
        self.assertEqual(warning_metric.value, "1")

    def test_album_list_rehydrates_output_summary_by_output_dir(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            album_dir = root / "Artist" / "Album"
            album_dir.mkdir(parents=True)
            (root / ".musorg" / "runs").mkdir(parents=True)
            (root / ".musorg" / "runs" / "run.json").write_text(json.dumps({
                "changed_albums": [{
                    "source_dir": "/input/Artist/Album",
                    "output_dir": str(album_dir),
                    "metadata_intelligence": {
                        "before": {},
                        "after": {},
                        "diff": [],
                        "cleanupActions": [],
                        "providerDecisions": {"metadataProvider": "deezer", "artworkProvider": "deezer", "winner": "deezer", "path": "deezer-fast-path", "rejectedProviders": []},
                        "matchReasoning": [],
                        "confidence": {"score": 95, "level": "high", "label": "High confidence", "reasons": ["exact match"], "signals": []},
                        "suspiciousMetadata": [],
                    },
                }],
            }), encoding="utf-8")

            preview = AlbumPreview(
                album_title="Album",
                artist_name="Artist",
                track_count=1,
                folder_path=str(album_dir),
                status="Ready",
                issues=(),
            )
            with patch("musorg.api.services.library.scan_album_previews", return_value=[preview]):
                payload = list_albums_for_root(str(root))

        self.assertEqual(payload.albums[0].provider, "deezer")
        self.assertEqual(payload.albums[0].confidenceLevel, "high")
        self.assertFalse(payload.albums[0].lowConfidence)
        self.assertIsNotNone(payload.albums[0].metadataIntelligence)
