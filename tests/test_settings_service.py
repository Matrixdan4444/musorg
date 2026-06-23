from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from musorg.api.services import settings as settings_service


class SettingsServiceTests(unittest.TestCase):
    def test_fresh_install_requires_onboarding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.get_library_settings_state()

            self.assertFalse(payload.onboardingCompleted)
            self.assertFalse(payload.onboardingDismissed)

    def test_existing_config_without_onboarding_flags_is_treated_as_completed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()
            settings_dir.mkdir()
            settings_path.write_text(
                json.dumps({
                    "library_root": str(library),
                    "output_root": str(output),
                    "language": "en",
                    "output_format": {
                        "album_folder_preset": "artist_album",
                    },
                }),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.get_library_settings_state()

            self.assertTrue(payload.onboardingCompleted)
            self.assertFalse(payload.onboardingDismissed)

    def test_save_library_settings_preserves_onboarding_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                initial = settings_service.save_library_settings(
                    str(library),
                    str(output),
                    onboarding_completed=False,
                    onboarding_dismissed=True,
                )
                reloaded = settings_service.save_library_settings(
                    str(library),
                    str(output),
                    duplicate_handling="move_duplicates_to_archive",
                )

            self.assertFalse(initial.onboardingCompleted)
            self.assertTrue(initial.onboardingDismissed)
            self.assertFalse(reloaded.onboardingCompleted)
            self.assertTrue(reloaded.onboardingDismissed)

    def test_save_library_settings_persists_developer_mode_language_and_appearance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            library.mkdir()
            output.mkdir()
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"

            with (
                patch.dict("os.environ", {
                    "MUSORG_LIBRARY_PATH": "",
                    "MUSORG_SETTINGS_DIR": str(settings_dir),
                    "MUSORG_SETTINGS_PATH": str(settings_path),
                }, clear=False),
            ):
                payload = settings_service.save_library_settings(
                    str(library),
                    str(output),
                    developer_mode=True,
                    language="ru",
                    theme_mode="dark",
                    accent_color="teal",
                )

                self.assertTrue(payload.developerMode)
                self.assertEqual(payload.language, "ru")
                self.assertEqual(payload.themeMode, "dark")
                self.assertEqual(payload.accentColor, "teal")
                self.assertEqual(payload.duplicateHandling, "keep_everything")
                self.assertEqual(payload.filenameCompatibility, "preserve_original")
                self.assertTrue(settings_service.is_developer_mode_enabled())
                self.assertEqual(settings_service.get_language(), "ru")
                self.assertEqual(settings_service.get_theme_mode(), "dark")
                self.assertEqual(settings_service.get_accent_color(), "teal")
                self.assertEqual(payload.outputFormat.albumFolderPreset, "artist_year_album")
                self.assertEqual(payload.outputFormat.discHandling, "keep_together")
                self.assertEqual(payload.outputFormat.fileNaming, "track_title")
                self.assertEqual(payload.outputFormat.separatorStyle, "dot")
                self.assertEqual(payload.outputFormat.customAlbumPattern, ["artist", "folder_break", "year", "album"])
                self.assertTrue(payload.metadataPreservation.core.trackTitle)
                self.assertTrue(payload.metadataPreservation.release.releaseDate)
                self.assertTrue(payload.metadataPreservation.artwork.embedArtwork)
                self.assertFalse(payload.metadataPreservation.artwork.saveCoverJpg)
                self.assertTrue(payload.metadataPreservation.library.replayGain)
                self.assertTrue(payload.metadataPreservation.advancedIds.musicBrainzReleaseId)

    def test_get_library_settings_accepts_new_accent_colors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()
            settings_dir.mkdir()
            settings_path.write_text(
                '{"library_root": "%s", "output_root": "%s", "theme_mode": "dark", "accent_color": "emerald"}'
                % (library, output),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.get_library_settings_state()

            self.assertEqual(payload.themeMode, "dark")
            self.assertEqual(payload.accentColor, "emerald")

    def test_get_library_settings_defaults_developer_mode_to_false_language_to_en_and_appearance_to_dark_violet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            library.mkdir()
            output.mkdir()
            settings_dir = root / ".musorg"
            settings_dir.mkdir()
            settings_path = settings_dir / "settings.json"
            settings_path.write_text(
                '{"library_root": "%s", "output_root": "%s"}' % (library, output),
                encoding="utf-8",
            )

            with (
                patch.dict("os.environ", {
                    "MUSORG_LIBRARY_PATH": "",
                    "MUSORG_SETTINGS_DIR": str(settings_dir),
                    "MUSORG_SETTINGS_PATH": str(settings_path),
                }, clear=False),
            ):
                payload = settings_service.get_library_settings_state()

            self.assertFalse(payload.developerMode)
            self.assertEqual(payload.language, "en")
            self.assertEqual(payload.themeMode, "dark")
            self.assertEqual(payload.accentColor, "violet")
            self.assertEqual(payload.duplicateHandling, "keep_everything")
            self.assertEqual(payload.filenameCompatibility, "preserve_original")
            self.assertEqual(payload.outputFormat.albumFolderPreset, "artist_year_album")
            self.assertEqual(payload.outputFormat.discHandling, "keep_together")
            self.assertEqual(payload.outputFormat.fileNaming, "track_title")
            self.assertEqual(payload.outputFormat.separatorStyle, "dot")
            self.assertEqual(payload.outputFormat.customAlbumPattern, ["artist", "folder_break", "year", "album"])
            self.assertTrue(payload.metadataPreservation.core.trackTitle)
            self.assertFalse(payload.metadataPreservation.artwork.saveCoverJpg)
            self.assertTrue(payload.metadataPreservation.library.replayGain)

    def test_isolated_settings_env_does_not_touch_real_settings_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            isolated_dir = root / "isolated-musorg"
            isolated_path = isolated_dir / "settings.json"
            real_home = root / "home"
            real_settings_path = real_home / ".musorg" / "settings.json"
            library.mkdir()
            output.mkdir()
            real_home.mkdir()

            with patch.dict("os.environ", {
                "HOME": str(real_home),
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(isolated_dir),
                "MUSORG_SETTINGS_PATH": str(isolated_path),
            }, clear=False):
                settings_service.save_library_settings(
                    str(library),
                    str(output),
                    developer_mode=False,
                    language="en",
                    theme_mode="dark",
                    accent_color="violet",
                )

            self.assertTrue(isolated_path.exists())
            self.assertFalse(real_settings_path.exists())

    def test_save_library_settings_persists_output_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.save_library_settings(
                    str(library),
                    str(output),
                    developer_mode=False,
                    language="en",
                    theme_mode="dark",
                    accent_color="blue",
                    duplicate_handling="move_duplicates_to_archive",
                    filename_compatibility="cross_platform_safe",
                    output_format={
                        "album_folder_preset": "genre_artist_album",
                        "disc_handling": "prefix_disc",
                        "file_naming": "track_artist_title",
                        "separator_style": "hyphen",
                        "custom_album_pattern": ["genre", "folder_break", "artist", "folder_break", "album"],
                    },
                )

                self.assertEqual(payload.duplicateHandling, "move_duplicates_to_archive")
                self.assertEqual(payload.themeMode, "dark")
                self.assertEqual(payload.accentColor, "blue")
                self.assertEqual(payload.filenameCompatibility, "cross_platform_safe")
                self.assertEqual(payload.outputFormat.albumFolderPreset, "genre_artist_album")
                self.assertEqual(payload.outputFormat.discHandling, "prefix_disc")
                self.assertEqual(payload.outputFormat.fileNaming, "track_artist_title")
                self.assertEqual(payload.outputFormat.separatorStyle, "hyphen")
                self.assertEqual(payload.outputFormat.customAlbumPattern, ["genre", "folder_break", "artist", "folder_break", "album"])

                reloaded = settings_service.get_library_settings_state()
                self.assertEqual(reloaded.duplicateHandling, "move_duplicates_to_archive")
                self.assertEqual(reloaded.themeMode, "dark")
                self.assertEqual(reloaded.accentColor, "blue")
                self.assertEqual(reloaded.filenameCompatibility, "cross_platform_safe")
                self.assertEqual(reloaded.outputFormat.albumFolderPreset, "genre_artist_album")
                self.assertEqual(reloaded.outputFormat.discHandling, "prefix_disc")
                self.assertEqual(reloaded.outputFormat.fileNaming, "track_artist_title")
                self.assertEqual(reloaded.outputFormat.separatorStyle, "hyphen")
                self.assertEqual(reloaded.outputFormat.customAlbumPattern, ["genre", "folder_break", "artist", "folder_break", "album"])

    def test_save_library_settings_persists_metadata_preservation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.save_library_settings(
                    str(library),
                    str(output),
                    metadata_preservation={
                        "core": {
                            "trackTitle": True,
                            "trackArtist": False,
                            "albumTitle": True,
                            "albumArtist": True,
                            "trackNumber": True,
                            "discNumber": True,
                            "discTotal": False,
                        },
                        "release": {
                            "releaseDate": True,
                            "genre": False,
                            "releaseType": True,
                            "explicit": False,
                            "compilation": True,
                        },
                        "artwork": {
                            "embedArtwork": True,
                            "saveCoverJpg": True,
                            "replaceLowQualityArtwork": False,
                            "preserveHigherQualityArtwork": True,
                        },
                        "library": {
                            "replayGain": False,
                            "singleOriginalTrackNumber": True,
                        },
                        "advancedIds": {
                            "musicBrainzReleaseId": False,
                            "musicBrainzTrackId": True,
                        },
                    },
                )

                self.assertFalse(payload.metadataPreservation.core.trackArtist)
                self.assertFalse(payload.metadataPreservation.core.discTotal)
                self.assertFalse(payload.metadataPreservation.release.genre)
                self.assertTrue(payload.metadataPreservation.artwork.saveCoverJpg)
                self.assertFalse(payload.metadataPreservation.library.replayGain)
                self.assertFalse(payload.metadataPreservation.advancedIds.musicBrainzReleaseId)

                reloaded = settings_service.get_library_settings_state()
                self.assertFalse(reloaded.metadataPreservation.core.trackArtist)
                self.assertTrue(reloaded.metadataPreservation.artwork.saveCoverJpg)
                self.assertFalse(reloaded.metadataPreservation.library.replayGain)

    def test_get_library_settings_normalizes_invalid_appearance_to_dark_violet(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_dir.mkdir()
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()
            settings_path.write_text(
                '{"library_root": "%s", "output_root": "%s", "theme_mode": "midnight", "accent_color": "sunset"}' % (library, output),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.get_library_settings_state()

            self.assertEqual(payload.themeMode, "dark")
            self.assertEqual(payload.accentColor, "violet")

    def test_get_library_settings_normalizes_legacy_cyan_accent_to_sky(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            settings_dir = root / ".musorg"
            settings_dir.mkdir()
            settings_path = settings_dir / "settings.json"
            library.mkdir()
            output.mkdir()
            settings_path.write_text(
                '{"library_root": "%s", "output_root": "%s", "theme_mode": "dark", "accent_color": "cyan"}' % (library, output),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {
                "MUSORG_LIBRARY_PATH": "",
                "MUSORG_SETTINGS_DIR": str(settings_dir),
                "MUSORG_SETTINGS_PATH": str(settings_path),
            }, clear=False):
                payload = settings_service.get_library_settings_state()

            self.assertEqual(payload.themeMode, "dark")
            self.assertEqual(payload.accentColor, "sky")

    def test_get_library_settings_migrates_legacy_theme_values(self):
        cases = [
            ("dark", "dark", "violet"),
            ("light", "light", "violet"),
            ("dark_teal", "dark", "teal"),
            ("dark_blue", "dark", "blue"),
        ]

        for legacy_theme, expected_mode, expected_accent in cases:
            with self.subTest(legacy_theme=legacy_theme):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    library = root / "library"
                    output = root / "output"
                    settings_dir = root / ".musorg"
                    settings_dir.mkdir()
                    settings_path = settings_dir / "settings.json"
                    library.mkdir()
                    output.mkdir()
                    settings_path.write_text(
                        '{"library_root": "%s", "output_root": "%s", "theme": "%s"}' % (library, output, legacy_theme),
                        encoding="utf-8",
                    )

                    with patch.dict("os.environ", {
                        "MUSORG_LIBRARY_PATH": "",
                        "MUSORG_SETTINGS_DIR": str(settings_dir),
                        "MUSORG_SETTINGS_PATH": str(settings_path),
                    }, clear=False):
                        payload = settings_service.get_library_settings_state()

                    self.assertEqual(payload.themeMode, expected_mode)
                    self.assertEqual(payload.accentColor, expected_accent)


if __name__ == "__main__":
    unittest.main()
