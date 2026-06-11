from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from musorg.core.cover_art import load_album_cover_bytes


class CoreCoverArtTests(unittest.TestCase):
    @patch("musorg.core.cover_art.FLAC")
    def test_load_album_cover_bytes_prefers_embedded_flac_picture(self, flac_mock):
        flac_mock.return_value = type("Audio", (), {
            "pictures": [type("Picture", (), {"data": b"embedded-cover"})()],
        })()

        with tempfile.TemporaryDirectory() as temp_dir:
            self._touch_file(f"{temp_dir}/Artist/Album/01 - Track.flac", b"fLaC")
            self._touch_file(f"{temp_dir}/Artist/Album/cover.jpg", b"folder-cover")

            cover_bytes = load_album_cover_bytes(f"{temp_dir}/Artist/Album")

        self.assertEqual(cover_bytes, b"embedded-cover")

    def test_load_album_cover_bytes_falls_back_to_folder_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._touch_file(f"{temp_dir}/Artist/Album/01 - Track.flac", b"fLaC")
            self._touch_file(f"{temp_dir}/Artist/Album/folder.jpg", b"folder-cover")

            cover_bytes = load_album_cover_bytes(f"{temp_dir}/Artist/Album")

        self.assertEqual(cover_bytes, b"folder-cover")

    def _touch_file(self, path: str, payload: bytes) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(payload)
