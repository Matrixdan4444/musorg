import os
import tempfile
import unittest

from musorg.filesystem.scanner import scan_files


class ScannerTests(unittest.TestCase):
    def test_scan_files_ignores_macos_appledouble_sidecars(self):
        with tempfile.TemporaryDirectory() as root:
            artist_dir = os.path.join(root, "Artist", "Album")
            os.makedirs(artist_dir)

            real_track = os.path.join(artist_dir, "01. Track.flac")
            sidecar_track = os.path.join(artist_dir, "._01. Track.flac")
            hidden_other = os.path.join(artist_dir, ".DS_Store")

            for path in (real_track, sidecar_track, hidden_other):
                with open(path, "wb") as handle:
                    handle.write(b"")

            scanned = scan_files(root)

        self.assertEqual(scanned, [real_track])
