import os
import tempfile
import unicodedata
import unittest
from unittest.mock import patch

from musorg.core.stages.metadata_read import source_album_group_key
from musorg.filesystem.naming import filesystem_path_key, filesystem_safe_name, normalize_filesystem_path
from musorg.filesystem.organizer import cleanup_existing_album_folders, reset_session_state, unique_destination_path


class UnicodePathTests(unittest.TestCase):
    def test_filesystem_safe_name_normalizes_to_nfc(self):
        decomposed = "Cafe\u0301"

        safe_name = filesystem_safe_name(decomposed)

        self.assertEqual(safe_name, "Café")
        self.assertEqual(unicodedata.normalize("NFC", safe_name), safe_name)

    def test_unique_destination_path_treats_nfc_and_nfd_as_same_path(self):
        with tempfile.TemporaryDirectory() as root_path:
            reset_session_state()
            nfc_path = os.path.join(root_path, "Café.flac")
            nfd_path = os.path.join(root_path, unicodedata.normalize("NFD", "Café.flac"))

            first = unique_destination_path(nfc_path)
            second = unique_destination_path(nfd_path)

            self.assertEqual(first, normalize_filesystem_path(nfc_path))
            self.assertTrue(second.endswith("(2).flac"))

    def test_cleanup_existing_album_folders_skips_equivalent_folder_name_with_different_normalization(self):
        root_output = "/tmp/library"
        artist_path = os.path.join(root_output, "Artist")
        target_folder = os.path.join(artist_path, "2020 - Café")
        listed_folder_name = unicodedata.normalize("NFD", "2020 - Café")
        listed_candidate = os.path.join(artist_path, listed_folder_name)
        reset_session_state()

        class Journal:
            def __init__(self):
                self.operations = []

            def record(self, action, **details):
                self.operations.append((action, details))

        journal = Journal()

        def fake_isdir(path):
            normalized = filesystem_path_key(path)
            if normalized in {
                filesystem_path_key(root_output),
                filesystem_path_key(artist_path),
                filesystem_path_key(listed_candidate),
            }:
                return True
            if normalized == filesystem_path_key(target_folder):
                return False
            return False

        with (
            patch("musorg.filesystem.organizer.os.path.isdir", side_effect=fake_isdir),
            patch("musorg.filesystem.organizer.os.listdir", side_effect=[["Artist"], [listed_folder_name]]),
        ):
            cleanup_existing_album_folders(
                root_output=root_output,
                target_folder=target_folder,
                album="Cafe\u0301",
                dry_run=True,
                journal=journal,
            )

        self.assertEqual(len(journal.operations), 1)
        action, details = journal.operations[0]
        self.assertEqual(action, "preview_remove_directory")
        self.assertEqual(details["path"], normalize_filesystem_path(target_folder))

    def test_source_album_group_key_uses_normalized_source_dir_identity(self):
        nfc_path = os.path.join("/tmp", "Café", "01.flac")
        nfd_path = unicodedata.normalize("NFD", nfc_path)

        left = source_album_group_key({"path": nfc_path, "album": "Album"})
        right = source_album_group_key({"path": nfd_path, "album": "Album"})

        self.assertEqual(left, right)
        self.assertEqual(left[0], filesystem_path_key(os.path.dirname(nfc_path)))


if __name__ == "__main__":
    unittest.main()
