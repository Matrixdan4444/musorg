import os
import tempfile
import unittest
from pathlib import Path

from musorg.metadata.cue import (
    cue_index_to_seconds,
    cue_track_specs,
    detect_image_cue,
    parse_cue_text,
)


SINGLE_IMAGE_CUE = """REM GENRE Electronica
REM DATE 1998
PERFORMER "Massive Attack"
TITLE "Mezzanine"
FILE "Massive Attack - Mezzanine.wav" WAVE
  TRACK 01 AUDIO
    TITLE "Angel"
    PERFORMER "Massive Attack"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Risingson"
    PERFORMER "Massive Attack"
    INDEX 00 05:59:00
    INDEX 01 06:00:00
  TRACK 03 AUDIO
    TITLE "Teardrop"
    INDEX 01 10:30:00
"""

MULTI_FILE_CUE = """PERFORMER "Artist"
TITLE "Album"
FILE "01 - A.flac" WAVE
  TRACK 01 AUDIO
    TITLE "A"
    INDEX 01 00:00:00
FILE "02 - B.flac" WAVE
  TRACK 02 AUDIO
    TITLE "B"
    INDEX 01 00:00:00
"""


class CueIndexTests(unittest.TestCase):
    def test_index_to_seconds(self):
        self.assertEqual(cue_index_to_seconds("00:00:00"), 0.0)
        self.assertEqual(cue_index_to_seconds("03:45:00"), 225.0)
        self.assertEqual(cue_index_to_seconds("00:00:75"), 1.0)  # 75 frames = 1s

    def test_invalid_index_raises(self):
        with self.assertRaises(ValueError):
            cue_index_to_seconds("1:2")


class ParseCueTests(unittest.TestCase):
    def test_parses_single_image_album(self):
        sheet = parse_cue_text(SINGLE_IMAGE_CUE)
        self.assertEqual(sheet.performer, "Massive Attack")
        self.assertEqual(sheet.title, "Mezzanine")
        self.assertEqual(sheet.date, "1998")
        self.assertEqual(sheet.genre, "Electronica")
        self.assertEqual(len(sheet.file_names), 1)
        self.assertTrue(sheet.is_single_image)
        self.assertEqual([t.title for t in sheet.tracks], ["Angel", "Risingson", "Teardrop"])
        # INDEX 01 wins over the pregap INDEX 00 on track 2.
        self.assertEqual(sheet.tracks[1].start_seconds, 360.0)
        self.assertEqual(sheet.tracks[0].start_seconds, 0.0)

    def test_multi_file_cue_is_not_single_image(self):
        sheet = parse_cue_text(MULTI_FILE_CUE)
        self.assertEqual(len(sheet.file_names), 2)
        self.assertFalse(sheet.is_single_image)


class CueTrackSpecsTests(unittest.TestCase):
    def test_specs_compute_end_from_next_start_and_duration(self):
        sheet = parse_cue_text(SINGLE_IMAGE_CUE)
        specs = cue_track_specs("image.flac", sheet, image_duration=900.0)
        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0]["start"], 0.0)
        self.assertEqual(specs[0]["end"], 360.0)
        self.assertEqual(specs[1]["start"], 360.0)
        self.assertEqual(specs[1]["end"], 630.0)
        # Last track ends at the image duration.
        self.assertEqual(specs[2]["start"], 630.0)
        self.assertEqual(specs[2]["end"], 900.0)
        self.assertEqual(specs[0]["number"], 1)
        self.assertEqual(specs[2]["title"], "Teardrop")


class DetectImageCueTests(unittest.TestCase):
    def _write(self, folder: Path, name: str, content: bytes = b"") -> Path:
        path = folder / name
        path.write_bytes(content)
        return path

    def test_detects_image_even_when_cue_extension_differs(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            # cue says .wav, real file is .flac
            self._write(folder, "album.flac")
            (folder / "album.cue").write_text(SINGLE_IMAGE_CUE, encoding="utf-8")
            result = detect_image_cue(folder)
            self.assertIsNotNone(result)
            image_path, sheet = result
            self.assertEqual(os.path.basename(image_path), "album.flac")
            self.assertEqual(len(sheet.tracks), 3)

    def test_missing_image_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "album.cue").write_text(SINGLE_IMAGE_CUE, encoding="utf-8")
            self.assertIsNone(detect_image_cue(folder))

    def test_multi_file_cue_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            self._write(folder, "01 - A.flac")
            self._write(folder, "02 - B.flac")
            (folder / "album.cue").write_text(MULTI_FILE_CUE, encoding="utf-8")
            self.assertIsNone(detect_image_cue(folder))

    def test_no_cue_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            self._write(folder, "track.flac")
            self.assertIsNone(detect_image_cue(folder))


class LibraryPreviewCueTests(unittest.TestCase):
    def test_load_album_detail_expands_image_cue_into_tracks(self):
        from musorg.core.library_preview import load_album_detail

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = root / "Massive Attack" / "Mezzanine"
            folder.mkdir(parents=True)
            # Presence-only image (preview doesn't decode audio) + the cue.
            (folder / "album.flac").write_bytes(b"")
            (folder / "album.cue").write_text(SINGLE_IMAGE_CUE, encoding="utf-8")

            detail = load_album_detail(str(folder), str(root))

            self.assertEqual(len(detail.tracks), 3)
            self.assertEqual(
                [t.track_title for t in detail.tracks],
                ["Angel", "Risingson", "Teardrop"],
            )
            self.assertEqual(detail.album_title, "Mezzanine")
            self.assertEqual(detail.artist_name, "Massive Attack")


if __name__ == "__main__":
    unittest.main()
