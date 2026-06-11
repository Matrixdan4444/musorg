import json
import os
import tempfile
import unittest
from unittest.mock import ANY, MagicMock, patch

from click.testing import CliRunner

from musorg.cli.main import run
from musorg.core.pipeline import RunResult
from musorg.core.context import Context
from musorg.core.run_report import RunReport
from musorg.filesystem.naming import (
    build_output_preview_tree,
    collapse_duplicate_leading_year,
    default_output_format_settings,
    format_output_destination,
)
from musorg.filesystem.organizer import (
    SINGLES_ALBUM_TITLE,
    cleanup_stale_single_track,
    create_flac_file,
    copy_track_to_destination,
    is_standalone_single,
    normalize_picture_data,
    organize_single_tracks,
    organize_track,
    resolve_executable,
    single_release_group_key,
    single_track_identity,
    write_metadata_tags,
)
from musorg.filesystem.tagging import default_metadata_preservation_settings
from musorg.core.release_intelligence import ReleaseIntelligenceRegistry
from musorg.core.stages.organize import _album_output_root, organize_stage


class SingleTrackIdentityTests(unittest.TestCase):
    def test_ignores_album_name_for_single_deduplication(self):
        base_track = {
            "albumartist": "Хаски",
            "artist": "Хаски",
            "title": "Пуля-дура",
            "release_date_iso": "2017-03-31",
            "singleoriginaltracknumber": 1,
        }

        original_album_track = dict(base_track, album="Пуля-дура")
        singles_album_track = dict(base_track, album=SINGLES_ALBUM_TITLE)

        self.assertEqual(
            single_track_identity(original_album_track),
            single_track_identity(singles_album_track),
        )

    def test_single_release_group_key_uses_album_and_date(self):
        track = {
            "albumartist": "Хаски",
            "artist": "Хаски",
            "album": "У",
            "date": "01-01-2019",
        }

        self.assertEqual(
            single_release_group_key(track),
            ("хаски", "у", "01-01-2019"),
        )

    def test_standalone_single_detects_one_track_release_by_matching_album_and_title(self):
        track = {
            "albumartist": "Хаски",
            "artist": "Хаски",
            "album": "ТОПЬ",
            "title": "ТОПЬ",
            "releasetype": "",
            "path": "/tmp/top.flac",
        }

        self.assertTrue(is_standalone_single(track, 1))

    def test_single_release_detects_partial_multi_track_single_release(self):
        track = {
            "albumartist": "monipula",
            "artist": "monipula",
            "album": "Мимозы",
            "title": "Мимозы",
            "releasetype": "single",
            "release_track_count": 2,
            "path": "/tmp/mimozy.flac",
        }

        self.assertTrue(is_standalone_single(track, 1))

    def test_single_release_goes_to_singles_even_without_title_heuristic(self):
        track = {
            "albumartist": "monipula",
            "artist": "monipula",
            "album": "Мимозы",
            "title": "Мимозы",
            "releasetype": "single",
            "release_track_count": 2,
            "path": "/tmp/mimozy.flac",
        }

        self.assertTrue(is_standalone_single(track, 1))

    def test_large_multi_track_release_tagged_single_does_not_go_to_singles(self):
        track = {
            "albumartist": "David Bowie",
            "artist": "David Bowie",
            "album": "Scary Monsters (And Super Creeps)",
            "title": "It's No Game (No. 1)",
            "releasetype": "single",
            "release_track_count": 12,
            "path": "/tmp/01.flac",
        }

        self.assertFalse(is_standalone_single(track, 12))

    def test_ep_release_never_goes_to_singles_even_with_low_track_count(self):
        track = {
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Real EP",
            "title": "Track",
            "releasetype": "ep",
            "release_track_count": 3,
            "path": "/tmp/01.flac",
        }

        self.assertFalse(is_standalone_single(track, 1))


class OrganizeSingleTracksTests(unittest.TestCase):
    def test_writes_singles_album_tag_for_single_tracks(self):
        captured_tracks = []
        track = {
            "path": "/tmp/source.flac",
            "albumartist": "масло черного тмина",
            "artist": "масло черного тмина",
            "album": "kensshi",
            "title": "мастурбируем",
            "date": "20-11-2020",
            "release_date_iso": "2020-11-20",
            "tracknumber": 1,
            "discnumber": 1,
            "singleoriginaltracknumber": 1,
            "releasetype": "single",
        }

        def fake_copy_track_to_destination(track_data, _destination, dry_run=False, journal=None):
            captured_tracks.append(dict(track_data))

        with tempfile.TemporaryDirectory() as root_output:
            with patch("musorg.filesystem.organizer.copy_track_to_destination", side_effect=fake_copy_track_to_destination):
                copied, total = organize_single_tracks([track], root_output)

        self.assertEqual(copied, 1)
        self.assertEqual(total, 1)
        self.assertEqual(len(captured_tracks), 1)
        self.assertEqual(captured_tracks[0]["album"], SINGLES_ALBUM_TITLE)

    @patch("musorg.filesystem.organizer.log")
    @patch("musorg.filesystem.organizer.write_metadata_tags")
    @patch("musorg.filesystem.organizer.create_flac_file")
    def test_dry_run_previews_single_track_copy_without_writing(
        self,
        create_flac_file_mock,
        write_metadata_tags_mock,
        log_mock,
    ):
        track = {
            "path": "/tmp/source.flac",
            "albumartist": "масло черного тмина",
            "artist": "масло черного тмина",
            "album": "kensshi",
            "title": "мастурбируем",
            "date": "20-11-2020",
            "release_date_iso": "2020-11-20",
            "tracknumber": 1,
            "discnumber": 1,
            "singleoriginaltracknumber": 1,
            "releasetype": "single",
            "cover": "https://example.com/cover.jpg",
        }

        with tempfile.TemporaryDirectory() as root_output:
            copied, total = organize_single_tracks([track], root_output, dry_run=True)

        self.assertEqual((copied, total), (1, 1))
        create_flac_file_mock.assert_not_called()
        write_metadata_tags_mock.assert_not_called()
        self.assertTrue(any("Would copy" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("Would write tags" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("Would download cover art" in call.args[1] for call in log_mock.call_args_list))


class WriteMetadataTagsTests(unittest.TestCase):
    def _base_track(self, **overrides):
        track = {
            "artist": "Artist",
            "albumartist": "Artist",
            "album": "Album",
            "title": "Title",
            "tracknumber": 1,
            "discnumber": 1,
            "date": "0000",
            "release_date_iso": "",
            "singleoriginaltracknumber": 1,
            "cover": None,
        }
        track.update(overrides)
        return track

    @staticmethod
    def _written_tags(audio):
        return {
            call.args[0]: call.args[1]
            for call in audio.__setitem__.call_args_list
        }

    @staticmethod
    def _metadata_settings(**overrides):
        settings = default_metadata_preservation_settings()
        for section, values in overrides.items():
            settings[section].update(values)
        return settings

    @patch("musorg.filesystem.tagging.write_cover_art")
    @patch("musorg.filesystem.tagging.restore_flac_pictures")
    @patch("musorg.filesystem.tagging.clear_comment_tags")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures", return_value=[])
    @patch("musorg.filesystem.tagging.File")
    def test_writes_year_and_releasetime_for_full_iso_date(
        self,
        file_mock,
        _read_existing_flac_pictures_mock,
        _clear_comment_tags_mock,
        _restore_flac_pictures_mock,
        _write_cover_art_mock,
    ):
        audio = MagicMock()
        audio.tags = {"date": ["01-01-2001"], "release_date_iso": ["2001-01-01"]}
        file_mock.return_value = audio

        write_metadata_tags("/tmp/test.flac", self._base_track(date="10-04-2026", release_date_iso="2026-04-10"))

        written_tags = self._written_tags(audio)
        written_keys = list(written_tags)
        self.assertEqual(written_tags["DATE"], ["2026"])
        self.assertEqual(written_tags["RELEASETIME"], ["2026-04-10"])
        self.assertNotIn("date", written_keys)
        self.assertNotIn("release_date_iso", written_keys)

    @patch("musorg.filesystem.tagging.write_cover_art")
    @patch("musorg.filesystem.tagging.restore_flac_pictures")
    @patch("musorg.filesystem.tagging.clear_comment_tags")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures", return_value=[])
    @patch("musorg.filesystem.tagging.File")
    def test_writes_only_year_when_only_year_is_available(
        self,
        file_mock,
        _read_existing_flac_pictures_mock,
        _clear_comment_tags_mock,
        _restore_flac_pictures_mock,
        _write_cover_art_mock,
    ):
        audio = MagicMock()
        audio.tags = {"releasetime": ["2001-01-01"]}
        file_mock.return_value = audio

        write_metadata_tags("/tmp/test.flac", self._base_track(date="1999", release_date_iso="1999"))

        written_tags = self._written_tags(audio)
        written_keys = list(written_tags)
        self.assertEqual(written_tags["DATE"], ["1999"])
        self.assertNotIn("RELEASETIME", written_keys)

    @patch("musorg.filesystem.tagging.write_cover_art")
    @patch("musorg.filesystem.tagging.restore_flac_pictures")
    @patch("musorg.filesystem.tagging.clear_comment_tags")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures", return_value=[])
    @patch("musorg.filesystem.tagging.File")
    def test_does_not_write_releasetime_for_malformed_release_date_iso(
        self,
        file_mock,
        _read_existing_flac_pictures_mock,
        _clear_comment_tags_mock,
        _restore_flac_pictures_mock,
        _write_cover_art_mock,
    ):
        audio = MagicMock()
        audio.tags = {"releasetime": ["2001-01-01"]}
        file_mock.return_value = audio

        write_metadata_tags("/tmp/test.flac", self._base_track(date="10-04-2026", release_date_iso="10-04-2026"))

        written_tags = self._written_tags(audio)
        written_keys = list(written_tags)
        self.assertEqual(written_tags["DATE"], ["2026"])
        self.assertNotIn("RELEASETIME", written_keys)

    @patch("musorg.filesystem.tagging.write_cover_art")
    @patch("musorg.filesystem.tagging.restore_flac_pictures")
    @patch("musorg.filesystem.tagging.clear_comment_tags")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures", return_value=[])
    @patch("musorg.filesystem.tagging.File")
    def test_disabling_metadata_fields_removes_them_from_cleaned_files(
        self,
        file_mock,
        _read_existing_flac_pictures_mock,
        _clear_comment_tags_mock,
        _restore_flac_pictures_mock,
        _write_cover_art_mock,
    ):
        audio = MagicMock()
        audio.tags = {
            "artist": ["Artist"],
            "title": ["Title"],
            "musicbrainz_albumid": ["mb-release-1"],
            "replaygain_track_gain": ["-7.10 dB"],
        }
        file_mock.return_value = audio

        write_metadata_tags(
            "/tmp/test.flac",
            self._base_track(musicbrainz_release_id="mb-release-1", replaygain_track_gain="-7.10 dB"),
            metadata_preservation_settings=self._metadata_settings(
                core={"trackArtist": False, "trackTitle": False},
                library={"replayGain": False},
                advancedIds={"musicBrainzReleaseId": False},
            ),
        )

        written_tags = self._written_tags(audio)
        self.assertNotIn("artist", written_tags)
        self.assertNotIn("title", written_tags)
        self.assertNotIn("musicbrainz_albumid", written_tags)
        self.assertNotIn("replaygain_track_gain", written_tags)
        self.assertNotIn("artist", audio.tags)
        self.assertNotIn("title", audio.tags)
        self.assertNotIn("musicbrainz_albumid", audio.tags)
        self.assertNotIn("replaygain_track_gain", audio.tags)

    @patch("musorg.filesystem.tagging.write_cover_art")
    @patch("musorg.filesystem.tagging.restore_flac_pictures")
    @patch("musorg.filesystem.tagging.clear_comment_tags")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures", return_value=[])
    @patch("musorg.filesystem.tagging.File")
    def test_preserves_musicbrainz_and_replaygain_when_enabled(
        self,
        file_mock,
        _read_existing_flac_pictures_mock,
        _clear_comment_tags_mock,
        _restore_flac_pictures_mock,
        _write_cover_art_mock,
    ):
        audio = MagicMock()
        audio.tags = {}
        file_mock.return_value = audio

        write_metadata_tags(
            "/tmp/test.flac",
            self._base_track(
                musicbrainz_release_id="mb-release-1",
                musicbrainz_track_id="mb-track-1",
                replaygain_track_gain="-7.10 dB",
                replaygain_album_gain="-6.45 dB",
            ),
            metadata_preservation_settings=self._metadata_settings(),
        )

        written_tags = self._written_tags(audio)
        self.assertEqual(written_tags["musicbrainz_albumid"], ["mb-release-1"])
        self.assertEqual(written_tags["musicbrainz_trackid"], ["mb-track-1"])
        self.assertEqual(written_tags["replaygain_track_gain"], ["-7.10 dB"])
        self.assertEqual(written_tags["replaygain_album_gain"], ["-6.45 dB"])

    @patch("musorg.filesystem.tagging.build_cover_picture")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures")
    @patch("musorg.filesystem.tagging.File")
    def test_skips_picture_inspection_when_no_cover_update_is_needed(
        self,
        file_mock,
        read_existing_flac_pictures_mock,
        build_cover_picture_mock,
    ):
        audio = MagicMock()
        audio.tags = {}
        file_mock.return_value = audio

        write_metadata_tags("/tmp/test.flac", self._base_track(cover=None))

        read_existing_flac_pictures_mock.assert_not_called()
        build_cover_picture_mock.assert_not_called()

    @patch("musorg.filesystem.tagging.build_cover_picture")
    @patch("musorg.filesystem.tagging.read_existing_flac_pictures", return_value=[])
    @patch("musorg.filesystem.tagging.File")
    def test_reads_existing_pictures_from_loaded_audio_when_cover_is_present(
        self,
        file_mock,
        read_existing_flac_pictures_mock,
        build_cover_picture_mock,
    ):
        audio = MagicMock()
        audio.tags = {}
        audio.pictures = []
        file_mock.return_value = audio
        build_cover_picture_mock.return_value = MagicMock(width=1000, height=1000)

        write_metadata_tags("/tmp/test.flac", self._base_track(cover="https://example.com/cover.jpg"))

        read_existing_flac_pictures_mock.assert_called_once_with(audio)
        build_cover_picture_mock.assert_called_once()


class ExecutableResolutionTests(unittest.TestCase):
    @patch.dict("os.environ", {"MUSORG_FFMPEG_BIN": "/custom/ffmpeg"}, clear=True)
    @patch("musorg.filesystem.media.shutil.which")
    def test_resolve_executable_prefers_environment_override(self, which_mock):
        self.assertEqual(resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN"), "/custom/ffmpeg")
        which_mock.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("musorg.filesystem.media.shutil.which", return_value="/usr/local/bin/ffmpeg")
    def test_resolve_executable_falls_back_to_path_lookup(self, which_mock):
        self.assertEqual(resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN"), "/usr/local/bin/ffmpeg")
        which_mock.assert_called_once_with("ffmpeg")

    @patch("musorg.filesystem.media.shutil.which", return_value="/custom/sips")
    @patch("musorg.filesystem.media.subprocess.run", side_effect=RuntimeError("stop"))
    def test_normalize_picture_data_uses_resolved_sips_binary(self, run_mock, _which_mock):
        data, mime_type = normalize_picture_data(b"cover", "image/jpeg")

        self.assertEqual((data, mime_type), (b"cover", "image/jpeg"))
        self.assertEqual(run_mock.call_args.args[0][0], "/custom/sips")

    @patch("musorg.filesystem.media.shutil.which", return_value="/custom/ffmpeg")
    @patch("musorg.filesystem.media.subprocess.run")
    def test_create_flac_file_uses_resolved_ffmpeg_binary(self, run_mock, _which_mock):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = f"{temp_dir}/source.mp3"
            destination_path = f"{temp_dir}/output.flac"
            with open(source_path, "wb") as source_file:
                source_file.write(b"audio")

            create_flac_file(source_path, destination_path)

        self.assertEqual(run_mock.call_args.args[0][0], "/custom/ffmpeg")

    @patch("musorg.filesystem.media.shutil.which", return_value=None)
    def test_create_flac_file_raises_when_ffmpeg_is_unavailable(self, _which_mock):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = f"{temp_dir}/source.mp3"
            destination_path = f"{temp_dir}/output.flac"
            with open(source_path, "wb") as source_file:
                source_file.write(b"audio")

            with self.assertRaisesRegex(FileNotFoundError, "MUSORG_FFMPEG_BIN"):
                create_flac_file(source_path, destination_path)


class OutputFormatNamingTests(unittest.TestCase):
    def _track(self, **overrides):
        track = {
            "path": "/tmp/source.flac",
            "albumartist": "The Limiñanas",
            "artist": "The Limiñanas",
            "album": "Down Underground",
            "title": "The Darkside",
            "date": "10-04-2015",
            "release_date_iso": "2015-04-10",
            "tracknumber": 1,
            "discnumber": 1,
            "genre": "Rock",
        }
        track.update(overrides)
        return track

    def test_default_preset_formats_artist_year_album_with_dot_separator(self):
        destination = format_output_destination(self._track(), "/output", default_output_format_settings())

        self.assertEqual(destination.album_root, "/output/The Limiñanas/2015 - Down Underground")
        self.assertEqual(destination.file_path, "/output/The Limiñanas/2015 - Down Underground/01. The Darkside.flac")

    def test_genre_artist_album_preset_uses_nested_folder_segments(self):
        settings = {
            **default_output_format_settings(),
            "album_folder_preset": "genre_artist_album",
            "separator_style": "space",
            "file_naming": "title_only",
        }

        destination = format_output_destination(self._track(), "/output", settings)

        self.assertEqual(destination.album_root, "/output/Rock/The Limiñanas/Down Underground")
        self.assertEqual(destination.file_path, "/output/Rock/The Limiñanas/Down Underground/The Darkside.flac")

    def test_keep_together_creates_disc_subfolders_for_multi_disc_releases(self):
        destination = format_output_destination(
            self._track(tracknumber=2, discnumber=2),
            "/output",
            default_output_format_settings(),
        )

        self.assertEqual(destination.album_root, "/output/The Limiñanas/2015 - Down Underground")
        self.assertEqual(destination.file_path, "/output/The Limiñanas/2015 - Down Underground/CD2/02. The Darkside.flac")

    def test_flatten_writes_tracks_directly_to_album_root(self):
        settings = {
            **default_output_format_settings(),
            "disc_handling": "flatten",
        }

        destination = format_output_destination(
            self._track(tracknumber=2, discnumber=2),
            "/output",
            settings,
        )

        self.assertEqual(destination.file_path, "/output/The Limiñanas/2015 - Down Underground/02. The Darkside.flac")

    def test_prefix_disc_writes_disc_prefixed_track_numbers(self):
        settings = {
            **default_output_format_settings(),
            "disc_handling": "prefix_disc",
            "separator_style": "hyphen",
        }

        destination = format_output_destination(
            self._track(tracknumber=2, discnumber=2),
            "/output",
            settings,
        )

        self.assertEqual(destination.file_path, "/output/The Limiñanas/2015 - Down Underground/2-02 - The Darkside.flac")

    def test_cross_platform_safe_compatibility_normalizes_output_paths(self):
        track = self._track(albumartist="Björk", artist="Björk", album="Sigur Rós / AC/DC", title="Françoise Hardy")
        track["_filename_compatibility"] = "cross_platform_safe"

        destination = format_output_destination(track, "/output", default_output_format_settings())

        self.assertEqual(destination.album_root, "/output/Bjork/2015 - Sigur Ros _ AC_DC")
        self.assertEqual(destination.file_path, "/output/Bjork/2015 - Sigur Ros _ AC_DC/01. Francoise Hardy.flac")

    def test_preview_tree_marks_flattened_duplicate_track_numbers_as_ambiguous(self):
        settings = {
            **default_output_format_settings(),
            "disc_handling": "flatten",
        }

        preview = build_output_preview_tree(
            [
                self._track(tracknumber=1, discnumber=1, title="The Darkside"),
                self._track(tracknumber=1, discnumber=2, title="Je me souviens comme si j’y étais"),
            ],
            settings,
            has_artwork=True,
        )

        self.assertTrue(preview["warnings"])
        self.assertIn("ambiguous", preview["warnings"][0]["id"])
        self.assertTrue(any(node["label"] == "Cover.jpg" for node in preview["tree"]))

    def test_preview_tree_uses_cross_platform_safe_names(self):
        preview = build_output_preview_tree(
            [self._track(albumartist="Björk", artist="Björk", album="AC/DC", title="Sigur Rós")],
            default_output_format_settings(),
            has_artwork=False,
        )

        safe_preview = build_output_preview_tree(
            [dict(self._track(albumartist="Björk", artist="Björk", album="AC/DC", title="Sigur Rós"), _filename_compatibility="cross_platform_safe")],
            default_output_format_settings(),
            has_artwork=False,
        )

        self.assertIn("Björk", preview["albumRootLabel"])
        self.assertIn("Bjork", safe_preview["albumRootLabel"])
        self.assertTrue(any(node["label"] == "01. Sigur Ros.flac" for node in safe_preview["tree"]))


class DryRunTests(unittest.TestCase):
    @patch("musorg.filesystem.organizer.log")
    @patch("musorg.filesystem.organizer.write_metadata_tags")
    @patch("musorg.filesystem.organizer.create_flac_file")
    def test_copy_track_to_destination_dry_run_does_not_modify_files(
        self,
        create_flac_file_mock,
        write_metadata_tags_mock,
        log_mock,
    ):
        track = {
            "path": "/tmp/source.mp3",
            "artist": "Artist",
            "albumartist": "Artist",
            "album": "Album",
            "title": "Title",
            "date": "10-04-2026",
            "release_date_iso": "2026-04-10",
            "tracknumber": 1,
            "discnumber": 1,
            "singleoriginaltracknumber": 1,
            "cover": "https://example.com/cover.jpg",
        }

        copy_track_to_destination(track, "/tmp/output.flac", dry_run=True)

        create_flac_file_mock.assert_not_called()
        write_metadata_tags_mock.assert_not_called()
        self.assertTrue(any("Would transcode" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("Would write tags" in call.args[1] for call in log_mock.call_args_list))
        self.assertTrue(any("Would download cover art" in call.args[1] for call in log_mock.call_args_list))


class DuplicateArchiveRoutingTests(unittest.TestCase):
    def test_archive_mode_routes_clear_weaker_duplicate_to_archive(self):
        track = {"path": "/library/Artist/Album/01.flac"}
        registry = ReleaseIntelligenceRegistry(
            summaries_by_path={
                "/library/Artist/Album": {
                    "relationshipStatus": "exact_duplicate",
                    "bestVersion": False,
                    "duplicateConfidence": 91,
                    "qualityRank": 2,
                },
            },
            related_payload_by_path={},
        )

        output_root = _album_output_root(
            "/output",
            track,
            release_registry=registry,
            duplicate_handling="move_duplicates_to_archive",
        )

        self.assertEqual(output_root, "/output/Archive")

    def test_archive_mode_keeps_best_version_in_main_output(self):
        track = {"path": "/library/Artist/Album/01.flac"}
        registry = ReleaseIntelligenceRegistry(
            summaries_by_path={
                "/library/Artist/Album": {
                    "relationshipStatus": "exact_duplicate",
                    "bestVersion": True,
                    "duplicateConfidence": 91,
                    "qualityRank": 1,
                },
            },
            related_payload_by_path={},
        )

        output_root = _album_output_root(
            "/output",
            track,
            release_registry=registry,
            duplicate_handling="move_duplicates_to_archive",
        )

        self.assertEqual(output_root, "/output")

    def test_context_stores_dry_run_flag(self):
        context = Context("/tmp/music", dry_run=True)
        self.assertTrue(context.dry_run)

    @patch("musorg.cli.main.run_pipeline")
    def test_cli_passes_dry_run_to_core_pipeline(self, run_pipeline_mock):
        runner = CliRunner()
        run_pipeline_mock.return_value = RunResult(
            albums_processed=0,
            tracks_processed=0,
            output_path=None,
            stats={},
        )

        result = runner.invoke(run, ["/tmp/music", "--dry-run"])

        self.assertEqual(result.exit_code, 0)
        run_pipeline_mock.assert_called_once_with("/tmp/music", apply=False)


class CoverSidecarTests(unittest.TestCase):
    @patch("musorg.filesystem.organizer.copy_track_to_destination")
    @patch("musorg.filesystem.organizer.resolve_cover_sidecar_bytes", return_value=b"cover-bytes")
    def test_organize_track_writes_cover_jpg_when_enabled(
        self,
        _resolve_cover_sidecar_bytes_mock,
        copy_track_to_destination_mock,
    ):
        track = {
            "path": "/tmp/source.flac",
            "artist": "Artist",
            "albumartist": "Artist",
            "album": "Album",
            "title": "Title",
            "date": "10-04-2026",
            "release_date_iso": "2026-04-10",
            "tracknumber": 1,
            "discnumber": 1,
            "_output_format_settings": default_output_format_settings(),
            "_metadata_preservation_settings": {
                **default_metadata_preservation_settings(),
                "artwork": {
                    "embedArtwork": True,
                    "saveCoverJpg": True,
                    "replaceLowQualityArtwork": True,
                    "preserveHigherQualityArtwork": True,
                },
            },
        }

        with tempfile.TemporaryDirectory() as root_output:
            destination = organize_track(track, root_output)

            self.assertIsNotNone(destination)
            self.assertTrue(copy_track_to_destination_mock.called)
            self.assertTrue(os.path.exists(os.path.join(track["_organized_album_root"], "Cover.jpg")))


class RollbackTests(unittest.TestCase):
    def test_cleanup_stale_single_track_moves_file_to_backup_and_writes_manifest(self):
        track = {
            "path": "/tmp/release.flac",
            "albumartist": "Artist",
            "artist": "Artist",
            "album": SINGLES_ALBUM_TITLE,
            "title": "Track",
            "date": "01-01-2020",
            "release_date_iso": "2020-01-01",
            "singleoriginaltracknumber": 1,
        }

        with tempfile.TemporaryDirectory() as root_output:
            singles_folder = os.path.join(root_output, "Artist", SINGLES_ALBUM_TITLE)
            os.makedirs(singles_folder, exist_ok=True)
            stale_file = os.path.join(singles_folder, "01. Track.flac")
            with open(stale_file, "wb") as file_handle:
                file_handle.write(b"audio")

            journal = type("Journal", (), {})()
            from musorg.filesystem.rollback import OperationJournal
            journal = OperationJournal(root_output, dry_run=False)

            with (
                patch("musorg.metadata.parser.read_tags", return_value=track),
                patch("musorg.metadata.normalizer.normalize_track", return_value=dict(track, releasetype="single")),
            ):
                cleanup_stale_single_track(track, root_output, dry_run=False, journal=journal)
                journal.finalize()

            self.assertFalse(os.path.exists(stale_file))
            self.assertTrue(os.path.exists(journal.manifest_path))
            with open(journal.manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)

            self.assertEqual(manifest["output_root"], root_output)
            self.assertTrue(any(item["action"] == "backup_file" for item in manifest["operations"]))
            backup_path = next(
                item["details"]["backup_path"]
                for item in manifest["operations"]
                if item["action"] == "backup_file"
            )
            self.assertTrue(os.path.exists(backup_path))


class OrganizeStageTests(unittest.TestCase):
    def test_multi_track_single_tagged_release_goes_to_singles(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        context.tracks = [
            {
                "path": "/tmp/01.flac",
                "albumartist": "Хаски",
                "artist": "Хаски",
                "album": "У",
                "title": "Track 1",
                "date": "01-01-2019",
                "release_date_iso": "2019-01-01",
                "releasetype": "single",
            },
            {
                "path": "/tmp/02.flac",
                "albumartist": "Хаски",
                "artist": "Хаски",
                "album": "У",
                "title": "Track 2",
                "date": "01-01-2019",
                "release_date_iso": "2019-01-01",
                "releasetype": "single",
            },
        ]

        with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
            with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(2, 2)) as organize_single_tracks_mock:
                organize_stage(context)

        organize_track_mock.assert_not_called()
        organize_single_tracks_mock.assert_called_once_with(context.tracks, "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_one_track_single_release_goes_to_singles(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        track = {
            "path": "/tmp/top.flac",
            "albumartist": "Хаски",
            "artist": "Хаски",
            "album": "ТОПЬ",
            "title": "ТОПЬ",
            "date": "01-01-2020",
            "release_date_iso": "2020-01-01",
            "releasetype": "single",
        }
        context.tracks = [track]

        with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
            with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(1, 1)) as organize_single_tracks_mock:
                organize_stage(context)

        organize_track_mock.assert_not_called()
        organize_single_tracks_mock.assert_called_once_with([track], "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_one_track_matching_album_title_goes_to_singles_without_single_tag(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        track = {
            "path": "/tmp/top.flac",
            "albumartist": "Хаски",
            "artist": "Хаски",
            "album": "ТОПЬ",
            "title": "ТОПЬ",
            "date": "01-01-2020",
            "release_date_iso": "2020-01-01",
            "releasetype": "",
        }
        context.tracks = [track]

        with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
            with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(1, 1)) as organize_single_tracks_mock:
                organize_stage(context)

        organize_track_mock.assert_not_called()
        organize_single_tracks_mock.assert_called_once_with([track], "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_partial_multi_track_single_goes_to_singles(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        track = {
            "path": "/tmp/mimozy.flac",
            "albumartist": "monipula",
            "artist": "monipula",
            "album": "Мимозы",
            "title": "Мимозы",
            "date": "13-03-2026",
            "release_date_iso": "2026-03-13",
            "releasetype": "single",
            "release_track_count": 2,
        }
        context.tracks = [track]

        with patch("musorg.core.stages.organize.cleanup_stale_single_track") as cleanup_stale_single_track_mock:
            with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
                with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(1, 1)) as organize_single_tracks_mock:
                    organize_stage(context)

        cleanup_stale_single_track_mock.assert_not_called()
        organize_track_mock.assert_not_called()
        organize_single_tracks_mock.assert_called_once_with([track], "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_large_multi_track_release_tagged_single_stays_in_album_folders(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        context.tracks = [
            {
                "path": f"/tmp/{index:02}.flac",
                "albumartist": "David Bowie",
                "artist": "David Bowie",
                "album": "Scary Monsters (And Super Creeps)",
                "title": f"Track {index}",
                "date": "01-01-2020",
                "release_date_iso": "2020-01-01",
                "releasetype": "single",
                "release_track_count": 12,
            }
            for index in range(1, 13)
        ]

        with patch("musorg.core.stages.organize.cleanup_stale_single_track") as cleanup_stale_single_track_mock:
            with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
                with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)) as organize_single_tracks_mock:
                    organize_stage(context)

        self.assertEqual(cleanup_stale_single_track_mock.call_count, 12)
        self.assertEqual(organize_track_mock.call_count, 12)
        organize_single_tracks_mock.assert_called_once_with([], "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_non_single_tracks_cleanup_stale_singles_before_organizing(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        track = {
            "path": "/tmp/release.flac",
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Release",
            "title": "Track",
            "date": "01-01-2020",
            "release_date_iso": "2020-01-01",
            "releasetype": "album",
        }
        context.tracks = [track]

        with patch("musorg.core.stages.organize.cleanup_existing_album_folders") as cleanup_existing_album_folders_mock:
            with patch("musorg.core.stages.organize.cleanup_stale_single_track") as cleanup_stale_single_track_mock:
                with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
                    with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)) as organize_single_tracks_mock:
                        organize_stage(context)

        cleanup_existing_album_folders_mock.assert_called_once()
        cleanup_stale_single_track_mock.assert_called_once_with(track, "/tmp/music_organized", dry_run=False, journal=ANY)
        organize_track_mock.assert_called_once_with(track, "/tmp/music_organized", dry_run=False, journal=ANY, cleanup_conflicts=False)
        organize_single_tracks_mock.assert_called_once_with([], "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_album_conflict_cleanup_runs_once_per_album_group(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        context.tracks = [
            {
                "path": "/tmp/release-01.flac",
                "albumartist": "Artist",
                "artist": "Artist",
                "album": "Album",
                "title": "Track 1",
                "tracknumber": 1,
                "discnumber": 1,
                "date": "01-01-2020",
                "release_date_iso": "2020-01-01",
                "releasetype": "album",
            },
            {
                "path": "/tmp/release-02.flac",
                "albumartist": "Artist",
                "artist": "Artist",
                "album": "Album",
                "title": "Track 2",
                "tracknumber": 2,
                "discnumber": 1,
                "date": "01-01-2020",
                "release_date_iso": "2020-01-01",
                "releasetype": "album",
            },
        ]
        context.albums = {("artist", "album"): context.tracks}

        with patch("musorg.core.stages.organize.cleanup_existing_album_folders") as cleanup_existing_album_folders_mock:
            with patch("musorg.core.stages.organize.cleanup_stale_single_track"):
                with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
                    with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)) as organize_single_tracks_mock:
                        organize_stage(context)

        cleanup_existing_album_folders_mock.assert_called_once()
        self.assertEqual(organize_track_mock.call_count, 2)
        for call in organize_track_mock.call_args_list:
            self.assertEqual(call.kwargs["cleanup_conflicts"], False)
        organize_single_tracks_mock.assert_called_once_with([], "/tmp/music_organized", dry_run=False, journal=ANY)

    def test_album_conflict_cleanup_records_timing_separately(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        context.run_report = RunReport("/tmp/music", dry_run=True)
        track = {
            "path": "/tmp/release.flac",
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "title": "Track",
            "tracknumber": 1,
            "discnumber": 1,
            "date": "01-01-2020",
            "release_date_iso": "2020-01-01",
            "releasetype": "album",
        }
        context.tracks = [track]
        context.albums = {("artist", "album"): context.tracks}

        perf_counter_values = iter([1.0, 1.2])
        with (
            patch("musorg.core.run_report.perf_counter", side_effect=lambda: next(perf_counter_values)),
            patch("musorg.core.stages.organize.cleanup_existing_album_folders"),
            patch("musorg.core.stages.organize.cleanup_stale_single_track"),
            patch("musorg.core.stages.organize.organize_track", return_value="/tmp/music_organized/Artist/2020 - Album/01. Track.flac"),
            patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)),
        ):
            organize_stage(context)

        metrics = context.run_report.profiling_summary()["metrics"]
        self.assertAlmostEqual(metrics["album_conflict_cleanup"]["total_seconds"], 0.2)
        self.assertEqual(metrics["album_conflict_cleanup"]["count"], 1)

    def test_dry_run_passes_flag_to_organizer_operations(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        context.dry_run = True
        track = {
            "path": "/tmp/release.flac",
            "albumartist": "Artist",
            "artist": "Artist",
            "album": "Album",
            "title": "Track",
            "date": "01-01-2020",
            "release_date_iso": "2020-01-01",
            "releasetype": "album",
        }
        context.tracks = [track]

        with patch("musorg.core.stages.organize.cleanup_existing_album_folders") as cleanup_existing_album_folders_mock:
            with patch("musorg.core.stages.organize.cleanup_stale_single_track") as cleanup_stale_single_track_mock:
                with patch("musorg.core.stages.organize.organize_track", return_value=True) as organize_track_mock:
                    with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)) as organize_single_tracks_mock:
                        organize_stage(context)

        cleanup_existing_album_folders_mock.assert_called_once()
        cleanup_stale_single_track_mock.assert_called_once_with(track, "/tmp/music_organized", dry_run=True, journal=ANY)
        organize_track_mock.assert_called_once_with(track, "/tmp/music_organized", dry_run=True, journal=ANY, cleanup_conflicts=False)
        organize_single_tracks_mock.assert_called_once_with([], "/tmp/music_organized", dry_run=True, journal=ANY)

    def test_logs_album_progress_during_organize(self):
        context = type("Context", (), {})()
        context.root_path = "/tmp/music"
        context.tracks = [
            {
                "path": "/tmp/release.flac",
                "albumartist": "Artist",
                "artist": "Artist",
                "album": "Album",
                "title": "Track",
                "date": "01-01-2020",
                "release_date_iso": "2020-01-01",
                "releasetype": "album",
            }
        ]
        context.albums = {("artist", "album"): context.tracks}

        with patch("musorg.core.stages.organize.log") as log_mock:
            with patch("musorg.core.stages.organize.cleanup_existing_album_folders"):
                with patch("musorg.core.stages.organize.cleanup_stale_single_track"):
                    with patch("musorg.core.stages.organize.organize_track", return_value=True):
                        with patch("musorg.core.stages.organize.organize_single_tracks", return_value=(0, 0)):
                            organize_stage(context)

        self.assertTrue(
            any(
                call.args[0] == "Organize" and "Organizing album 1/1: Artist" in call.args[1]
                for call in log_mock.call_args_list
            )
        )

class CollapseDuplicateLeadingYearTests(unittest.TestCase):
    def test_collapses_repeated_leading_year(self):
        self.assertEqual(collapse_duplicate_leading_year("2024 - 2024 - начало"), "2024 - начало")

    def test_collapses_repeated_year_without_remainder(self):
        self.assertEqual(collapse_duplicate_leading_year("2024 - 2024"), "2024")

    def test_keeps_single_leading_year(self):
        self.assertEqual(collapse_duplicate_leading_year("2024 - начало"), "2024 - начало")

    def test_keeps_year_named_album(self):
        self.assertEqual(collapse_duplicate_leading_year("1984"), "1984")

    def test_keeps_year_in_parentheses(self):
        self.assertEqual(collapse_duplicate_leading_year("1989 (2014)"), "1989 (2014)")

    def test_does_not_collapse_different_years(self):
        self.assertEqual(collapse_duplicate_leading_year("2014 - 2024 - Album"), "2014 - 2024 - Album")

    def test_collapses_with_em_dash_separator(self):
        self.assertEqual(collapse_duplicate_leading_year("2024 — 2024 — начало"), "2024 — начало")


if __name__ == "__main__":
    unittest.main()
