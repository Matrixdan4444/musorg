"""Regression tests for Stage 1 audit hardening (data integrity / robustness).

Covers:
- replace_directory preserves recoverable data when a move fails and the
  restore also fails (no silent data loss).
- fetch_album_metadata does not abort the whole batch when one album fails.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import musorg.filesystem.organizer as organizer
from musorg.core.stages.metadata_read import fetch_album_metadata


class ReplaceDirectoryRecoveryTests(unittest.TestCase):
    def _make_dir_with_file(self, path: Path, content: str) -> None:
        path.mkdir(parents=True)
        (path / "track.flac").write_text(content)

    def test_replace_directory_replaces_existing(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source = root / "staged"
            destination = root / "Album"
            self._make_dir_with_file(source, "new")
            self._make_dir_with_file(destination, "old")

            organizer.replace_directory(str(source), str(destination))

            self.assertFalse(source.exists())
            self.assertEqual((destination / "track.flac").read_text(), "new")

    def test_replace_directory_preserves_data_when_restore_fails(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            source = root / "staged"
            destination = root / "Album"
            self._make_dir_with_file(source, "new")
            self._make_dir_with_file(destination, "original")

            real_rename = os.rename

            def fake_rename(src, dst):
                # Allow only moving the existing destination aside to its backup;
                # fail the source->destination move and the subsequent restore.
                if ".Singles.old." in os.path.basename(dst):
                    return real_rename(src, dst)
                raise OSError("simulated rename failure")

            with mock.patch.object(organizer.os, "rename", side_effect=fake_rename):
                with self.assertRaises(RuntimeError) as ctx:
                    organizer.replace_directory(str(source), str(destination))

            # The error must point the user at the recoverable backup.
            self.assertIn("preserved at", str(ctx.exception))

            # Original content still exists in a .Singles.old.* backup dir.
            backups = [p for p in root.iterdir() if p.name.startswith(".Singles.old.")]
            self.assertTrue(backups, "expected a preserved backup directory")
            preserved = (backups[0] / "track.flac").read_text()
            self.assertEqual(preserved, "original")
            # Source is untouched (its move failed), so nothing is lost.
            self.assertEqual((source / "track.flac").read_text(), "new")


class FetchAlbumMetadataResilienceTests(unittest.TestCase):
    def test_one_failing_album_does_not_abort_batch(self):
        album_keys = {
            ("Artist", "Good"): ("Artist", "Good", 1, ["t"], None, {}),
            ("Artist", "Bad"): ("Artist", "Bad", 1, ["t"], None, {}),
        }

        good_resolved = {
            "musicbrainz": {"title": "Good"},
            "deezer": {"title": "Good"},
            "deezer_result": None,
            "musicbrainz_result": None,
            "winner": "deezer",
            "path": None,
            "timings": {"deezer_phase": 0.0, "musicbrainz_fallback_phase": 0.0, "album_total": 0.0},
        }

        def fake_resolve(payload, total_albums, index, run_report=None, on_fallback=None):
            album = payload[1]
            if album == "Bad":
                raise RuntimeError("boom")
            return good_resolved

        with mock.patch(
            "musorg.core.stages.metadata_read.resolve_album_metadata",
            side_effect=fake_resolve,
        ):
            musicbrainz_data, deezer_data, _resolved = fetch_album_metadata(album_keys)

        # The good album resolved; the bad one degraded to None instead of crashing.
        self.assertEqual(musicbrainz_data[("Artist", "Good")], {"title": "Good"})
        self.assertIsNone(musicbrainz_data[("Artist", "Bad")])
        self.assertIsNone(deezer_data[("Artist", "Bad")])


if __name__ == "__main__":
    unittest.main()
