from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from musorg.api.services.batch_edit import _resolve_album_path
from musorg.api.services.library import AlbumRuntimeStateResolution

from musorg.api.schemas.music import (
    BatchEditAlbumDraftSchema,
    BatchEditApplyReleaseRequestSchema,
    BatchEditArtworkStateSchema,
    BatchEditEditorStateSchema,
    BatchEditFindArtworkRequestSchema,
    BatchEditFindReleaseRequestSchema,
    BatchEditTrackSchema,
    LibrarySettingsResponse,
)
from musorg.api.services.batch_edit import (
    _build_editor_state,
    apply_batch_edit_release,
    find_batch_edit_artwork,
    get_batch_edit_album_detail,
    list_batch_edit_albums,
)


class BatchEditServiceTests(unittest.TestCase):
    def test_resolve_album_path_uses_output_for_completed_albums(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir).resolve()
            source = root / "Artist" / "Album"
            output = root / "Artist" / "Album_organized"
            source.mkdir(parents=True)
            output.mkdir(parents=True)
            album_id = base64.urlsafe_b64encode(str(source).encode()).decode().rstrip("=")
            settings_state = LibrarySettingsResponse(
                libraryRoot=str(root),
                outputRoot=str(root),
                developerMode=False,
                language="en",
                isConfigured=True,
                isAvailable=True,
                source="settings",
                pickerAvailable=False,
            )
            resolution = AlbumRuntimeStateResolution(
                processing_state="completed",
                output_path=str(output),
                resolved_folder_path=str(output),
                resolved_mode="output",
            )
            with (
                patch("musorg.api.services.batch_edit.get_library_settings_state", return_value=settings_state),
                patch("musorg.api.services.batch_edit.resolve_album_runtime_state", return_value=resolution),
            ):
                self.assertEqual(_resolve_album_path(album_id), str(output))

    def test_list_batch_edit_albums_resolves_runtime_output_for_status(self):
        settings_state = LibrarySettingsResponse(
            libraryRoot="/music/source",
            outputRoot="/music/output",
            developerMode=False,
            language="en",
            isConfigured=True,
            isAvailable=True,
            source="settings",
            pickerAvailable=False,
        )

        with (
            patch("musorg.api.services.batch_edit.get_library_settings_state", return_value=settings_state),
            patch("musorg.api.services.batch_edit.list_albums_for_root") as list_mock,
        ):
            list_batch_edit_albums()

        list_mock.assert_called_once_with(
            "/music/source",
            include_metadata_intelligence=True,
            resolve_runtime_output=True,
        )

    def test_get_batch_edit_album_detail_resolves_runtime_output(self):
        settings_state = LibrarySettingsResponse(
            libraryRoot="/music/source",
            outputRoot="/music/output",
            developerMode=False,
            language="en",
            isConfigured=True,
            isAvailable=True,
            source="settings",
            pickerAvailable=False,
        )

        detail_payload = type("DetailPayload", (), {"album": None})()

        with (
            patch("musorg.api.services.batch_edit.get_library_settings_state", return_value=settings_state),
            patch("musorg.api.services.batch_edit.get_album_detail_payload_for_root", return_value=detail_payload) as detail_mock,
            patch("musorg.api.services.batch_edit.get_related_releases_payload", return_value=[]),
            patch("musorg.api.services.batch_edit.get_album_actions_payload", return_value=[]),
            patch("musorg.api.services.batch_edit._build_editor_state", return_value={"album": {}, "tracks": [], "artwork": {}}),
            patch("musorg.api.services.batch_edit.BatchEditAlbumDetailResponseSchema"),
        ):
            get_batch_edit_album_detail("album-123")

        detail_mock.assert_called_once_with(
            "album-123",
            "/music/source",
            include_metadata_intelligence=True,
            resolve_runtime_output=True,
        )

    @patch("musorg.api.services.batch_edit.read_tags")
    @patch("musorg.api.services.batch_edit._artwork_state")
    @patch("musorg.api.services.batch_edit._album_track_paths")
    @patch("musorg.api.services.batch_edit._resolve_album_path")
    def test_build_editor_state_uses_track_artist_when_albumartist_is_placeholder(
        self,
        resolve_album_path_mock,
        album_track_paths_mock,
        artwork_state_mock,
        read_tags_mock,
    ):
        track_path = Path("/music/source/Artist/Album/01 - Track.flac")
        resolve_album_path_mock.return_value = str(track_path.parent)
        album_track_paths_mock.return_value = [track_path]
        artwork_state_mock.return_value = {"hasArtwork": False, "coverUrl": "", "source": None}
        read_tags_mock.return_value = {
            "album": "Album",
            "albumartist": "Unknown artist",
            "artist": "Pharaoh & Boulevard Depo",
            "trackartist": "Pharaoh & Boulevard Depo",
            "title": "Track",
            "tracknumber": "1",
            "discnumber": "1",
            "duration_seconds": 120,
            "date": "2016",
            "genre": "Hip-Hop",
            "has_tracknumber_tag": True,
        }

        editor = _build_editor_state("album-123")

        self.assertEqual(editor.album.albumArtist, "Pharaoh & Boulevard Depo")
        self.assertEqual(editor.album.releaseArtist, "Pharaoh & Boulevard Depo")
        self.assertEqual(editor.tracks[0].albumArtist, "Pharaoh & Boulevard Depo")
        self.assertEqual(editor.tracks[0].artist, "Pharaoh & Boulevard Depo")

    @patch("musorg.api.services.batch_edit.cover_art_url")
    @patch("musorg.api.services.batch_edit.get_release_details")
    @patch("musorg.api.services.batch_edit.search_release_group")
    @patch("musorg.api.services.batch_edit.search_album_candidates")
    @patch("musorg.api.services.batch_edit._build_editor_state")
    def test_find_batch_edit_artwork_returns_provider_options_with_resolution_metadata(
        self,
        build_editor_state_mock,
        search_album_candidates_mock,
        search_release_group_mock,
        get_release_details_mock,
        cover_art_url_mock,
    ):
        build_editor_state_mock.return_value = BatchEditEditorStateSchema(
            album=BatchEditAlbumDraftSchema(
                albumTitle="Плакшери",
                albumArtist="Pharaoh",
                releaseArtist="Pharaoh",
            ),
            tracks=[],
            artwork=BatchEditArtworkStateSchema(hasArtwork=True, coverUrl="/albums/1/cover", source="embedded"),
        )
        search_album_candidates_mock.return_value = [
            {
                "id": 77,
                "title": "Плакшери",
                "artist": {"name": "Pharaoh"},
                "cover_xl": "https://cdn.deezer.com/cover-xl.jpg",
            }
        ]
        search_release_group_mock.return_value = [
            {
                "id": "rg-1",
                "title": "Плакшери",
                "artist-credit-phrase": "Pharaoh",
                "release-list": [{"id": "mb-release-1", "title": "Плакшери"}],
            }
        ]
        get_release_details_mock.return_value = {
            "id": "mb-release-1",
            "title": "Плакшери",
            "cover-art-archive": {"front": True},
        }
        cover_art_url_mock.return_value = "https://coverartarchive.org/release/mb-release-1/front-500"

        payload = find_batch_edit_artwork(
            "album-123",
            BatchEditFindArtworkRequestSchema(artist="Pharaoh", album="Плакшери"),
        )

        self.assertEqual(payload.queryArtist, "Pharaoh")
        self.assertEqual(payload.queryAlbum, "Плакшери")
        self.assertEqual(len(payload.options), 2)
        self.assertEqual(payload.options[0].provider, "deezer")
        self.assertEqual(payload.options[0].width, 1000)
        self.assertEqual(payload.options[0].height, 1000)
        self.assertEqual(payload.options[1].provider, "musicbrainz")
        self.assertEqual(payload.options[1].width, 500)
        self.assertEqual(payload.options[1].height, 500)

    @patch("musorg.api.services.batch_edit.write_cover_art_bytes")
    @patch("musorg.api.services.batch_edit.write_metadata_tags")
    @patch("musorg.api.services.batch_edit.format_deezer_tracks")
    @patch("musorg.api.services.batch_edit.deezer_get_album")
    @patch("musorg.api.services.batch_edit._build_editor_state")
    def test_apply_batch_edit_release_returns_preview_without_writing_files(
        self,
        build_editor_state_mock,
        deezer_get_album_mock,
        format_deezer_tracks_mock,
        write_metadata_tags_mock,
        write_cover_art_bytes_mock,
    ):
        build_editor_state_mock.return_value = BatchEditEditorStateSchema(
            album=BatchEditAlbumDraftSchema(
                albumTitle="Original Album",
                albumArtist="Original Artist",
                releaseArtist="Original Artist",
                year="2015",
                genre="Rap",
            ),
            tracks=[
                BatchEditTrackSchema(
                    id="track-1",
                    path="/music/source/Artist/Album/01.flac",
                    index=1,
                    title="Old Track",
                    artist="Original Artist",
                    albumArtist="Original Artist",
                    trackNumber="1",
                    discNumber="1",
                    genre="Rap",
                    comment="",
                    duration="03:30",
                    issues=[],
                )
            ],
            artwork=BatchEditArtworkStateSchema(hasArtwork=True, coverUrl="/albums/1/cover", source="embedded"),
        )
        deezer_get_album_mock.return_value = {
            "id": 10,
            "title": "New Album",
            "artist": {"name": "New Artist"},
            "nb_tracks": 1,
            "record_type": "album",
            "cover_xl": "https://cdn.deezer.com/new-cover-xl.jpg",
        }
        format_deezer_tracks_mock.return_value = [
            {"title": "New Track", "artist": "New Artist", "tracknumber": 1, "discnumber": 1}
        ]

        payload = apply_batch_edit_release(
            "album-123",
            BatchEditApplyReleaseRequestSchema(provider="deezer", providerReleaseId="10"),
        )

        self.assertEqual(payload.album.albumTitle, "New Album")
        self.assertEqual(payload.tracks[0].title, "New Track")
        self.assertEqual(payload.artwork.mode, "fetch_provider")
        self.assertTrue(any(item.id == "cover" for item in payload.diff))
        self.assertTrue(any(item.id == "tracks" for item in payload.diff))
        write_metadata_tags_mock.assert_not_called()
        write_cover_art_bytes_mock.assert_not_called()
