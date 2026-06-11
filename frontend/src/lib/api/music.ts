import { API_BASE_URL, getJson, postJson, putJson } from "@/lib/api/client";
import type {
  AlbumActionsPayload,
  AlbumDetailPayload,
  AlbumMetadataOverride,
  AlbumsPayload,
  BatchEditAlbumDetailPayload,
  BatchEditApplyReleasePayload,
  BatchEditArtworkDraft,
  BatchEditFindArtworkPayload,
  BatchEditBulkUpdatePayload,
  BatchEditBulkUpdateRequestPayload,
  BatchEditFindReleasePayload,
  BatchEditSavePayload,
  BatchEditSaveRequestPayload,
  BatchEditTrackRow,
  ClearCachePayload,
  CleanLibraryRequestPayload,
  CleanLibraryPayload,
  HealthPayload,
  LibraryPickerPayload,
  LibrarySettingsPayload,
  LogsPayload,
  ReleaseComparisonPayload,
  TracksPayload,
  UpdateLibrarySettingsPayload,
} from "@/types/music";


export function getHealth() {
  return getJson<HealthPayload>("/health");
}


export function getAlbums() {
  return getJson<AlbumsPayload>("/albums");
}


export function getAlbumDetail(albumId: string) {
  return getJson<AlbumDetailPayload>(`/albums/${albumId}`);
}


export function getAlbumTracks(albumId: string) {
  return getJson<TracksPayload>(`/albums/${albumId}/tracks`);
}


export function getAlbumRelatedReleases(albumId: string) {
  return getJson<ReleaseComparisonPayload>(`/albums/${albumId}/related-releases`);
}


export function getAlbumActions(albumId: string) {
  return getJson<AlbumActionsPayload>(`/albums/${albumId}/actions`);
}


export function getRunAlbums(runId: string) {
  return getJson<AlbumsPayload>(`/runs/${runId}/albums`);
}


export function getRunAlbumDetail(runId: string, albumId: string) {
  return getJson<AlbumDetailPayload>(`/runs/${runId}/albums/${albumId}`);
}


export function getRunAlbumTracks(runId: string, albumId: string) {
  return getJson<TracksPayload>(`/runs/${runId}/albums/${albumId}/tracks`);
}


export function getLogs() {
  return getJson<LogsPayload>("/logs");
}


export function logsWebSocketUrl(runId?: string | null, lastEventId?: string | null) {
  const base = new URL(API_BASE_URL);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${base.host}/ws/logs`);
  if (runId) {
    url.searchParams.set("runId", runId);
  }
  if (lastEventId) {
    url.searchParams.set("lastEventId", lastEventId);
  }
  return url.toString();
}


export function getLibrarySettings() {
  return getJson<LibrarySettingsPayload>("/settings/library");
}


export function setLibrarySettings(payload: UpdateLibrarySettingsPayload) {
  return postJson<LibrarySettingsPayload, UpdateLibrarySettingsPayload>("/settings/library", payload);
}


export function pickLibrarySettings() {
  return postJson<LibraryPickerPayload, undefined>("/settings/library/pick");
}


export function pickOutputSettings() {
  return postJson<LibraryPickerPayload, undefined>("/settings/output/pick");
}


export function clearSettingsCache() {
  return postJson<ClearCachePayload, undefined>("/settings/cache/clear");
}


export function cleanLibrary(overrides: AlbumMetadataOverride[] = []) {
  const payload: CleanLibraryRequestPayload = { overrides };
  return postJson<CleanLibraryPayload, CleanLibraryRequestPayload>("/clean", payload);
}


export function getBatchEditAlbums() {
  return getJson<AlbumsPayload>("/batch-edit/albums");
}


export function getBatchEditAlbumDetail(albumId: string) {
  return getJson<BatchEditAlbumDetailPayload>(`/batch-edit/albums/${albumId}`);
}


export function saveBatchEditAlbum(albumId: string, payload: BatchEditSaveRequestPayload) {
  return putJson<BatchEditSavePayload, BatchEditSaveRequestPayload>(`/batch-edit/albums/${albumId}`, payload);
}


export function saveBatchEditTracks(albumId: string, tracks: BatchEditTrackRow[]) {
  return putJson<BatchEditSavePayload, BatchEditTrackRow[]>(`/batch-edit/albums/${albumId}/tracks`, tracks);
}


export function saveBatchEditArtwork(albumId: string, payload: BatchEditArtworkDraft) {
  return postJson<BatchEditSavePayload, BatchEditArtworkDraft>(`/batch-edit/albums/${albumId}/artwork`, payload);
}


export function findBatchEditRelease(albumId: string, payload: { artist?: string; album?: string }) {
  return postJson<BatchEditFindReleasePayload, { artist?: string; album?: string }>(`/batch-edit/albums/${albumId}/find-release`, payload);
}


export function findBatchEditArtwork(albumId: string, payload: { artist?: string; album?: string }) {
  return postJson<BatchEditFindArtworkPayload, { artist?: string; album?: string }>(`/batch-edit/albums/${albumId}/find-artwork`, payload);
}


export function applyBatchEditRelease(albumId: string, payload: { provider: "deezer" | "musicbrainz"; providerReleaseId: string }) {
  return postJson<BatchEditApplyReleasePayload, { provider: "deezer" | "musicbrainz"; providerReleaseId: string }>(`/batch-edit/albums/${albumId}/apply-release`, payload);
}


export function bulkUpdateBatchEditAlbums(payload: BatchEditBulkUpdateRequestPayload) {
  return postJson<BatchEditBulkUpdatePayload, BatchEditBulkUpdateRequestPayload>("/batch-edit/bulk-update", payload);
}
