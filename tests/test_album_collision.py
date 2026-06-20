import os
import tempfile
import unittest

from musorg.filesystem.naming import format_output_destination
from musorg.filesystem.organizer import (
    claim_album_root,
    cleanup_existing_album_folders,
    reset_session_state,
)


class ClaimAlbumRootTests(unittest.TestCase):
    def setUp(self):
        reset_session_state()

    def tearDown(self):
        reset_session_state()

    def test_same_group_keeps_folder(self):
        root = "/out/Massive Attack/Mezzanine"
        first = claim_album_root(root, ("srcA", "mezzanine"))
        again = claim_album_root(root, ("srcA", "mezzanine"))
        self.assertEqual(first, again)

    def test_distinct_groups_get_separate_folders(self):
        root = "/out/Massive Attack/Mezzanine"
        a = claim_album_root(root, ("srcA", "mezzanine"))
        b = claim_album_root(root, ("srcB", "mezzanine"))
        c = claim_album_root(root, ("srcC", "mezzanine"))
        self.assertEqual(a, "/out/Massive Attack/Mezzanine")
        self.assertEqual(b, "/out/Massive Attack/Mezzanine (2)")
        self.assertEqual(c, "/out/Massive Attack/Mezzanine (3)")

    def test_reset_clears_registry(self):
        root = "/out/X/Album"
        claim_album_root(root, ("g1", "album"))
        reset_session_state()
        # After reset the folder is free again for a different group.
        self.assertEqual(claim_album_root(root, ("g2", "album")), root)

    def test_cleanup_does_not_delete_a_sibling_claimed_album(self):
        with tempfile.TemporaryDirectory() as out:
            artist = os.path.join(out, "Massive Attack")
            regular = os.path.join(artist, "1998 - Mezzanine")
            os.makedirs(regular)
            track_file = os.path.join(regular, "01. Angel.flac")
            open(track_file, "wb").close()

            # Edition 1 claims the regular folder; edition 2 (same album title)
            # targets a disambiguated folder and runs its conflict cleanup.
            claim_album_root(regular, ("srcA", "mezzanine"))
            target2 = os.path.join(artist, "1998 - Mezzanine (2)")
            claim_album_root(target2, ("srcB", "mezzanine"))

            cleanup_existing_album_folders(out, target2, "Mezzanine", album_aliases=["Mezzanine"])

            # The first edition's folder + file must survive.
            self.assertTrue(os.path.isdir(regular))
            self.assertTrue(os.path.isfile(track_file))

    def test_override_is_honored_by_format_output_destination(self):
        track = {
            "albumartist": "Massive Attack",
            "album": "Mezzanine",
            "title": "Angel",
            "tracknumber": 1,
            "_album_root_override": "/out/Massive Attack/Mezzanine (2)",
        }
        dest = format_output_destination(track, "/out", {})
        self.assertEqual(dest.album_root, "/out/Massive Attack/Mezzanine (2)")
        self.assertTrue(dest.file_path.startswith("/out/Massive Attack/Mezzanine (2)/"))


class BuildAlbumGroupsTests(unittest.TestCase):
    def _track(self, path, disc, number):
        return {
            "albumartist": "Massive Attack",
            "album": "Mezzanine",
            "path": path,
            "discnumber": disc,
            "tracknumber": number,
        }

    def test_distinct_editions_split_into_separate_groups(self):
        from musorg.core.stages.grouping import build_album_groups

        tracks = (
            [self._track("/music/regular/img.flac", "1", n) for n in range(1, 12)]
            + [self._track("/music/japan/img.ape", "1", n) for n in range(1, 13)]
        )
        groups = list(build_album_groups(tracks).values())
        self.assertEqual(len(groups), 2)
        sizes = sorted(len(g) for g in groups)
        self.assertEqual(sizes, [11, 12])

    def test_multi_disc_across_folders_stays_one_group(self):
        from musorg.core.stages.grouping import build_album_groups

        # Disc 1 and Disc 2 in separate folders, no number overlap -> one album.
        tracks = (
            [self._track("/music/album/cd1/img.flac", "1", n) for n in range(1, 6)]
            + [self._track("/music/album/cd2/img.flac", "2", n) for n in range(1, 6)]
        )
        groups = list(build_album_groups(tracks).values())
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 10)

    def test_single_album_one_group(self):
        from musorg.core.stages.grouping import build_album_groups

        tracks = [self._track("/music/album/img.flac", "1", n) for n in range(1, 6)]
        groups = list(build_album_groups(tracks).values())
        self.assertEqual(len(groups), 1)


if __name__ == "__main__":
    unittest.main()
