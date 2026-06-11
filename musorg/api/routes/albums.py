from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import Response

from musorg.api.schemas.music import AlbumActionsResponseSchema, AlbumDetailResponse, AlbumsResponse, ReleaseComparisonResponseSchema, TracksResponse
from musorg.api.services.library import (
    get_album_actions_payload,
    get_album_cover_response,
    get_album_cover_response_for_root,
    get_album_detail_payload,
    get_album_detail_payload_for_root,
    get_related_releases_payload,
    get_album_tracks_payload,
    get_album_tracks_payload_for_root,
    list_albums,
    list_albums_for_root,
)
from musorg.api.services.run_outputs import get_run_output


router = APIRouter(tags=["albums"])


@router.get("/albums", response_model=AlbumsResponse)
def albums() -> AlbumsResponse:
    return list_albums()


@router.get("/albums/{album_id}", response_model=AlbumDetailResponse)
def album_detail(album_id: str) -> AlbumDetailResponse:
    return get_album_detail_payload(album_id)


@router.get("/albums/{album_id}/cover", response_class=Response)
def album_cover(album_id: str) -> Response:
    return get_album_cover_response(album_id)


@router.get("/albums/{album_id}/tracks", response_model=TracksResponse)
def album_tracks(album_id: str) -> TracksResponse:
    return get_album_tracks_payload(album_id)


@router.get("/albums/{album_id}/related-releases", response_model=ReleaseComparisonResponseSchema)
def album_related_releases(album_id: str) -> ReleaseComparisonResponseSchema:
    return get_related_releases_payload(album_id)


@router.get("/albums/{album_id}/actions", response_model=AlbumActionsResponseSchema)
def album_actions(album_id: str) -> AlbumActionsResponseSchema:
    return get_album_actions_payload(album_id)


@router.get("/runs/{run_id}/albums", response_model=AlbumsResponse)
def run_albums(run_id: str) -> AlbumsResponse:
    output = get_run_output(run_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Run output not found")
    return list_albums_for_root(
        output.output_root,
        cover_url_builder=lambda album_id, _issues: f"/runs/{run_id}/albums/{album_id}/cover",
        include_metadata_intelligence=True,
    )


@router.get("/runs/{run_id}/albums/{album_id}", response_model=AlbumDetailResponse)
def run_album_detail(run_id: str, album_id: str) -> AlbumDetailResponse:
    output = get_run_output(run_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Run output not found")
    return get_album_detail_payload_for_root(
        album_id,
        output.output_root,
        cover_url_builder=lambda resolved_album_id, _issues: f"/runs/{run_id}/albums/{resolved_album_id}/cover",
        include_metadata_intelligence=True,
    )


@router.get("/runs/{run_id}/albums/{album_id}/cover", response_class=Response)
def run_album_cover(run_id: str, album_id: str) -> Response:
    output = get_run_output(run_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Run output not found")
    return get_album_cover_response_for_root(album_id, output.output_root)


@router.get("/runs/{run_id}/albums/{album_id}/tracks", response_model=TracksResponse)
def run_album_tracks(run_id: str, album_id: str) -> TracksResponse:
    output = get_run_output(run_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Run output not found")
    return get_album_tracks_payload_for_root(album_id, output.output_root)
