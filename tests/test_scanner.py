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

    def test_scan_files_includes_all_supported_formats_and_skips_others(self):
        with tempfile.TemporaryDirectory() as root:
            album = os.path.join(root, "Album")
            os.makedirs(album)
            supported = ["a.flac", "b.wav", "c.aiff", "d.m4a", "e.FLAC"]
            unsupported = ["notes.txt", "track.mp3", "cover.jpg", "song.ogg"]
            for name in supported + unsupported:
                with open(os.path.join(album, name), "wb") as handle:
                    handle.write(b"")

            scanned = {os.path.basename(path) for path in scan_files(root)}

        self.assertEqual(scanned, set(supported))

    def test_scan_files_is_recursive_and_sorted(self):
        with tempfile.TemporaryDirectory() as root:
            disc_two = os.path.join(root, "Album", "Disc 2")
            disc_one = os.path.join(root, "Album", "Disc 1")
            os.makedirs(disc_two)
            os.makedirs(disc_one)
            paths = [
                os.path.join(disc_one, "02. B.flac"),
                os.path.join(disc_one, "01. A.flac"),
                os.path.join(disc_two, "01. C.flac"),
            ]
            for path in paths:
                with open(path, "wb") as handle:
                    handle.write(b"")

            scanned = scan_files(root)

        # Directories and filenames are both walked in normalized sorted order.
        self.assertEqual(
            scanned,
            [
                os.path.join(disc_one, "01. A.flac"),
                os.path.join(disc_one, "02. B.flac"),
                os.path.join(disc_two, "01. C.flac"),
            ],
        )
