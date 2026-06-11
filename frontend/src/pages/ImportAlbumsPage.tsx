import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { BulkFieldLabel } from "@/components/BulkFieldLabel";
import { Panel } from "@/components/Panel";
import { AppHeader } from "@/components/layout/AppHeader";
import { AppShell } from "@/components/layout/AppShell";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { LibraryPickerDialog } from "@/components/layout/LibraryPickerDialog";
import { AlbumInspector, AlbumList, LogPanel, TrackTable } from "@/components/music";
import type { AlbumFilterState } from "@/components/music/AlbumList";
import type { EditableInspectorFields } from "@/components/music/AlbumInspector";
import { useAlbumActions } from "@/hooks/useAlbumActions";
import { useAlbumDetail } from "@/hooks/useAlbumDetail";
import { useAlbums } from "@/hooks/useAlbums";
import { useCleanLibrary } from "@/hooks/useCleanLibrary";
import { useLibrarySettings } from "@/hooks/useLibrarySettings";
import { useRelatedReleases } from "@/hooks/useRelatedReleases";
import { useI18n } from "@/i18n/useI18n";
import { devLog } from "@/lib/dev-log";
import { getAlbumActionableIssueCount, hasAlbumActionableIssues, summarizeLibraryIssues } from "@/lib/issue-counts";
import type { AppPage } from "@/types/layout";
import type {
  AlbumCompilationOverride,
  AlbumInspectorData,
  AlbumListItem,
  AlbumMetadataOverride,
  AlbumExplicitOverride,
  CapitalizationMode,
  CoverHandlingMode,
  MetadataProviderOverride,
  SummaryStat,
  TrackRow,
  YearSourceOverride,
} from "@/types/music";

type TrackIssueFilter = "all" | "issues" | "clean";

const defaultAlbumFilters: AlbumFilterState = {
  issuesOnly: false,
  cleanOnly: false,
  changedOnly: false,
  sortBy: "title",
  sortDirection: "asc",
};

type AlbumOverrideValues = Omit<AlbumMetadataOverride, "albumId">;
type AlbumOverrideMap = Record<string, Partial<AlbumOverrideValues>>;

interface BulkEditDraft {
  albumTitle: string;
  albumArtist: string;
  genre: string;
  year: string;
  disc: string;
  discTotal: string;
  compilation: AlbumCompilationOverride;
  explicit: AlbumExplicitOverride;
  capitalizationMode: CapitalizationMode;
  normalizeFeaturingArtists: boolean;
  overwriteExistingTags: boolean;
  metadataProvider: MetadataProviderOverride;
  yearSource: YearSourceOverride;
  coverHandlingMode: CoverHandlingMode;
}

const emptyBulkDraft: BulkEditDraft = {
  albumTitle: "",
  albumArtist: "",
  genre: "",
  year: "",
  disc: "",
  discTotal: "",
  compilation: "auto",
  explicit: "auto",
  capitalizationMode: "none",
  normalizeFeaturingArtists: false,
  overwriteExistingTags: false,
  metadataProvider: "auto",
  yearSource: "auto",
  coverHandlingMode: "auto",
};

const emptyTracks: TrackRow[] = [];

function cleanAlbumOverride(values: Partial<AlbumOverrideValues>): Partial<AlbumOverrideValues> {
  const next: Record<string, unknown> = {};
  for (const [key, rawValue] of Object.entries(values) as Array<[string, unknown]>) {
    if (rawValue == null) {
      continue;
    }
    if (typeof rawValue === "boolean") {
      if (rawValue) {
        next[key] = rawValue;
      }
      continue;
    }
    const value = String(rawValue).trim();
    if (!value || value === "auto" || value === "none") {
      continue;
    }
    next[key] = rawValue;
  }
  return next as Partial<AlbumOverrideValues>;
}

interface ImportAlbumsPageProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
}

export function ImportAlbumsPage({ activePage, onNavigate }: ImportAlbumsPageProps) {
  const { t } = useI18n();
  const importPageActive = activePage === "import";
  const [refreshKey, setRefreshKey] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string | null>(null);
  const [selectionLockedEmpty, setSelectionLockedEmpty] = useState(false);
  const [albumSearch, setAlbumSearch] = useState("");
  const [albumFilters, setAlbumFilters] = useState<AlbumFilterState>(defaultAlbumFilters);
  const [trackIssueFilter, setTrackIssueFilter] = useState<TrackIssueFilter>("all");
  const [metricFilter, setMetricFilter] = useState<string | null>(null);
  const [selectedTrackIds, setSelectedTrackIds] = useState<Set<string>>(new Set());
  const [logDialogOpen, setLogDialogOpen] = useState(false);
  const [stagedOverrides, setStagedOverrides] = useState<AlbumOverrideMap>({});
  const [bulkEditOpen, setBulkEditOpen] = useState(false);
  const [bulkDraft, setBulkDraft] = useState<BulkEditDraft>(emptyBulkDraft);
  const deferredAlbumSearch = useDeferredValue(albumSearch);
  const deferredAlbumFilters = useDeferredValue(albumFilters);

  const librarySettings = useLibrarySettings();
  const cleanLibrary = useCleanLibrary();
  const developerMode = librarySettings.data?.developerMode ?? false;
  const { data: albumsPayload, error: albumsError } = useAlbums(refreshKey, developerMode, importPageActive);
  const safeAlbums = albumsPayload?.albums ?? [];
  const effectiveSelectedAlbumId = useMemo(() => {
    if (selectionLockedEmpty) {
      return null;
    }
    if (selectedAlbumId && safeAlbums.some((album) => album.id === selectedAlbumId)) {
      return selectedAlbumId;
    }
    return safeAlbums[0]?.id ?? null;
  }, [safeAlbums, selectedAlbumId, selectionLockedEmpty]);
  const { data: detailData, loading: detailLoading, error: detailError } = useAlbumDetail(
    effectiveSelectedAlbumId,
    refreshKey,
    developerMode,
    importPageActive,
  );
  const { data: relatedReleasesData, loading: relatedReleasesLoading } = useRelatedReleases(
    effectiveSelectedAlbumId,
    refreshKey,
    importPageActive,
  );
  const { data: actionsData, loading: actionsLoading } = useAlbumActions(
    effectiveSelectedAlbumId,
    refreshKey,
    importPageActive,
  );

  const libraryState = librarySettings.data;
  const libraryPath = albumsPayload?.libraryPath || libraryState?.libraryRoot || t("import.chooseFolder");
  const noLibrarySelected = !librarySettings.loading && !libraryState?.isConfigured;
  const disconnectedLibrary = !librarySettings.loading && !!libraryState?.isConfigured && !libraryState?.isAvailable;
  const blockerMessage = disconnectedLibrary
    ? libraryState?.error || t("import.libraryDisconnected")
    : t("import.chooseLibraryPrompt");
  const emptyInspector = useMemo<AlbumInspectorData>(() => ({
    id: "",
    coverUrl: "",
    title: t("import.emptyInspector.title"),
    artist: t("import.emptyInspector.artist"),
    year: t("import.emptyInspector.year"),
    albumArtist: t("import.emptyInspector.albumArtist"),
    genre: t("import.emptyInspector.genre"),
    disc: t("import.emptyInspector.disc"),
    metrics: [
      { id: "info", label: t("import.metrics.info"), value: "i", severity: "neutral" },
      { id: "danger", label: t("import.metrics.issues"), value: "0", severity: "danger" },
      { id: "warning", label: t("import.metrics.metadata"), value: "0", severity: "warning" },
      { id: "success", label: t("import.metrics.ready"), value: "0", severity: "success" },
    ],
    issues: [],
  }), [t]);

  useEffect(() => {
    setSelectedAlbumId(null);
    setSelectionLockedEmpty(false);
    setMetricFilter(null);
  }, [libraryState?.libraryRoot]);

  useEffect(() => {
    if (!effectiveSelectedAlbumId || selectionLockedEmpty || selectedAlbumId === effectiveSelectedAlbumId) {
      return;
    }
    setSelectedAlbumId(effectiveSelectedAlbumId);
  }, [effectiveSelectedAlbumId, selectedAlbumId, selectionLockedEmpty]);

  useEffect(() => {
    const nextTrackIds = new Set((detailData.tracks ?? []).map((track) => track.id));
    setSelectedTrackIds(nextTrackIds);
  }, [detailData.tracks, effectiveSelectedAlbumId]);

  const dirtyAlbumIds = useMemo(() => new Set(
    Object.entries(stagedOverrides)
      .filter(([, overrides]) => Object.keys(overrides).length > 0)
      .map(([albumId]) => albumId),
  ), [stagedOverrides]);

  const preparedAlbums = useMemo(() => safeAlbums.map((album) => {
    const artist = album.artist === "Unknown artist" ? t("common.unknownArtist") : album.artist;
    const year = album.year === "Unknown" ? t("common.unknown") : album.year;
    return {
      ...album,
      artist,
      year,
      dirty: dirtyAlbumIds.has(album.id),
      issueCount: getAlbumActionableIssueCount(album),
      searchIndex: `${album.title} ${artist} ${year}`.toLowerCase(),
    };
  }), [dirtyAlbumIds, safeAlbums, t]);

  const albums = useMemo<AlbumListItem[]>(() => {
    const searchTerm = deferredAlbumSearch.trim().toLowerCase();
    const filtered = preparedAlbums
      .filter((album) => {
        if (deferredAlbumFilters.issuesOnly && !hasAlbumActionableIssues(album)) {
          return false;
        }
        if (deferredAlbumFilters.cleanOnly && hasAlbumActionableIssues(album)) {
          return false;
        }
        if (deferredAlbumFilters.changedOnly && !album.dirty) {
          return false;
        }
        if (!searchTerm) {
          return true;
        }

        return album.searchIndex.includes(searchTerm);
      })
      .sort((left, right) => {
        const leftValue =
          deferredAlbumFilters.sortBy === "artist" ? left.artist :
            deferredAlbumFilters.sortBy === "issueCount" ? String(left.issueCount).padStart(4, "0") :
              deferredAlbumFilters.sortBy === "year" ? left.year :
                left.title;
        const rightValue =
          deferredAlbumFilters.sortBy === "artist" ? right.artist :
            deferredAlbumFilters.sortBy === "issueCount" ? String(right.issueCount).padStart(4, "0") :
              deferredAlbumFilters.sortBy === "year" ? right.year :
                right.title;
        return deferredAlbumFilters.sortDirection === "asc"
          ? leftValue.localeCompare(rightValue)
          : rightValue.localeCompare(leftValue);
      });

    return filtered.map((album) => ({
      ...album,
      selected: album.id === effectiveSelectedAlbumId,
    }));
  }, [deferredAlbumFilters, deferredAlbumSearch, effectiveSelectedAlbumId, preparedAlbums]);

  const summary = useMemo<SummaryStat[]>(() => {
    const albumCount = safeAlbums.length;
    const trackCount = safeAlbums.reduce((total, album) => total + album.trackCount, 0);
    const actionableIssues = summarizeLibraryIssues(safeAlbums);
    const issuesCount = actionableIssues.total;
    const readyCount = safeAlbums.filter((album) => album.status === "ready").length;
    const processingCount = safeAlbums.filter((album) => {
      const state = album.processingState ?? "idle";
      return state !== "idle" && state !== "completed";
    }).length;

    return [
      { id: "albums", label: t("import.summary.albumsLabel"), value: String(albumCount), hint: t("import.summary.albumsHint"), severity: "neutral" },
      { id: "tracks", label: t("import.summary.tracksLabel"), value: String(trackCount), hint: t("import.summary.tracksHint"), severity: "neutral" },
      { id: "issues", label: t("import.summary.issuesLabel"), value: String(issuesCount), hint: t("import.summary.issuesHint"), severity: issuesCount > 0 ? "warning" : "success" },
      { id: "ready", label: t("import.summary.readyLabel"), value: String(readyCount), hint: t("import.summary.readyHint"), severity: readyCount > 0 ? "success" : "neutral" },
      { id: "processing", label: t("import.summary.processingLabel"), value: String(processingCount), hint: t("import.summary.processingHint"), severity: processingCount > 0 ? "warning" : "neutral" },
    ];
  }, [safeAlbums, t]);
  const sidebarStatus = cleanLibrary.loading
    ? t("import.processingRun")
    : noLibrarySelected
      ? t("import.pickLibraryToBegin")
      : disconnectedLibrary
        ? t("import.libraryDisconnected")
        : t("import.workspaceReady");

  const baseInspector = detailData.inspector ?? emptyInspector;
  const inspectorOverride = effectiveSelectedAlbumId ? stagedOverrides[effectiveSelectedAlbumId] : undefined;
  const visibleInspector = {
    ...baseInspector,
    title: inspectorOverride?.albumTitle ?? baseInspector.title,
    artist: baseInspector.artist === "Unknown artist" ? t("common.unknownArtist") : baseInspector.artist,
    albumArtist: (inspectorOverride?.albumArtist ?? baseInspector.albumArtist) === "Unknown artist"
      ? t("common.unknownArtist")
      : (inspectorOverride?.albumArtist ?? baseInspector.albumArtist),
    genre: (inspectorOverride?.genre ?? baseInspector.genre) === "Unknown"
      ? t("common.unknown")
      : (inspectorOverride?.genre ?? baseInspector.genre),
    year: (inspectorOverride?.year ?? baseInspector.year) === "Unknown"
      ? t("common.unknown")
      : (inspectorOverride?.year ?? baseInspector.year),
    disc: inspectorOverride?.disc ?? baseInspector.disc,
  };

  const tracks = detailData.tracks.length ? detailData.tracks : emptyTracks;
  const filteredTracks = useMemo(() => {
    let nextTracks = tracks;
    if (trackIssueFilter === "issues") {
      nextTracks = nextTracks.filter((track) => track.issues.length > 0);
    } else if (trackIssueFilter === "clean") {
      nextTracks = nextTracks.filter((track) => track.issues.length === 0);
    }

    if (metricFilter === "danger" || metricFilter === "warning") {
      nextTracks = nextTracks.filter((track) => track.issues.some((issue) => issue.severity === metricFilter));
    } else if (metricFilter === "success") {
      nextTracks = nextTracks.filter((track) => track.issues.length === 0);
    }

    return nextTracks;
  }, [metricFilter, trackIssueFilter, tracks]);

  async function handleSaveLibraryRoot(nextLibraryPath: string, nextOutputPath: string) {
    const saved = await librarySettings.saveLibraryRoots(nextLibraryPath, nextOutputPath);
    if (!saved) {
      return false;
    }
    setSelectedAlbumId(null);
    setSelectionLockedEmpty(false);
    setRefreshKey((value) => value + 1);
    return true;
  }

  async function handlePickLibraryRoot() {
    const picked = await librarySettings.pickLibraryRoot();
    return picked?.libraryRoot ?? null;
  }

  async function handlePickOutputRoot() {
    const picked = await librarySettings.pickOutputRoot();
    return picked?.libraryRoot ?? null;
  }

  function handleRescan() {
    cleanLibrary.clearError();
    librarySettings.clearError();
    setRefreshKey((value) => value + 1);
  }

  function serializeOverrides(overrides: AlbumOverrideMap): AlbumMetadataOverride[] {
    return Object.entries(overrides).flatMap(([albumId, values]) => {
      const cleaned = cleanAlbumOverride(values);
      return Object.keys(cleaned).length > 0 ? [{ albumId, ...cleaned }] : [];
    });
  }

  async function handleClean() {
    const result = await cleanLibrary.run(serializeOverrides(stagedOverrides));
    if (!result) {
      return;
    }
  }

  function handleReset() {
    if (Object.keys(stagedOverrides).length > 0) {
      const confirmed = window.confirm(t("import.resetConfirm"));
      if (!confirmed) {
        return;
      }
    }

    devLog(developerMode, "Resetting import workspace state");
    setSelectedAlbumId(null);
    setSelectionLockedEmpty(true);
    setAlbumSearch("");
    setAlbumFilters(defaultAlbumFilters);
    setTrackIssueFilter("all");
    setMetricFilter(null);
    setSelectedTrackIds(new Set());
    setBulkDraft(emptyBulkDraft);
    setBulkEditOpen(false);
    setLogDialogOpen(false);
    setStagedOverrides({});
    cleanLibrary.clearError();
    librarySettings.clearError();
  }

  function handleAlbumSelect(albumId: string) {
    setSelectionLockedEmpty(false);
    setSelectedAlbumId(albumId);
  }

  function handleFiltersChange(nextFilters: AlbumFilterState) {
    setAlbumFilters(nextFilters);
    devLog(developerMode, `Filter state changed: ${JSON.stringify(nextFilters)}`);
  }

  function handleToggleTrack(trackId: string) {
    setSelectedTrackIds((current) => {
      const next = new Set(current);
      if (next.has(trackId)) {
        next.delete(trackId);
      } else {
        next.add(trackId);
      }
      return next;
    });
  }

  function handleClearTrackSelection() {
    setSelectedTrackIds(new Set());
  }

  function handleDismissInspector() {
    setSelectedAlbumId(null);
    setSelectionLockedEmpty(true);
  }

  function commitAlbumOverride(albumId: string, changes: Partial<AlbumOverrideValues>) {
    setStagedOverrides((current) => {
      const next = { ...(current[albumId] ?? {}), ...changes };
      const cleaned = cleanAlbumOverride(next);
      if (Object.keys(cleaned).length === 0) {
        const { [albumId]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [albumId]: cleaned };
    });
  }

  function handleSaveInspectorOverride(changes: Partial<EditableInspectorFields>) {
    if (!effectiveSelectedAlbumId) {
      return;
    }
    commitAlbumOverride(effectiveSelectedAlbumId, changes);
  }

  function handleRevertInspectorOverride() {
    if (!effectiveSelectedAlbumId) {
      return;
    }
    setStagedOverrides((current) => {
      const { [effectiveSelectedAlbumId]: _removed, ...rest } = current;
      return rest;
    });
  }

  const bulkAffectedAlbums = albums;
  const workspaceGridColumns = "minmax(280px,0.95fr) minmax(0,1.55fr) minmax(300px,0.9fr)";

  function handleApplyBulkEdits() {
    devLog(developerMode, "Applying staged metadata edits", { affectedAlbums: bulkAffectedAlbums.length });
    const changes = cleanAlbumOverride(bulkDraft);
    if (Object.keys(changes).length === 0) {
      setBulkEditOpen(false);
      setBulkDraft(emptyBulkDraft);
      return;
    }
    setStagedOverrides((current) => {
      const next = { ...current };
      for (const album of bulkAffectedAlbums) {
        next[album.id] = cleanAlbumOverride({ ...(next[album.id] ?? {}), ...changes });
      }
      return next;
    });
    setBulkEditOpen(false);
    setBulkDraft(emptyBulkDraft);
  }

  function handleDiscardBulkEdits() {
    devLog(developerMode, "Discarded staged metadata edits");
    setBulkEditOpen(false);
    setBulkDraft(emptyBulkDraft);
  }

  return (
    <>
      <AppShell
        header={
          <AppHeader
            libraryPath={libraryPath}
            libraryStatusLabel={
              noLibrarySelected ? t("import.noLibrarySelected") : disconnectedLibrary ? t("common.disconnected") : t("common.connected")
            }
            libraryStatusTone={noLibrarySelected ? "neutral" : disconnectedLibrary ? "warning" : "success"}
            onOpenLibraryPicker={() => setPickerOpen(true)}
            onRescan={handleRescan}
            onClean={handleClean}
            onReset={handleReset}
            cleaning={cleanLibrary.loading}
            cleanDisabled={noLibrarySelected || disconnectedLibrary}
            summary={summary}
          />
        }
        sidebar={
          <AppSidebar
            activePage={activePage}
            onNavigate={onNavigate}
            statusLabel={sidebarStatus}
          />
        }
      >
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <div
            className="grid min-h-0 flex-1 gap-4 xl:min-h-[740px] xl:items-stretch xl:[grid-template-columns:var(--workspace-columns)]"
            style={{ ["--workspace-columns" as string]: workspaceGridColumns }}
          >
            <div className="flex min-h-0 min-w-0 flex-col">
              {noLibrarySelected || disconnectedLibrary ? (
                <Panel className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center text-[13px] text-muted-foreground">
                  <p>{blockerMessage}</p>
                  <button
                    className="app-button-primary rounded-2xl px-4 py-2"
                    type="button"
                    onClick={() => setPickerOpen(true)}
                  >
                    {t("import.chooseFolder")}
                  </button>
                </Panel>
              ) : albumsError ? (
                <Panel className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
                  {t("import.failedAlbums")}
                </Panel>
              ) : (
                <AlbumList
                  albums={albums}
                  search={albumSearch}
                  filters={albumFilters}
                  onSearchChange={setAlbumSearch}
                  onFiltersChange={handleFiltersChange}
                  onSelect={handleAlbumSelect}
                />
              )}
            </div>

            <div className="flex min-h-0 min-w-0 flex-col">
              {noLibrarySelected || disconnectedLibrary ? (
                <Panel className="flex h-full items-center justify-center px-8 text-center text-[13px] text-muted-foreground">
                  {t("import.blockerConnected")}
                </Panel>
              ) : detailError ? (
                <Panel className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
                  {t("import.failedTracks")}
                </Panel>
              ) : (
                <TrackTable
                  artist={visibleInspector.artist}
                  title={detailLoading ? t("import.loadingAlbum") : visibleInspector.title}
                  tracks={filteredTracks}
                  year={visibleInspector.year}
                  selectedTrackIds={selectedTrackIds}
                  trackIssueFilter={trackIssueFilter}
                  onToggleTrack={handleToggleTrack}
                  onClearSelection={handleClearTrackSelection}
                  onTrackIssueFilterChange={setTrackIssueFilter}
                  onOpenBulkEdit={() => {
                    devLog(developerMode, "Bulk edit started", { affectedAlbums: bulkAffectedAlbums.length });
                    setBulkEditOpen(true);
                  }}
                />
              )}
            </div>

            <div className="flex min-h-0 min-w-0 flex-col">
              {effectiveSelectedAlbumId ? (
                detailError ? (
                  <Panel className="flex h-full items-center justify-center text-[13px] text-muted-foreground">
                    {t("import.failedInspector")}
                  </Panel>
                ) : (
                  <AlbumInspector
                    inspector={visibleInspector}
                    tracks={tracks}
                    relatedReleases={relatedReleasesData}
                    relatedReleasesLoading={relatedReleasesLoading}
                    actions={actionsData}
                    actionsLoading={actionsLoading}
                    stagedOverride={inspectorOverride}
                    activeMetricFilter={metricFilter}
                    onDismiss={handleDismissInspector}
                    onMetricFilterChange={setMetricFilter}
                    onSaveOverride={handleSaveInspectorOverride}
                    onRevertOverride={handleRevertInspectorOverride}
                    onRunCleanup={handleClean}
                    cleanupRunning={cleanLibrary.loading}
                    developerMode={developerMode}
                  />
                )
              ) : (
                <Panel className="flex h-full items-center justify-center text-center text-[13px] text-muted-foreground">
                  {t("import.emptyInspector.title")}
                </Panel>
              )}
            </div>
          </div>

          <div className="h-[280px] shrink-0">
            <LogPanel
              developerMode={developerMode}
              open={logDialogOpen}
              onOpen={() => setLogDialogOpen(true)}
              onClose={() => setLogDialogOpen(false)}
            />
          </div>
        </div>
      </AppShell>

      <LibraryPickerDialog
        open={pickerOpen}
        libraryPath={libraryState?.libraryRoot ?? ""}
        outputPath={libraryState?.outputRoot ?? ""}
        isAvailable={libraryState?.isAvailable ?? false}
        isConfigured={libraryState?.isConfigured ?? false}
        error={libraryState?.error ?? librarySettings.error ?? cleanLibrary.error}
        pickerAvailable={libraryState?.pickerAvailable ?? false}
        busy={librarySettings.saving || librarySettings.picking || cleanLibrary.loading}
        onClose={() => setPickerOpen(false)}
        onPickLibrary={handlePickLibraryRoot}
        onPickOutput={handlePickOutputRoot}
        onSave={handleSaveLibraryRoot}
      />

      {bulkEditOpen ? (
        <BulkEditModal
          affectedAlbumCount={bulkAffectedAlbums.length}
          draft={bulkDraft}
          onDraftChange={setBulkDraft}
          onApply={handleApplyBulkEdits}
          onDiscard={handleDiscardBulkEdits}
        />
      ) : null}
    </>
  );
}

function BulkEditModal({
  affectedAlbumCount,
  draft,
  onDraftChange,
  onApply,
  onDiscard,
}: {
  affectedAlbumCount: number;
  draft: BulkEditDraft;
  onDraftChange: (draft: BulkEditDraft) => void;
  onApply: () => void;
  onDiscard: () => void;
}) {
  const { t } = useI18n();
  const changedFields = Object.entries(cleanAlbumOverride(draft));
  const helpTexts = {
    compilation: t("import.bulk.help.compilation"),
    explicit: t("import.bulk.help.explicit"),
    capitalizationMode: t("import.bulk.help.capitalizationMode"),
    normalizeFeaturingArtists: t("import.bulk.help.normalizeFeaturingArtists"),
    overwriteExistingTags: t("import.bulk.help.overwriteExistingTags"),
    metadataProvider: t("import.bulk.help.metadataProvider"),
    yearSource: t("import.bulk.help.yearSource"),
    coverHandlingMode: t("import.bulk.help.coverHandlingMode"),
  } as const;
  const fieldLabels = {
    albumTitle: t("import.bulk.fields.albumTitle"),
    albumArtist: t("import.bulk.fields.albumArtist"),
    genre: t("import.bulk.fields.genre"),
    year: t("import.bulk.fields.year"),
    disc: t("import.bulk.fields.disc"),
    discTotal: t("import.bulk.fields.discTotal"),
    compilation: t("import.bulk.fields.compilation"),
    explicit: t("import.bulk.fields.explicit"),
    capitalizationMode: t("import.bulk.fields.capitalizationMode"),
    normalizeFeaturingArtists: t("import.bulk.fields.normalizeFeaturingArtists"),
    overwriteExistingTags: t("import.bulk.fields.overwriteExistingTags"),
    metadataProvider: t("import.bulk.fields.metadataProvider"),
    yearSource: t("import.bulk.fields.yearSource"),
    coverHandlingMode: t("import.bulk.fields.coverHandlingMode"),
  } as const;
  return (
    <div className="app-modal-overlay fixed inset-0 z-50 flex items-center justify-center px-4 py-6">
      <Panel className="app-modal-panel flex h-[min(86vh,920px)] w-full max-w-[760px] min-h-0 flex-col p-0">
        <div className="flex items-center justify-between border-b border-border-soft/75 px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">{t("import.bulk.title")}</h2>
            <p className="mt-1 text-[12px] text-muted-foreground">{t("import.bulk.subtitle", { count: affectedAlbumCount })}</p>
          </div>
          <button
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-surface-subtle/75 hover:text-[hsl(var(--text-strong))]"
            type="button"
            onClick={onDiscard}
          >
            ×
          </button>
        </div>
        <div className="grid min-h-0 flex-1 gap-3 overflow-y-auto px-5 py-5 md:grid-cols-2 content-start">
          <BulkField label={t("import.bulk.fields.albumTitle")} value={draft.albumTitle} onChange={(value) => onDraftChange({ ...draft, albumTitle: value })} />
          <BulkField label={t("import.bulk.fields.albumArtist")} value={draft.albumArtist} onChange={(value) => onDraftChange({ ...draft, albumArtist: value })} />
          <BulkField label={t("import.bulk.fields.genre")} value={draft.genre} onChange={(value) => onDraftChange({ ...draft, genre: value })} />
          <BulkField label={t("import.bulk.fields.year")} value={draft.year} onChange={(value) => onDraftChange({ ...draft, year: value })} />
          <BulkField label={t("import.bulk.fields.disc")} value={draft.disc} onChange={(value) => onDraftChange({ ...draft, disc: value })} />
          <BulkField label={t("import.bulk.fields.discTotal")} value={draft.discTotal} onChange={(value) => onDraftChange({ ...draft, discTotal: value })} />
          <BulkSelect
            label={t("import.bulk.fields.compilation")}
            helpText={helpTexts.compilation}
            value={draft.compilation}
            onChange={(value) => onDraftChange({ ...draft, compilation: value as AlbumCompilationOverride })}
            options={[
              { value: "auto", label: t("import.bulk.options.auto") },
              { value: "true", label: t("import.bulk.options.true") },
              { value: "false", label: t("import.bulk.options.false") },
            ]}
          />
          <BulkSelect
            label={t("import.bulk.fields.explicit")}
            helpText={helpTexts.explicit}
            value={draft.explicit}
            onChange={(value) => onDraftChange({ ...draft, explicit: value as AlbumExplicitOverride })}
            options={[
              { value: "auto", label: t("import.bulk.options.auto") },
              { value: "true", label: t("import.bulk.options.true") },
              { value: "false", label: t("import.bulk.options.false") },
            ]}
          />
          <BulkSelect
            label={t("import.bulk.fields.capitalizationMode")}
            helpText={helpTexts.capitalizationMode}
            value={draft.capitalizationMode}
            onChange={(value) => onDraftChange({ ...draft, capitalizationMode: value as CapitalizationMode })}
            options={[
              { value: "none", label: t("import.bulk.options.none") },
              { value: "title_case", label: t("import.bulk.options.titleCase") },
              { value: "sentence_case", label: t("import.bulk.options.sentenceCase") },
              { value: "upper", label: t("import.bulk.options.upper") },
              { value: "lower", label: t("import.bulk.options.lower") },
            ]}
          />
          <BulkSelect
            label={t("import.bulk.fields.metadataProvider")}
            helpText={helpTexts.metadataProvider}
            value={draft.metadataProvider}
            onChange={(value) => onDraftChange({ ...draft, metadataProvider: value as MetadataProviderOverride })}
            options={[
              { value: "auto", label: t("import.bulk.options.auto") },
              { value: "deezer", label: "Deezer" },
              { value: "musicbrainz", label: "MusicBrainz" },
            ]}
          />
          <BulkSelect
            label={t("import.bulk.fields.yearSource")}
            helpText={helpTexts.yearSource}
            value={draft.yearSource}
            onChange={(value) => onDraftChange({ ...draft, yearSource: value as YearSourceOverride })}
            options={[
              { value: "auto", label: t("import.bulk.options.auto") },
              { value: "local_tags", label: t("import.bulk.options.localTags") },
              { value: "deezer", label: "Deezer" },
              { value: "musicbrainz", label: "MusicBrainz" },
            ]}
          />
          <BulkSelect
            label={t("import.bulk.fields.coverHandlingMode")}
            helpText={helpTexts.coverHandlingMode}
            value={draft.coverHandlingMode}
            onChange={(value) => onDraftChange({ ...draft, coverHandlingMode: value as CoverHandlingMode })}
            options={[
              { value: "auto", label: t("import.bulk.options.auto") },
              { value: "keep_existing", label: t("import.bulk.options.keepExisting") },
              { value: "force_deezer", label: t("import.bulk.options.forceDeezer") },
              { value: "force_musicbrainz", label: t("import.bulk.options.forceMusicBrainz") },
              { value: "remove", label: t("import.bulk.options.remove") },
            ]}
          />
          <BulkCheckbox
            label={t("import.bulk.fields.normalizeFeaturingArtists")}
            helpText={helpTexts.normalizeFeaturingArtists}
            checked={draft.normalizeFeaturingArtists}
            onChange={(checked) => onDraftChange({ ...draft, normalizeFeaturingArtists: checked })}
          />
          <BulkCheckbox
            label={t("import.bulk.fields.overwriteExistingTags")}
            helpText={helpTexts.overwriteExistingTags}
            checked={draft.overwriteExistingTags}
            onChange={(checked) => onDraftChange({ ...draft, overwriteExistingTags: checked })}
          />
        </div>
        <div className="border-t border-border-soft/75 px-5 py-4">
          <p className="text-[12px] font-medium text-[hsl(var(--text-strong))]">{t("import.bulk.preview")}</p>
          <div className="mt-2 text-[12px] text-muted-foreground">
            {changedFields.length === 0 ? t("import.bulk.emptyPreview") : changedFields.map(([key, value]) => (
              <p key={key}>• {fieldLabels[key as keyof typeof fieldLabels]}: {typeof value === "boolean" ? t("settings.enabled") : String(value)}</p>
            ))}
          </div>
          <div className="mt-4 flex gap-2">
            <button
              className="app-button-primary rounded-2xl px-4 py-2 text-[12px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-60"
              type="button"
              disabled={changedFields.length === 0 || affectedAlbumCount === 0}
              onClick={onApply}
            >
              {t("import.bulk.apply")}
            </button>
            <button
              className="app-button-secondary rounded-2xl px-4 py-2 text-[12px]"
              type="button"
              onClick={onDiscard}
            >
              {t("import.bulk.discard")}
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function BulkField({
  label,
  value,
  onChange,
  helpText,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  helpText?: string | undefined;
}) {
  return (
    <label className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3">
      <BulkFieldLabel label={label} helpText={helpText} />
      <input
        className="mt-2 w-full bg-transparent text-[13px] text-[hsl(var(--text-base))] outline-none"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function BulkSelect({
  label,
  helpText,
  value,
  onChange,
  options,
}: {
  label: string;
  helpText?: string | undefined;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3">
      <BulkFieldLabel label={label} helpText={helpText} />
      <select
        className="app-control mt-2 w-full rounded-xl px-3 py-2 text-[13px]"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

function BulkCheckbox({
  label,
  helpText,
  checked,
  onChange,
}: {
  label: string;
  helpText?: string | undefined;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3 text-[13px] text-[hsl(var(--text-base))]">
      <BulkFieldLabel label={label} helpText={helpText} />
      <input checked={checked} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}
