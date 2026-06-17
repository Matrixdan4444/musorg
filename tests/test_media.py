import os
import tempfile
import unittest
from unittest import mock

from musorg.filesystem import media


class ResolveExecutableTests(unittest.TestCase):
    def test_env_var_override_takes_precedence(self):
        with mock.patch.dict(os.environ, {"MUSORG_FFMPEG_BIN": "/custom/ffmpeg"}):
            self.assertEqual(media.resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN"), "/custom/ffmpeg")

    def test_falls_back_to_which_when_env_var_absent(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(media.shutil, "which", return_value="/usr/bin/ffmpeg") as which:
                self.assertEqual(media.resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN"), "/usr/bin/ffmpeg")
            which.assert_called_once_with("ffmpeg")

    def test_returns_none_when_not_found(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(media.shutil, "which", return_value=None):
                self.assertIsNone(media.resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN"))


class CreateFlacFileTests(unittest.TestCase):
    def test_lossless_source_is_copied_verbatim(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "in.flac")
            dest = os.path.join(root, "out.flac")
            payload = b"fLaC-bytes"
            with open(source, "wb") as handle:
                handle.write(payload)

            media.create_flac_file(source, dest)

            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_missing_ffmpeg_for_lossy_source_raises(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "in.wav")
            dest = os.path.join(root, "out.flac")
            with open(source, "wb") as handle:
                handle.write(b"RIFF")

            with mock.patch.object(media, "resolve_executable", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    media.create_flac_file(source, dest)


class NormalizePictureDataTests(unittest.TestCase):
    def test_returns_input_unchanged_when_sips_missing(self):
        with mock.patch.object(media, "resolve_executable", return_value=None):
            data, mime = media.normalize_picture_data(b"image-bytes", "image/png")
        self.assertEqual(data, b"image-bytes")
        self.assertEqual(mime, "image/png")


if __name__ == "__main__":
    unittest.main()
