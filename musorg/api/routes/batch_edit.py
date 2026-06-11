from __future__ import annotations

from fastapi import APIRouter

from musorg.api.schemas.music import (
    AlbumsResponse,
    BatchEditAlbumDetailResponseSchema,
    BatchEditApplyReleaseRequestSchema,
    BatchEditApplyReleaseResponseSchema,
    BatchEditArtworkDraftSchema,
    BatchEditFindArtworkRequestSchema,
    BatchEditFindArtworkResponseSchema,
    BatchEditBulkUpdateRequestSchema,
    BatchEditBulkUpdateResponseSchema,
    BatchEditFindReleaseRequestSchema,
    BatchEditFindReleaseResponseSchema,
    BatchEditSaveRequestSchema,
    BatchEditSaveResponseSchema,
    BatchEditTrackSchema,
)
from musorg.api.services.batch_edit import (
    apply_batch_edit_release,
    bulk_update_batch_edit_albums,
    find_batch_edit_artwork,
    find_batch_edit_release,
    get_batch_edit_album_detail,
    list_batch_edit_albums,
    save_batch_edit_album,
    save_batch_edit_artwork,
    save_batch_edit_tracks,
)


router = APIRouter(tags=["batch-edit"])


@router.get("/batch-edit/albums", response_model=AlbumsResponse)
def batch_edit_albums() -> AlbumsResponse:
    return list_batch_edit_albums()


@router.get("/batch-edit/albums/{album_id}", response_model=BatchEditAlbumDetailResponseSchema)
def batch_edit_album_detail(album_id: str) -> BatchEditAlbumDetailResponseSchema:
    return get_batch_edit_album_detail(album_id)


@router.put("/batch-edit/albums/{album_id}", response_model=BatchEditSaveResponseSchema)
def batch_edit_album_save(album_id: str, request: BatchEditSaveRequestSchema) -> BatchEditSaveResponseSchema:
    return save_batch_edit_album(album_id, request)


@router.put("/batch-edit/albums/{album_id}/tracks", response_model=BatchEditSaveResponseSchema)
def batch_edit_tracks_save(album_id: str, tracks: list[BatchEditTrackSchema]) -> BatchEditSaveResponseSchema:
    return save_batch_edit_tracks(album_id, tracks)


@router.post("/batch-edit/albums/{album_id}/artwork", response_model=BatchEditSaveResponseSchema)
def batch_edit_artwork_save(album_id: str, artwork: BatchEditArtworkDraftSchema) -> BatchEditSaveResponseSchema:
    return save_batch_edit_artwork(album_id, artwork)


@router.post("/batch-edit/albums/{album_id}/find-release", response_model=BatchEditFindReleaseResponseSchema)
def batch_edit_find_release(album_id: str, request: BatchEditFindReleaseRequestSchema) -> BatchEditFindReleaseResponseSchema:
    return find_batch_edit_release(album_id, request)


@router.post("/batch-edit/albums/{album_id}/find-artwork", response_model=BatchEditFindArtworkResponseSchema)
def batch_edit_find_artwork(album_id: str, request: BatchEditFindArtworkRequestSchema) -> BatchEditFindArtworkResponseSchema:
    return find_batch_edit_artwork(album_id, request)


@router.post("/batch-edit/albums/{album_id}/apply-release", response_model=BatchEditApplyReleaseResponseSchema)
def batch_edit_apply_release(album_id: str, request: BatchEditApplyReleaseRequestSchema) -> BatchEditApplyReleaseResponseSchema:
    return apply_batch_edit_release(album_id, request)


@router.post("/batch-edit/bulk-update", response_model=BatchEditBulkUpdateResponseSchema)
def batch_edit_bulk_update(request: BatchEditBulkUpdateRequestSchema) -> BatchEditBulkUpdateResponseSchema:
    return bulk_update_batch_edit_albums(request)
