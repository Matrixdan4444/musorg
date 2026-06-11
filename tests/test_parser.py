import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

from mutagen.flac import FLACNoHeaderError

from musorg.metadata.parser import read_tags
from musorg.metadata.normalizer import normalize_track, release_type_hint_from_album


class ReadTagsTests(unittest.TestCase):
    @patch("musorg.metadata.parser.warning")
    @patch("musorg.metadata.parser.File")
    def test_returns_none_for_invalid_audio_file(self, file_mock, warning_mock):
        file_mock.side_effect = FLACNoHeaderError("broken.flac is not a valid FLAC file")

        result = read_tags("/tmp/broken.flac")

        self.assertIsNone(result)
        warning_mock.assert_called_once()

    @patch("musorg.metadata.parser.File")
    def test_reads_release_date_from_alternate_fields(self, file_mock):
        file_mock.return_value = {
            "artist": ["Хаски"],
            "albumartist": ["Хаски"],
            "album": ["Любимые песни (воображаемых) людей"],
            "title": ["Пуля-дура"],
            "tracknumber": ["1"],
            "discnumber": ["1"],
            "releasedate": ["2017-03-31"],
        }

        result = read_tags("/tmp/test.flac")

        self.assertEqual(result["date"], "2017-03-31")
        self.assertEqual(result["release_date_iso"], "2017-03-31")

    @patch("musorg.metadata.parser.File")
    def test_reads_releasetime_and_cover_art_presence(self, file_mock):
        easy_audio = {
            "artist": ["Хаски"],
            "albumartist": ["Хаски"],
            "album": ["Любимые песни (воображаемых) людей"],
            "title": ["Пуля-дура"],
            "tracknumber": ["1"],
            "discnumber": ["1"],
            "disctotal": ["2"],
            "date": ["2017"],
            "releasetime": ["2017-03-31"],
            "musicbrainz_albumid": ["mb-release-1"],
            "musicbrainz_trackid": ["mb-track-1"],
            "replaygain_track_gain": ["-7.10 dB"],
            "replaygain_album_gain": ["-6.45 dB"],
            "compilation": ["false"],
            "explicit": ["true"],
        }
        full_audio = MagicMock()
        full_audio.pictures = [object()]
        full_audio.info.length = 181.2
        file_mock.side_effect = [easy_audio, full_audio]

        result = read_tags("/tmp/test.flac")

        self.assertEqual(result["releasetime"], "2017-03-31")
        self.assertEqual(result["disctotal"], "2")
        self.assertEqual(result["musicbrainz_release_id"], "mb-release-1")
        self.assertEqual(result["musicbrainz_track_id"], "mb-track-1")
        self.assertEqual(result["replaygain_track_gain"], "-7.10 dB")
        self.assertEqual(result["replaygain_album_gain"], "-6.45 dB")
        self.assertEqual(result["compilation"], "false")
        self.assertEqual(result["explicit"], "true")
        self.assertEqual(result["duration_seconds"], 181.2)
        self.assertTrue(result["has_date_tag"])
        self.assertTrue(result["has_releasetime_tag"])
        self.assertTrue(result["has_tracknumber_tag"])
        self.assertTrue(result["has_cover_art"])
        self.assertEqual(result["cover_width"], 0)
        self.assertEqual(result["cover_height"], 0)

    @patch("musorg.metadata.parser.File")
    def test_reads_embedded_cover_dimensions_from_flac_picture(self, file_mock):
        easy_audio = {
            "artist": ["Хаски"],
            "albumartist": ["Хаски"],
            "album": ["Любимые песни (воображаемых) людей"],
            "title": ["Пуля-дура"],
            "tracknumber": ["1"],
            "discnumber": ["1"],
            "date": ["2017"],
        }
        picture = MagicMock()
        picture.width = 1200
        picture.height = 1200
        full_audio = MagicMock()
        full_audio.pictures = [picture]
        full_audio.info.length = 181.2
        file_mock.side_effect = [easy_audio, full_audio]

        result = read_tags("/tmp/test.flac")

        self.assertEqual(result["cover_width"], 1200)
        self.assertEqual(result["cover_height"], 1200)


class NormalizeTrackDateTests(unittest.TestCase):
    def test_normalize_track_converts_iso_date_to_display_format(self):
        track = normalize_track({
            "date": "2017-03-31",
            "release_date_iso": "",
        })

        self.assertEqual(track["date"], "31-03-2017")
        self.assertEqual(track["release_date_iso"], "2017-03-31")

    def test_normalize_track_uses_release_date_iso_when_date_missing(self):
        track = normalize_track({
            "date": "0000",
            "release_date_iso": "2020-11-20",
        })

        self.assertEqual(track["date"], "20-11-2020")
        self.assertEqual(track["release_date_iso"], "2020-11-20")

    def test_normalize_track_strips_ep_suffix_from_album_title(self):
        track = normalize_track({
            "album": "Триптих о Человечине (EP)",
        })

        self.assertEqual(track["album"], "Триптих о Человечине")
        self.assertEqual(track["releasetype"], "")

    def test_normalize_track_preserves_existing_release_type(self):
        track = normalize_track({
            "album": "У (EP)",
            "releasetype": "album",
        })

        self.assertEqual(track["album"], "У")
        self.assertEqual(track["releasetype"], "album")


class ReleaseTypeHintTests(unittest.TestCase):
    def test_extracts_ep_hint_from_album_suffix(self):
        self.assertEqual(
            release_type_hint_from_album("Триптих о Человечине (EP)"),
            "ep",
        )

    def test_extracts_single_hint_from_album_suffix(self):
        self.assertEqual(
            release_type_hint_from_album("Track Title [Single]"),
            "single",
        )

    def test_returns_empty_for_non_release_suffix(self):
        self.assertEqual(
            release_type_hint_from_album("Album Name (Deluxe Edition)"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
