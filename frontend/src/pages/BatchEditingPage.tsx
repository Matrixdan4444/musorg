import { ChevronDown, ChevronRight, ImagePlus, Search, Upload, Wand2, X } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, ReactNode } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { ModalPortal } from "@/components/ModalPortal";
import { Panel } from "@/components/Panel";
import { CoverImage } from "@/components/music/CoverImage";
import { IssueBadge } from "@/components/music/IssueBadge";
import { useBatchEditAlbumDetail } from "@/hooks/useBatchEditAlbumDetail";
import { useBatchEditAlbums } from "@/hooks/useBatchEditAlbums";
import { useLibrarySettings } from "@/hooks/useLibrarySettings";
import { useI18n } from "@/i18n/useI18n";
import {
  applyBatchEditRelease,
  bulkUpdateBatchEditAlbums,
  findBatchEditArtwork,
  findBatchEditRelease,
  saveBatchEditAlbum,
} from "@/lib/api/music";
import { cn } from "@/lib/cn";
import type { AppPage } from "@/types/layout";
import type {
  BatchEditAlbumDraft,
  BatchEditAlbumDetailPayload,
  BatchEditApplyReleasePayload,
  BatchEditArtworkDraft,
  BatchEditArtworkOption,
  BatchEditCandidate,
  BatchEditTrackRow,
  MetadataDiffField,
} from "@/types/music";


interface BatchEditingPageProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
}

const emptyArtworkDraft: BatchEditArtworkDraft = { mode: "keep" };
const emptyBulkDraft = {
  albumArtist: "",
  year: "",
  genre: "",
  releaseType: "",
  comment: "",
};
const albumFieldOrder: Array<keyof BatchEditAlbumDraft> = [
  "albumTitle",
  "albumArtist",
  "releaseArtist",
  "year",
  "genre",
  "releaseType",
  "label",
  "catalogNumber",
  "copyright",
  "comment",
];

export function BatchEditingPage({ activePage, onNavigate }: BatchEditingPageProps) {
  const { t } = useI18n();
  const batchEditingActive = activePage === "batch-edit";
  const librarySettings = useLibrarySettings();
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedAlbumIds, setSelectedAlbumIds] = useState<Set<string>>(new Set());
  const [albumDraft, setAlbumDraft] = useState<BatchEditAlbumDraft | null>(null);
  const [trackDraftsById, setTrackDraftsById] = useState<Record<string, BatchEditTrackRow>>({});
  const [artworkDraft, setArtworkDraft] = useState<BatchEditArtworkDraft>(emptyArtworkDraft);
  const [releaseReplacementDraft, setReleaseReplacementDraft] = useState<BatchEditApplyReleasePayload | null>(null);
  const [pendingReleasePreview, setPendingReleasePreview] = useState<BatchEditApplyReleasePayload | null>(null);
  const [saving, setSaving] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [releaseDialogOpen, setReleaseDialogOpen] = useState(false);
  const [artworkDialogOpen, setArtworkDialogOpen] = useState(false);
  const [releaseQueryArtist, setReleaseQueryArtist] = useState("");
  const [releaseQueryAlbum, setReleaseQueryAlbum] = useState("");
  const [releaseCandidates, setReleaseCandidates] = useState<BatchEditCandidate[]>([]);
  const [findingRelease, setFindingRelease] = useState(false);
  const [previewingReleaseId, setPreviewingReleaseId] = useState<string | null>(null);
  const [artworkOptions, setArtworkOptions] = useState<BatchEditArtworkOption[]>([]);
  const [findingArtwork, setFindingArtwork] = useState(false);
  const [artworkTab, setArtworkTab] = useState<"provider" | "local">("provider");
  const [draggingArtwork, setDraggingArtwork] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkDraft, setBulkDraft] = useState(emptyBulkDraft);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [expandedTrackIds, setExpandedTrackIds] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const deferredSearch = useDeferredValue(search);
  const albumsQuery = useBatchEditAlbums(refreshKey, batchEditingActive);
  const detailQuery = useBatchEditAlbumDetail(selectedAlbumId, refreshKey, batchEditingActive);
  const albums = albumsQuery.data?.albums ?? [];
  const selectedDetail = detailQuery.data?.album.id === selectedAlbumId ? detailQuery.data : null;

  useEffect(() => {
    if (!selectedAlbumId && albums.length > 0) {
      setSelectedAlbumId(albums[0]?.id ?? null);
      return;
    }
    if (selectedAlbumId && albums.length > 0 && !albums.some((album) => album.id === selectedAlbumId)) {
      setSelectedAlbumId(albums[0]?.id ?? null);
    }
  }, [albums, selectedAlbumId]);

  useEffect(() => {
    if (!selectedDetail || selectedDetail.album.id !== selectedAlbumId) {
      return;
    }
    setAlbumDraft(selectedDetail.editor.album);
    setTrackDraftsById({});
    setArtworkDraft(emptyArtworkDraft);
    setReleaseReplacementDraft(null);
    setPendingReleasePreview(null);
    setArtworkOptions([]);
    setReleaseCandidates([]);
    setReleaseQueryArtist(selectedDetail.editor.album.albumArtist || selectedDetail.editor.album.releaseArtist || "");
    setReleaseQueryAlbum(selectedDetail.editor.album.albumTitle || "");
    setArtworkTab("provider");
    setAdvancedOpen(false);
    setExpandedTrackIds(new Set(selectedDetail.editor.tracks[0]?.id ? [selectedDetail.editor.tracks[0].id] : []));
  }, [selectedAlbumId, selectedDetail?.album.id]);

  const filteredAlbums = useMemo(() => {
    const term = deferredSearch.trim().toLowerCase();
    return albums.filter((album) => {
      if (!term) {
        return true;
      }
      return [album.title, album.artist, album.year].join(" ").toLowerCase().includes(term);
    });
  }, [albums, deferredSearch]);

  const mergedAlbumDraft = albumDraft ?? selectedDetail?.editor.album ?? null;
  const mergedTracks = useMemo(() => {
    const base = selectedDetail?.editor.tracks ?? [];
    return base.map((track) => trackDraftsById[track.id] ?? track);
  }, [selectedDetail?.editor.tracks, trackDraftsById]);

  const dirtyAlbumFields = useMemo(
    () => diffAlbumFields(selectedDetail?.editor.album ?? null, mergedAlbumDraft),
    [mergedAlbumDraft, selectedDetail?.editor.album],
  );
  const dirtyTrackIds = useMemo(
    () => diffTrackIds(selectedDetail?.editor.tracks ?? [], mergedTracks),
    [mergedTracks, selectedDetail?.editor.tracks],
  );
  const artworkDirty = artworkDraft.mode !== "keep";
  const releaseDirty = releaseReplacementDraft !== null;
  const hasUnsavedChanges = Boolean(selectedDetail) && selectedDetail?.album.id === selectedAlbumId && (
    dirtyAlbumFields.size > 0
    || dirtyTrackIds.size > 0
    || artworkDirty
    || releaseDirty
  );

  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      if (!hasUnsavedChanges) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [hasUnsavedChanges]);

  const displayedAlbumTitle = mergedAlbumDraft?.albumTitle || selectedDetail?.album.title || "";
  const displayedAlbumArtist = resolveDisplayArtist(mergedAlbumDraft, selectedDetail) || t("common.unknownArtist");
  const currentCoverUrl = artworkDraft.mode === "remove"
    ? ""
    : artworkDraft.coverUrl || selectedDetail?.editor.artwork.coverUrl || selectedDetail?.album.coverUrl || "";

  async function handleSave() {
    if (!selectedAlbumId || !mergedAlbumDraft) {
      return;
    }
    try {
      setSaving(true);
      setPageError(null);
      await saveBatchEditAlbum(selectedAlbumId, {
        album: mergedAlbumDraft,
        tracks: mergedTracks,
        artwork: artworkDraft,
        releaseReplacement: releaseReplacementDraft,
      });
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : t("batchEditing.errors.save"));
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (!selectedDetail) {
      return;
    }
    setAlbumDraft(selectedDetail.editor.album);
    setTrackDraftsById({});
    setArtworkDraft(emptyArtworkDraft);
    setReleaseReplacementDraft(null);
    setPendingReleasePreview(null);
    setArtworkOptions([]);
  }

  function guardNavigation(next: () => void) {
    if (hasUnsavedChanges && !window.confirm(t("batchEditing.errors.discardConfirm"))) {
      return;
    }
    next();
  }

  function handleSelectAlbum(albumId: string) {
    if (albumId === selectedAlbumId) {
      return;
    }
    guardNavigation(() => {
      // Clear drafts up-front so the new card never briefly diffs against the
      // previous album's draft (which flashed a false "Metadata Modified").
      setAlbumDraft(null);
      setTrackDraftsById({});
      setArtworkDraft(emptyArtworkDraft);
      setReleaseReplacementDraft(null);
      setSelectedAlbumId(albumId);
    });
  }

  function handleNavigate(page: AppPage) {
    guardNavigation(() => onNavigate(page));
  }

  function handleToggleSelection(albumId: string) {
    setSelectedAlbumIds((current) => {
      const next = new Set(current);
      if (next.has(albumId)) {
        next.delete(albumId);
      } else {
        next.add(albumId);
      }
      return next;
    });
  }

  function handleAlbumFieldChange<K extends keyof BatchEditAlbumDraft>(field: K, value: BatchEditAlbumDraft[K]) {
    setAlbumDraft((current) => ({ ...(current ?? selectedDetail?.editor.album ?? ({} as BatchEditAlbumDraft)), [field]: value }));
  }

  function handleTrackFieldChange(trackId: string, field: keyof BatchEditTrackRow, value: string) {
    const baseTrack = mergedTracks.find((track) => track.id === trackId);
    if (!baseTrack) {
      return;
    }
    setTrackDraftsById((current) => ({
      ...current,
      [trackId]: {
        ...(current[trackId] ?? baseTrack),
        [field]: value,
      },
    }));
  }

  function toggleTrackExpanded(trackId: string) {
    setExpandedTrackIds((current) => {
      const next = new Set(current);
      if (next.has(trackId)) {
        next.delete(trackId);
      } else {
        next.add(trackId);
      }
      return next;
    });
  }

  async function handleFindRelease() {
    if (!selectedAlbumId) {
      return;
    }
    try {
      setFindingRelease(true);
      setPageError(null);
      const payload = await findBatchEditRelease(selectedAlbumId, {
        artist: releaseQueryArtist,
        album: releaseQueryAlbum,
      });
      setPendingReleasePreview(null);
      setReleaseCandidates(payload.candidates);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : t("batchEditing.errors.findReleases"));
    } finally {
      setFindingRelease(false);
    }
  }

  async function handlePreviewRelease(candidate: BatchEditCandidate) {
    if (!selectedAlbumId) {
      return;
    }
    try {
      setPreviewingReleaseId(candidate.id);
      setPageError(null);
      const payload = await applyBatchEditRelease(selectedAlbumId, {
        provider: candidate.provider,
        providerReleaseId: candidate.providerReleaseId,
      });
      setPendingReleasePreview(payload);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : t("batchEditing.errors.previewRelease"));
    } finally {
      setPreviewingReleaseId(null);
    }
  }

  function handleApplyReleasePreview() {
    if (!pendingReleasePreview) {
      return;
    }
    setAlbumDraft(pendingReleasePreview.album);
    setTrackDraftsById(Object.fromEntries(pendingReleasePreview.tracks.map((track) => [track.id, track])));
    setArtworkDraft(pendingReleasePreview.artwork);
    setReleaseReplacementDraft(pendingReleasePreview);
    setPendingReleasePreview(null);
    setReleaseDialogOpen(false);
  }

  async function handleFindArtwork() {
    if (!selectedAlbumId || !mergedAlbumDraft) {
      return;
    }
    try {
      setFindingArtwork(true);
      setPageError(null);
      const payload = await findBatchEditArtwork(selectedAlbumId, {
        artist: mergedAlbumDraft.albumArtist || mergedAlbumDraft.releaseArtist,
        album: mergedAlbumDraft.albumTitle,
      });
      setArtworkOptions(payload.options);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : t("batchEditing.errors.findArtwork"));
    } finally {
      setFindingArtwork(false);
    }
  }

  function openArtworkDialog() {
    setArtworkDialogOpen(true);
    setArtworkTab("provider");
    setArtworkOptions([]);
    void handleFindArtwork();
  }

  function handleLocalArtworkFile(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      setArtworkDraft({
        mode: "upload",
        imageBase64: result,
        mimeType: file.type,
        filename: file.name,
        coverUrl: result,
      });
    };
    reader.readAsDataURL(file);
  }

  function handleArtworkInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) {
      handleLocalArtworkFile(file);
    }
    event.target.value = "";
  }

  function handleArtworkDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDraggingArtwork(false);
    const file = event.dataTransfer.files?.[0];
    if (file) {
      handleLocalArtworkFile(file);
    }
  }

  function applyProviderArtwork(option: BatchEditArtworkOption) {
    setArtworkDraft({
      mode: "fetch_provider",
      coverUrl: option.coverUrl,
    });
  }

  async function handleBulkApply() {
    const albumIds = Array.from(selectedAlbumIds);
    if (albumIds.length === 0) {
      return;
    }
    try {
      setSaving(true);
      setPageError(null);
      await bulkUpdateBatchEditAlbums({
        albumIds,
        albumArtist: bulkDraft.albumArtist || null,
        year: bulkDraft.year || null,
        genre: bulkDraft.genre || null,
        releaseType: bulkDraft.releaseType || null,
        comment: bulkDraft.comment || null,
      });
      setBulkOpen(false);
      setBulkDraft(emptyBulkDraft);
      setSelectedAlbumIds(new Set());
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setPageError(err instanceof Error ? err.message : t("batchEditing.errors.bulk"));
    } finally {
      setSaving(false);
    }
  }

  const sidebarStatus = albumsQuery.loading
    ? t("batchEditing.status.loading")
    : hasUnsavedChanges
      ? t("batchEditing.status.unsaved")
      : t("batchEditing.status.ready");

  const libraryPath = librarySettings.data?.libraryRoot || albumsQuery.data?.libraryPath || t("batchEditing.chooseLibrary");
  const disconnectedLibrary = !librarySettings.loading && !!librarySettings.data?.isConfigured && !librarySettings.data?.isAvailable;
  const noLibrarySelected = !librarySettings.loading && !librarySettings.data?.isConfigured;

  return (
    <AppShell
      header={(
        <header className="space-y-4 border-b border-border-soft/75 px-4 py-5 lg:px-8">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="space-y-1">
              <h1 className="text-[17px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">{t("batchEditing.title")}</h1>
              <p className="text-[13px] text-muted-foreground">
                {t("batchEditing.subtitle")}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="app-button-secondary rounded-2xl px-4 py-2 text-[13px]"
                type="button"
                onClick={() => setRefreshKey((value) => value + 1)}
              >
                {t("batchEditing.refresh")}
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3 text-[13px]">
            <span className="truncate text-[hsl(var(--text-base))]">{libraryPath}</span>
            <span className={noLibrarySelected ? "text-muted-foreground" : disconnectedLibrary ? "text-[hsl(var(--warning-fg))]" : "text-[hsl(var(--success-fg))]"}>
              {noLibrarySelected ? t("batchEditing.noLibrarySelected") : disconnectedLibrary ? t("common.disconnected") : t("common.connected")}
            </span>
            <span className="ml-auto text-muted-foreground">{t("batchEditing.albumCount", { count: filteredAlbums.length })}</span>
          </div>
        </header>
      )}
      sidebar={(
        <AppSidebar
          activePage={activePage}
          onNavigate={handleNavigate}
          statusLabel={sidebarStatus}
        />
      )}
    >
      <div className="grid min-h-0 flex-1 gap-4 xl:min-h-[740px] xl:grid-cols-[minmax(260px,22%)_minmax(0,1fr)]">
        <Panel className="flex h-full min-h-0 flex-col overflow-hidden p-3 xl:min-h-[740px]">
          <div className="flex items-center gap-2 rounded-2xl border border-border-soft/75 bg-surface-contrast/80 px-3 py-2.5">
            <Search className="h-4 w-4 text-muted-foreground" />
            <input
              className="batch-input min-w-0 flex-1 border-0 bg-transparent px-0 py-0 ring-0 focus:ring-0"
              placeholder={t("batchEditing.list.searchPlaceholder")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-x-hidden overflow-y-auto pr-1 [scrollbar-gutter:stable]">
            {filteredAlbums.map((album) => (
              <button
                key={album.id}
                className={cn(
                  "grid min-h-[92px] w-full grid-cols-[24px_56px_minmax(0,1fr)] gap-3 rounded-2xl border px-3 py-3 text-left transition",
                  album.id === selectedAlbumId ? "border-[hsl(var(--accent-hue)_70%_60%)] bg-surface-selected/90" : "border-border-soft/75 bg-surface-soft hover:bg-surface-subtle",
                )}
                type="button"
                onClick={() => handleSelectAlbum(album.id)}
              >
                <div className="pt-1">
                  <input
                    checked={selectedAlbumIds.has(album.id)}
                    type="checkbox"
                    onChange={() => handleToggleSelection(album.id)}
                    onClick={(event) => event.stopPropagation()}
                  />
                </div>
                <CoverImage alt={album.title} className="h-[56px] w-[56px] rounded-xl" compact priority src={album.coverUrl} />
                <div className="grid min-w-0 grid-rows-[auto_auto] gap-2">
                  <div className="min-w-0 space-y-1">
                    <h3 className="line-clamp-2 break-words text-[14px] font-semibold leading-5 text-[hsl(var(--text-strong))]">{album.title}</h3>
                    <p className="line-clamp-2 break-words text-[12px] leading-5 text-muted-foreground">{album.artist} • {album.year}</p>
                  </div>
                  <div className="flex min-w-0 flex-wrap gap-1.5">
                    {album.processingState === "completed" ? <IssueBadge className="min-w-0 shrink whitespace-normal text-left" compact severity="success" value={t("batchEditing.badges.completed")} /> : null}
                    {album.lowConfidence ? <IssueBadge className="min-w-0 shrink whitespace-normal text-left" compact severity="warning" issue={{ id: "low-confidence", label: t("batchEditing.badges.lowConfidence"), severity: "warning" }} /> : null}
                    {!album.coverUrl ? <IssueBadge className="min-w-0 shrink whitespace-normal text-left" compact severity="warning" issue={{ id: "missing-art", label: t("batchEditing.badges.missingArtwork"), severity: "warning" }} /> : null}
                    {selectedAlbumId === album.id && hasUnsavedChanges ? <IssueBadge className="min-w-0 shrink whitespace-normal text-left" compact severity="neutral" value={t("batchEditing.badges.metadataModified")} /> : null}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-border-soft/75 px-1 pt-3 text-[12px] text-muted-foreground">
            <span>{t("batchEditing.list.selectedCount", { count: selectedAlbumIds.size })}</span>
            <button
              className="app-button-secondary rounded-xl px-3 py-2"
              type="button"
              disabled={selectedAlbumIds.size === 0}
              onClick={() => setBulkOpen(true)}
            >
              {t("batchEditing.list.bulkEdit")}
            </button>
          </div>
        </Panel>

        <Panel className="flex h-full min-h-0 flex-col overflow-hidden p-0 xl:min-h-[740px]">
          {!selectedDetail || !mergedAlbumDraft ? (
            <div className="flex h-full items-center justify-center p-8 text-[13px] text-muted-foreground">
              {t("batchEditing.detail.selectPrompt")}
            </div>
          ) : (
            <div className="relative flex h-full min-h-0 flex-col">
              <div className="min-h-0 flex-1 overflow-y-auto">
                <div className="space-y-5 p-4 pb-28 lg:p-5 lg:pb-32">
                  <section className="rounded-[24px] border border-border-soft/80 bg-[linear-gradient(135deg,hsl(var(--accent)/0.16),hsl(var(--surface-subtle)/0.96))] p-4 lg:p-5">
                    <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
                      <CoverImage alt={displayedAlbumTitle} className="h-[158px] w-[158px] shrink-0 rounded-[28px]" src={currentCoverUrl} />
                      <div className="min-w-0 flex-1 space-y-3">
                        <div className="space-y-1">
                          <h2 className="break-words text-[24px] font-semibold leading-tight text-[hsl(var(--text-strong))]">{displayedAlbumTitle}</h2>
                          <p className="break-words text-[14px] leading-6 text-muted-foreground">{displayedAlbumArtist}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {selectedDetail.album.lowConfidence ? <IssueBadge compact severity="warning" issue={{ id: "low-confidence", label: t("batchEditing.badges.lowConfidence"), severity: "warning" }} /> : null}
                          {!selectedDetail.editor.artwork.hasArtwork ? <IssueBadge compact severity="warning" issue={{ id: "missing-art", label: t("batchEditing.badges.missingArtwork"), severity: "warning" }} /> : null}
                          {artworkDirty ? <IssueBadge compact severity="neutral" value={t("batchEditing.badges.artworkModified")} /> : null}
                          {releaseReplacementDraft ? <IssueBadge compact severity="success" value={t("batchEditing.badges.releaseDraftApplied")} /> : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            className="app-button-secondary inline-flex items-center gap-2 rounded-2xl px-3 py-2 text-[12px]"
                            type="button"
                            onClick={openArtworkDialog}
                          >
                            <ImagePlus className="h-3.5 w-3.5" />
                            {t("batchEditing.detail.replaceArtwork")}
                          </button>
                          <button
                            className={cn(
                              "inline-flex items-center gap-2 rounded-2xl px-3 py-2 text-[12px]",
                              selectedDetail.album.lowConfidence
                                ? "border border-[hsl(var(--warning-border)/0.6)] bg-warning text-warning-foreground"
                                : "app-button-secondary",
                            )}
                            type="button"
                            onClick={() => setReleaseDialogOpen(true)}
                          >
                            <Wand2 className="h-3.5 w-3.5" />
                            {t("batchEditing.detail.findRelease")}
                          </button>
                        </div>
                      </div>
                    </div>
                  </section>

                  <section className="space-y-3">
                    <SectionHeading
                      title={t("batchEditing.albumMeta.heading")}
                      detail={t("batchEditing.albumMeta.detail")}
                    />
                    <div className="grid gap-3 lg:grid-cols-2">
                      <Field label={t("batchEditing.albumMeta.albumTitle")} dirty={dirtyAlbumFields.has("albumTitle")} value={mergedAlbumDraft.albumTitle} onChange={(value) => handleAlbumFieldChange("albumTitle", value)} />
                      <Field label={t("batchEditing.albumMeta.albumArtist")} dirty={dirtyAlbumFields.has("albumArtist")} value={mergedAlbumDraft.albumArtist} onChange={(value) => handleAlbumFieldChange("albumArtist", value)} />
                      <Field label={t("batchEditing.albumMeta.releaseArtist")} dirty={dirtyAlbumFields.has("releaseArtist")} value={mergedAlbumDraft.releaseArtist} onChange={(value) => handleAlbumFieldChange("releaseArtist", value)} />
                      <Field label={t("batchEditing.albumMeta.year")} dirty={dirtyAlbumFields.has("year")} value={mergedAlbumDraft.year} onChange={(value) => handleAlbumFieldChange("year", value)} />
                      <Field label={t("batchEditing.albumMeta.genre")} dirty={dirtyAlbumFields.has("genre")} value={mergedAlbumDraft.genre} onChange={(value) => handleAlbumFieldChange("genre", value)} />
                      <Field label={t("batchEditing.albumMeta.releaseType")} dirty={dirtyAlbumFields.has("releaseType")} value={mergedAlbumDraft.releaseType} onChange={(value) => handleAlbumFieldChange("releaseType", value)} />
                    </div>
                  </section>

                  <section className="space-y-3">
                    <button
                      className="flex w-full items-center justify-between rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3 text-left"
                      type="button"
                      onClick={() => setAdvancedOpen((value) => !value)}
                    >
                      <div>
                        <h3 className="text-[14px] font-semibold text-[hsl(var(--text-strong))]">{t("batchEditing.advanced.heading")}</h3>
                        <p className="mt-1 text-[12px] text-muted-foreground">{t("batchEditing.advanced.detail")}</p>
                      </div>
                      {advancedOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                    </button>
                    {advancedOpen ? (
                      <div className="grid gap-3 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-4 lg:grid-cols-2">
                        <Field label={t("batchEditing.advanced.label")} dirty={dirtyAlbumFields.has("label")} value={mergedAlbumDraft.label} onChange={(value) => handleAlbumFieldChange("label", value)} />
                        <Field label={t("batchEditing.advanced.catalogNumber")} dirty={dirtyAlbumFields.has("catalogNumber")} value={mergedAlbumDraft.catalogNumber} onChange={(value) => handleAlbumFieldChange("catalogNumber", value)} />
                        <Field label={t("batchEditing.advanced.copyright")} dirty={dirtyAlbumFields.has("copyright")} value={mergedAlbumDraft.copyright} onChange={(value) => handleAlbumFieldChange("copyright", value)} />
                        <TextAreaField label={t("batchEditing.advanced.comment")} dirty={dirtyAlbumFields.has("comment")} value={mergedAlbumDraft.comment} onChange={(value) => handleAlbumFieldChange("comment", value)} />
                      </div>
                    ) : null}
                  </section>

                  {releaseReplacementDraft?.diff?.length ? (
                    <section className="space-y-3">
                      <SectionHeading
                        title={t("batchEditing.releasePreview.heading")}
                        detail={t("batchEditing.releasePreview.detail")}
                      />
                      <ReleaseDiffPreview rows={releaseReplacementDraft.diff} />
                    </section>
                  ) : null}

                  <section className="space-y-3">
                    <SectionHeading
                      title={t("batchEditing.trackMeta.heading")}
                      detail={t("batchEditing.trackMeta.detail")}
                    />
                    <div className="space-y-2">
                      {mergedTracks.map((track) => {
                        const expanded = expandedTrackIds.has(track.id);
                        const dirty = dirtyTrackIds.has(track.id);
                        return (
                          <div key={track.id} className="overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-subtle/85">
                            <button
                              className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-surface-subtle"
                              type="button"
                              onClick={() => toggleTrackExpanded(track.id)}
                            >
                              <div className="pt-0.5 text-muted-foreground">
                                {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                                  <span className="shrink-0 text-[13px] font-semibold text-[hsl(var(--info-fg))]">{String(track.index).padStart(2, "0")}.</span>
                                  <span className="break-words text-[14px] font-medium text-[hsl(var(--text-strong))]">{track.title}</span>
                                  {dirty ? <DirtyPill label={t("batchEditing.badges.modified")} /> : null}
                                </div>
                                <p className="mt-1 break-words text-[12px] leading-5 text-muted-foreground">{track.artist}</p>
                              </div>
                              {track.issues.length ? (
                                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                                  {track.issues.map((issue) => <IssueBadge key={issue.id} compact issue={issue} />)}
                                </div>
                              ) : (
                                <span className="shrink-0 text-[11px] text-[hsl(var(--success-fg))]">{t("batchEditing.badges.ok")}</span>
                              )}
                            </button>
                            {expanded ? (
                              <div className="border-t border-border-soft/75 px-4 py-4">
                                <div className="grid gap-3 lg:grid-cols-2">
                                  <Field label={t("batchEditing.trackMeta.title")} value={track.title} onChange={(value) => handleTrackFieldChange(track.id, "title", value)} />
                                  <Field label={t("batchEditing.trackMeta.artist")} value={track.artist} onChange={(value) => handleTrackFieldChange(track.id, "artist", value)} />
                                  <Field label={t("batchEditing.trackMeta.trackNumber")} value={track.trackNumber} onChange={(value) => handleTrackFieldChange(track.id, "trackNumber", value)} />
                                  <Field label={t("batchEditing.trackMeta.discNumber")} value={track.discNumber} onChange={(value) => handleTrackFieldChange(track.id, "discNumber", value)} />
                                  <Field label={t("batchEditing.trackMeta.genre")} value={track.genre} onChange={(value) => handleTrackFieldChange(track.id, "genre", value)} />
                                  <Field label={t("batchEditing.trackMeta.albumArtist")} value={track.albumArtist} onChange={(value) => handleTrackFieldChange(track.id, "albumArtist", value)} />
                                  <TextAreaField label={t("batchEditing.trackMeta.comment")} value={track.comment} onChange={(value) => handleTrackFieldChange(track.id, "comment", value)} />
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  {pageError ? <p className="text-[12px] text-[hsl(var(--danger-fg))]">{pageError}</p> : null}
                </div>
              </div>

              {hasUnsavedChanges ? (
                <div className="sticky bottom-0 z-10 border-t border-border-soft/75 bg-panel/95 px-4 py-3 backdrop-blur-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-[13px] font-semibold text-[hsl(var(--text-strong))]">{t("batchEditing.unsaved.title")}</p>
                      <p className="text-[12px] text-muted-foreground">{t("batchEditing.unsaved.detail")}</p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        className="app-button-secondary rounded-2xl px-4 py-2 text-[13px]"
                        type="button"
                        onClick={handleReset}
                      >
                        {t("batchEditing.unsaved.discard")}
                      </button>
                      <button
                        className="app-button-primary rounded-2xl px-4 py-2 text-[13px] font-semibold"
                        type="button"
                        disabled={saving}
                        onClick={() => void handleSave()}
                      >
                        {saving ? t("batchEditing.unsaved.saving") : t("batchEditing.unsaved.save")}
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </Panel>
      </div>

      {releaseDialogOpen ? (
        <Dialog onClose={() => setReleaseDialogOpen(false)} title={t("batchEditing.releaseDialog.title")}>
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <Field label={t("batchEditing.releaseDialog.artist")} value={releaseQueryArtist} onChange={setReleaseQueryArtist} />
              <Field label={t("batchEditing.releaseDialog.album")} value={releaseQueryAlbum} onChange={setReleaseQueryAlbum} />
            </div>
            <button
              className="app-button-primary rounded-2xl px-4 py-2 text-[13px] font-semibold"
              type="button"
              disabled={findingRelease}
              onClick={() => void handleFindRelease()}
            >
              {findingRelease ? t("batchEditing.releaseDialog.searching") : t("batchEditing.releaseDialog.search")}
            </button>

            {pendingReleasePreview ? (
              <div className="space-y-4 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-4">
                <div className="flex flex-col gap-4 md:flex-row md:items-start">
                  <CoverImage alt={pendingReleasePreview.candidate.title} className="h-24 w-24 rounded-2xl" compact src={pendingReleasePreview.candidate.coverUrl} />
                  <div className="min-w-0 space-y-1">
                    <h4 className="break-words text-[15px] font-semibold text-[hsl(var(--text-strong))]">{pendingReleasePreview.candidate.title}</h4>
                    <p className="break-words text-[12px] text-muted-foreground">{pendingReleasePreview.candidate.artist}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {pendingReleasePreview.candidate.year} • {t("batchEditing.releaseDialog.tracks", { count: pendingReleasePreview.candidate.trackCount })} • {pendingReleasePreview.candidate.provider}
                    </p>
                  </div>
                </div>
                <ReleaseDiffPreview rows={pendingReleasePreview.diff} compact />
                <div className="flex flex-wrap gap-2">
                  <button
                    className="app-button-secondary rounded-2xl px-4 py-2 text-[13px]"
                    type="button"
                    onClick={() => setPendingReleasePreview(null)}
                  >
                    {t("batchEditing.releaseDialog.backToResults")}
                  </button>
                  <button
                    className="app-button-primary rounded-2xl px-4 py-2 text-[13px] font-semibold"
                    type="button"
                    onClick={handleApplyReleasePreview}
                  >
                    {t("batchEditing.releaseDialog.applyRelease")}
                  </button>
                </div>
              </div>
            ) : null}

            <div className="max-h-[420px] space-y-2 overflow-y-auto">
              {releaseCandidates.map((candidate) => (
                <button
                  key={candidate.id}
                  className="grid w-full grid-cols-[64px_minmax(0,1fr)_124px] gap-3 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-3 text-left"
                  type="button"
                  disabled={previewingReleaseId === candidate.id}
                  onClick={() => void handlePreviewRelease(candidate)}
                >
                  <CoverImage alt={candidate.title} className="h-16 w-16 rounded-xl" compact src={candidate.coverUrl} />
                  <div className="min-w-0">
                    <h4 className="break-words text-[13px] font-semibold text-[hsl(var(--text-strong))]">{candidate.title}</h4>
                    <p className="break-words text-[12px] text-muted-foreground">{candidate.artist}</p>
                    <p className="text-[11px] text-muted-foreground">{candidate.year} • {t("batchEditing.releaseDialog.tracks", { count: candidate.trackCount })} • {candidate.provider}</p>
                    {formatArtworkResolution(candidate.artworkWidth, candidate.artworkHeight) ? (
                      <p className="mt-1 text-[11px] text-[hsl(var(--info-fg))]">{t("batchEditing.releaseDialog.artworkRes", { res: formatArtworkResolution(candidate.artworkWidth, candidate.artworkHeight) ?? "" })}</p>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-end text-[12px] text-[hsl(var(--success-fg))]">
                    {previewingReleaseId === candidate.id ? t("batchEditing.releaseDialog.loading") : t("batchEditing.releaseDialog.preview")}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </Dialog>
      ) : null}

      {artworkDialogOpen ? (
        <Dialog onClose={() => setArtworkDialogOpen(false)} title={t("batchEditing.artworkDialog.title")}>
          <div className="space-y-4">
            <div className="inline-flex rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-1">
              <button
                className={cn("rounded-[14px] px-3 py-2 text-[12px] transition", artworkTab === "provider" ? "bg-surface-strong text-[hsl(var(--text-strong))]" : "text-muted-foreground")}
                type="button"
                onClick={() => {
                  setArtworkTab("provider");
                  if (artworkOptions.length === 0) {
                    void handleFindArtwork();
                  }
                }}
              >
                {t("batchEditing.artworkDialog.providerTab")}
              </button>
              <button
                className={cn("rounded-[14px] px-3 py-2 text-[12px] transition", artworkTab === "local" ? "bg-surface-strong text-[hsl(var(--text-strong))]" : "text-muted-foreground")}
                type="button"
                onClick={() => setArtworkTab("local")}
              >
                {t("batchEditing.artworkDialog.localTab")}
              </button>
            </div>

            {artworkTab === "provider" ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3 text-[12px] text-muted-foreground">
                  <span>{t("batchEditing.artworkDialog.searchingFor")}</span>
                  <span className="text-[hsl(var(--text-strong))]">{displayedAlbumArtist}</span>
                  <span>•</span>
                  <span className="text-[hsl(var(--text-strong))]">{displayedAlbumTitle}</span>
                  <button
                    className="app-button-secondary ml-auto rounded-xl px-3 py-1.5"
                    type="button"
                    disabled={findingArtwork}
                    onClick={() => void handleFindArtwork()}
                  >
                    {findingArtwork ? t("batchEditing.artworkDialog.searching") : t("batchEditing.artworkDialog.refresh")}
                  </button>
                </div>
                <div className="space-y-2">
                  {artworkOptions.map((option) => (
                    <button
                      key={option.id}
                      className="grid w-full grid-cols-[88px_minmax(0,1fr)_104px] gap-3 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-3 text-left"
                      type="button"
                      onClick={() => applyProviderArtwork(option)}
                    >
                      <CoverImage alt={option.releaseTitle || t("batchEditing.artworkDialog.option")} className="h-[88px] w-[88px] rounded-2xl" compact src={option.coverUrl} />
                      <div className="min-w-0 space-y-1">
                        <p className="text-[13px] font-semibold text-[hsl(var(--text-strong))]">{option.provider === "musicbrainz" ? "MusicBrainz" : "Deezer"}</p>
                        <p className="break-words text-[12px] text-muted-foreground">{option.releaseTitle || displayedAlbumTitle}</p>
                        <p className="text-[11px] text-[hsl(var(--info-fg))]">{formatArtworkResolution(option.width, option.height) || t("batchEditing.artworkDialog.resolutionUnavailable")}</p>
                      </div>
                      <div className="flex items-center justify-end text-[12px] text-[hsl(var(--success-fg))]">{t("batchEditing.artworkDialog.apply")}</div>
                    </button>
                  ))}
                  {!findingArtwork && artworkOptions.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-border-soft/75 px-4 py-6 text-center text-[12px] text-muted-foreground">
                      {t("batchEditing.artworkDialog.noArtwork")}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <button
                  className={cn(
                    "flex w-full flex-col items-center justify-center gap-2 rounded-[24px] border border-dashed px-6 py-10 text-center transition",
                    draggingArtwork ? "border-[hsl(var(--info-border)/0.6)] bg-info/40" : "border-border-soft/80 bg-surface-subtle/85 hover:bg-surface-subtle",
                  )}
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    setDraggingArtwork(true);
                  }}
                  onDragOver={(event) => event.preventDefault()}
                  onDragLeave={(event) => {
                    event.preventDefault();
                    setDraggingArtwork(false);
                  }}
                  onDrop={handleArtworkDrop}
                >
                  <Upload className="h-5 w-5 text-[hsl(var(--info-fg))]" />
                  <p className="text-[13px] font-medium text-[hsl(var(--text-strong))]">{t("batchEditing.artworkDialog.dragPrompt")}</p>
                  <p className="text-[12px] text-muted-foreground">{t("batchEditing.artworkDialog.dragHint")}</p>
                </button>
                <input
                  ref={fileInputRef}
                  className="hidden"
                  type="file"
                  accept="image/*"
                  onChange={handleArtworkInputChange}
                />
                {artworkDraft.mode === "upload" && artworkDraft.coverUrl ? (
                  <div className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-4">
                    <p className="mb-3 text-[12px] text-muted-foreground">{artworkDraft.filename || t("batchEditing.artworkDialog.selectedFile")}</p>
                    <CoverImage alt={t("batchEditing.artworkDialog.uploadedPreview")} className="h-[180px] w-[180px] rounded-[24px]" src={artworkDraft.coverUrl} />
                  </div>
                ) : null}
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-2xl border border-[hsl(var(--danger-border)/0.6)] bg-danger px-4 py-2 text-[13px] text-danger-foreground"
                type="button"
                onClick={() => setArtworkDraft({ mode: "remove" })}
              >
                {t("batchEditing.artworkDialog.removeArtwork")}
              </button>
              <button
                className="app-button-secondary rounded-2xl px-4 py-2 text-[13px]"
                type="button"
                onClick={() => setArtworkDialogOpen(false)}
              >
                {t("batchEditing.artworkDialog.done")}
              </button>
            </div>
          </div>
        </Dialog>
      ) : null}

      {bulkOpen ? (
        <Dialog onClose={() => setBulkOpen(false)} title={t("batchEditing.bulkDialog.title")}>
          <div className="space-y-3">
            <p className="text-[12px] text-muted-foreground">{t("batchEditing.bulkDialog.selectedCount", { count: selectedAlbumIds.size })}</p>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label={t("batchEditing.bulkDialog.albumArtist")} value={bulkDraft.albumArtist} onChange={(value) => setBulkDraft((current) => ({ ...current, albumArtist: value }))} />
              <Field label={t("batchEditing.bulkDialog.year")} value={bulkDraft.year} onChange={(value) => setBulkDraft((current) => ({ ...current, year: value }))} />
              <Field label={t("batchEditing.bulkDialog.genre")} value={bulkDraft.genre} onChange={(value) => setBulkDraft((current) => ({ ...current, genre: value }))} />
              <Field label={t("batchEditing.bulkDialog.releaseType")} value={bulkDraft.releaseType} onChange={(value) => setBulkDraft((current) => ({ ...current, releaseType: value }))} />
              <TextAreaField label={t("batchEditing.bulkDialog.comment")} value={bulkDraft.comment} onChange={(value) => setBulkDraft((current) => ({ ...current, comment: value }))} />
            </div>
            <button
              className="app-button-primary rounded-2xl px-4 py-2 text-[13px] font-semibold"
              type="button"
              disabled={saving}
              onClick={() => void handleBulkApply()}
            >
              {saving ? t("batchEditing.bulkDialog.applying") : t("batchEditing.bulkDialog.apply")}
            </button>
          </div>
        </Dialog>
      ) : null}
    </AppShell>
  );
}

function Field({
  label,
  value,
  onChange,
  dirty = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  dirty?: boolean;
}) {
  return (
    <label className="block space-y-1">
      <FieldLabel dirty={dirty} label={label} />
      <input
        className="batch-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
  dirty = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  dirty?: boolean;
}) {
  return (
    <label className="block space-y-1 md:col-span-2">
      <FieldLabel dirty={dirty} label={label} />
      <textarea
        className="batch-input min-h-[90px]"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function FieldLabel({ label, dirty }: { label: string; dirty: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
      <span>{label}</span>
      {dirty ? <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--info-fg))]" /> : null}
    </span>
  );
}

function DirtyPill({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-[hsl(var(--info-border)/0.48)] bg-info px-2 py-0.5 text-[10px] text-info-foreground">
      {label}
    </span>
  );
}

function SectionHeading({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="space-y-1">
      <h3 className="text-[15px] font-semibold text-[hsl(var(--text-strong))]">{title}</h3>
      <p className="text-[12px] leading-5 text-muted-foreground">{detail}</p>
    </div>
  );
}

function ReleaseDiffPreview({ rows, compact = false }: { rows: MetadataDiffField[]; compact?: boolean }) {
  return (
    <div className={cn("space-y-2 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-4", compact && "p-3")}>
      <div className="hidden text-[11px] uppercase tracking-[0.14em] text-muted-foreground md:grid md:grid-cols-[140px_minmax(0,1fr)_minmax(0,1fr)]">
        <span>Field</span>
        <span>Current</span>
        <span>New</span>
      </div>
      {rows.map((item) => (
        <div key={item.id} className="grid gap-2 text-[12px] text-muted-foreground md:grid-cols-[140px_minmax(0,1fr)_minmax(0,1fr)]">
          <span className="text-[hsl(var(--text-base))]">{item.label}</span>
          <span className="break-words">{item.before}</span>
          <span className="break-words text-[hsl(var(--success-fg))]">{item.after}</span>
        </div>
      ))}
    </div>
  );
}

function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <ModalPortal>
      <div className="app-modal-overlay fixed inset-0 z-50 flex items-center justify-center p-5">
        <div className="w-full max-w-[920px] rounded-[28px] border border-border-soft/80 bg-panel p-5 shadow-panel">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-[16px] font-semibold text-[hsl(var(--text-strong))]">{title}</h3>
            <button className="rounded-full px-3 py-1 text-[13px] text-muted-foreground" type="button" onClick={onClose}>
              <X className="h-4 w-4" />
            </button>
          </div>
          {children}
        </div>
      </div>
    </ModalPortal>
  );
}

function diffAlbumFields(base: BatchEditAlbumDraft | null, draft: BatchEditAlbumDraft | null) {
  const dirty = new Set<keyof BatchEditAlbumDraft>();
  if (!base || !draft) {
    return dirty;
  }
  for (const field of albumFieldOrder) {
    if ((base[field] ?? "") !== (draft[field] ?? "")) {
      dirty.add(field);
    }
  }
  return dirty;
}

function diffTrackIds(baseTracks: BatchEditTrackRow[], draftTracks: BatchEditTrackRow[]) {
  const dirty = new Set<string>();
  for (const track of draftTracks) {
    const base = baseTracks.find((candidate) => candidate.id === track.id);
    if (!base) {
      dirty.add(track.id);
      continue;
    }
    if (
      base.title !== track.title
      || base.artist !== track.artist
      || base.albumArtist !== track.albumArtist
      || base.trackNumber !== track.trackNumber
      || base.discNumber !== track.discNumber
      || base.genre !== track.genre
      || base.comment !== track.comment
    ) {
      dirty.add(track.id);
    }
  }
  return dirty;
}

function resolveDisplayArtist(
  draft: BatchEditAlbumDraft | null,
  selectedDetail: BatchEditAlbumDetailPayload | null,
) {
  return [
    draft?.albumArtist,
    draft?.releaseArtist,
    selectedDetail?.editor.album.albumArtist,
    selectedDetail?.editor.album.releaseArtist,
    selectedDetail?.album.albumArtist,
    selectedDetail?.album.artist,
  ].find((value) => value && value.trim()) || "";
}

function formatArtworkResolution(width?: number | null, height?: number | null) {
  if (!width || !height) {
    return "";
  }
  return `${width}×${height}`;
}
