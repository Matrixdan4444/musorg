import {
  getAlbumDetail,
  getAlbumTracks,
  getAlbums,
  getRunAlbumDetail,
  getRunAlbumTracks,
  getRunAlbums,
} from "@/lib/api/music";
import { devLog } from "@/lib/dev-log";
import { logStreamStore } from "@/lib/log-stream-store";
import type {
  AlbumDetailPayload,
  AlbumInspectorData,
  AlbumListItem,
  AlbumsPayload,
  LogEntry,
  TrackRow,
  TracksPayload,
  WorkspaceSourceMode,
} from "@/types/music";

type Listener = () => void;

interface AlbumDetailState {
  inspector: AlbumInspectorData | null;
  tracks: TrackRow[];
}

type WorkspaceAlbumSourceKind = "raw" | "runtime_processed" | "run_output";

interface WorkspaceAlbumSource {
  kind: WorkspaceAlbumSourceKind;
  runId: string | null;
}

interface WorkspaceRuntimeState {
  libraryPath: string;
  sourceMode: WorkspaceSourceMode;
  displayRunId: string | null;
  outputRoot: string | null;
  albumOrder: string[];
  albumsById: Record<string, AlbumListItem>;
  baseAlbumsById: Record<string, AlbumListItem>;
  detailsById: Record<string, AlbumDetailState>;
  baseDetailsById: Record<string, AlbumDetailState>;
  sourcesById: Record<string, WorkspaceAlbumSource>;
  detailVersions: Record<string, number>;
  albumsVersion: number;
  activeRunId: string | null;
}

interface AlbumsSnapshot {
  libraryPath: string;
  albumOrder: string[];
  albumsById: Record<string, AlbumListItem>;
  albumsVersion: number;
}

const initialState: WorkspaceRuntimeState = {
  libraryPath: "",
  sourceMode: "input",
  displayRunId: null,
  outputRoot: null,
  albumOrder: [],
  albumsById: {},
  baseAlbumsById: {},
  detailsById: {},
  baseDetailsById: {},
  sourcesById: {},
  detailVersions: {},
  albumsVersion: 0,
  activeRunId: null,
};

const EMPTY_DETAIL_STATE: AlbumDetailState = { inspector: null, tracks: [] };

function defaultDetailState(): AlbumDetailState {
  return EMPTY_DETAIL_STATE;
}

function cloneDetailState(detail: AlbumDetailState): AlbumDetailState {
  return {
    inspector: detail.inspector ? { ...detail.inspector } : null,
    tracks: [...detail.tracks],
  };
}

function clearRuntimeAlbumFields(album: AlbumListItem): AlbumListItem {
  return {
    ...album,
    processingState: "idle",
    outputPath: null,
    provider: null,
    releaseType: null,
    confidenceLevel: null,
    lowConfidence: false,
    metadataIntelligence: null,
    topAction: null,
    actionSummary: [],
    actionCount: 0,
  };
}

function clearRuntimeInspectorFields(inspector: AlbumInspectorData): AlbumInspectorData {
  return {
    ...inspector,
    processingState: "idle",
    outputPath: null,
    provider: null,
    confidenceLevel: null,
    lowConfidence: false,
    metadataIntelligence: null,
    topAction: null,
    actionSummary: [],
    actionCount: 0,
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function asAlbumListItem(value: unknown): AlbumListItem | null {
  const record = asRecord(value);
  if (!record || typeof record.id !== "string") {
    return null;
  }
  return record as unknown as AlbumListItem;
}

function asInspector(value: unknown): AlbumInspectorData | null {
  const record = asRecord(value);
  if (!record || typeof record.id !== "string") {
    return null;
  }
  return record as unknown as AlbumInspectorData;
}

function asTrackRows(value: unknown): TrackRow[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  return value.filter((row): row is TrackRow => Boolean(asRecord(row)?.id));
}

function resolvedSourceKind(
  album: AlbumListItem | undefined,
  sourceMode: WorkspaceSourceMode,
): WorkspaceAlbumSourceKind {
  if (!album) {
    return sourceMode === "output" ? "run_output" : "raw";
  }
  if (sourceMode === "output") {
    return "run_output";
  }
  return album.processingState === "completed" && album.outputPath ? "runtime_processed" : "raw";
}

function mergeAlbumIntoInspector(
  current: AlbumInspectorData | null,
  album: Partial<AlbumListItem> & { id: string },
): AlbumInspectorData | null {
  if (!current) {
    return null;
  }

  const warningCount = album.issueCounts?.warning ?? null;
  const dangerCount = album.issueCounts?.danger ?? null;
  const successCount = album.issueCounts?.success ?? null;

  return {
    ...current,
    id: album.id,
    title: album.title ?? current.title,
    artist: album.artist ?? current.artist,
    year: album.year ?? current.year,
    coverUrl: album.coverUrl ?? current.coverUrl,
    processingState: album.processingState ?? current.processingState ?? null,
    outputPath: album.outputPath ?? current.outputPath ?? null,
    provider: album.provider ?? current.provider ?? null,
    confidenceLevel: album.confidenceLevel ?? current.confidenceLevel ?? null,
    lowConfidence: album.lowConfidence ?? current.lowConfidence ?? false,
    metadataIntelligence: album.metadataIntelligence ?? current.metadataIntelligence ?? null,
    topAction: album.topAction ?? current.topAction ?? null,
    actionSummary: album.actionSummary ?? current.actionSummary ?? [],
    actionCount: album.actionCount ?? current.actionCount ?? 0,
    issues: current.issues,
    metrics: current.metrics.map((metric) => {
      if (metric.id === "danger" && dangerCount !== null) {
        return { ...metric, value: String(dangerCount) };
      }
      if (metric.id === "warning" && warningCount !== null) {
        return { ...metric, value: String(warningCount) };
      }
      if (metric.id === "success" && successCount !== null) {
        return { ...metric, value: String(successCount) };
      }
      return metric;
    }),
  };
}

class WorkspaceRuntimeStore {
  private state: WorkspaceRuntimeState = initialState;
  private albumsSnapshot: AlbumsSnapshot = {
    libraryPath: initialState.libraryPath,
    albumOrder: initialState.albumOrder,
    albumsById: initialState.albumsById,
    albumsVersion: initialState.albumsVersion,
  };
  private listeners = new Set<Listener>();
  private albumListeners = new Set<Listener>();
  private detailListenersByAlbum = new Map<string, Set<Listener>>();
  private liveSubscribed = false;
  private developerMode = false;

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  subscribeAlbums = (listener: Listener) => {
    this.albumListeners.add(listener);
    return () => this.albumListeners.delete(listener);
  };

  subscribeAlbumDetail = (albumId: string, listener: Listener) => {
    const listeners = this.detailListenersByAlbum.get(albumId) ?? new Set<Listener>();
    listeners.add(listener);
    this.detailListenersByAlbum.set(albumId, listeners);
    return () => {
      const current = this.detailListenersByAlbum.get(albumId);
      if (!current) {
        return;
      }
      current.delete(listener);
      if (current.size === 0) {
        this.detailListenersByAlbum.delete(albumId);
      }
    };
  };

  getSnapshot = () => this.state;
  getAlbumsSnapshot = () => this.albumsSnapshot;
  getAlbumDetailSnapshot = (albumId: string | null) => {
    if (!albumId) {
      return EMPTY_DETAIL_STATE;
    }
    return this.state.detailsById[albumId] ?? defaultDetailState();
  };

  async ensureConnected(developerMode: boolean) {
    this.developerMode = developerMode;
    await logStreamStore.ensureConnected(developerMode);
    if (this.liveSubscribed) {
      return;
    }
    this.liveSubscribed = true;
    logStreamStore.subscribeToEvents((event) => {
      this.applyRuntimeEvent(event);
    });
  }

  async bootstrapAlbums() {
    const payload = await getAlbums();
    this.hydrateAlbums(payload, { sourceMode: "input", displayRunId: null, outputRoot: null, resetDetails: true });
    return payload;
  }

  async bootstrapAlbumDetail(albumId: string) {
    const { displayRunId, sourceMode } = this.state;
    const current = this.state.detailsById[albumId] ?? defaultDetailState();
    const source = this.state.sourcesById[albumId];
    const keepProcessedDetail = sourceMode === "input"
      && source?.kind === "runtime_processed"
      && Boolean(this.state.activeRunId)
      && Boolean(current.inspector);

    if (keepProcessedDetail) {
      return current;
    }

    const [detailPayload, tracksPayload] = sourceMode === "output" && displayRunId
      ? await Promise.all([
        getRunAlbumDetail(displayRunId, albumId),
        getRunAlbumTracks(displayRunId, albumId),
      ])
      : await Promise.all([
        getAlbumDetail(albumId),
        getAlbumTracks(albumId),
      ]);
    this.hydrateAlbumDetail(albumId, detailPayload, tracksPayload);
    return {
      inspector: detailPayload.album,
      tracks: tracksPayload.tracks,
    };
  }

  private async bootstrapRunOutput(runId: string, outputRoot: string | null) {
    const payload = await getRunAlbums(runId);
    this.hydrateAlbums(payload, {
      sourceMode: "output",
      displayRunId: runId,
      outputRoot: outputRoot ?? payload.libraryPath,
      resetDetails: true,
    });
  }

  hydrateAlbums(
    payload: AlbumsPayload,
    options?: {
      sourceMode?: WorkspaceSourceMode;
      displayRunId?: string | null;
      outputRoot?: string | null;
      resetDetails?: boolean;
    },
  ) {
    const nextSourceMode = options?.sourceMode ?? this.state.sourceMode;
    const previousDetailIds = new Set(Object.keys(this.state.detailsById));
    const nextAlbumsById: Record<string, AlbumListItem> = {};
    const nextBaseAlbumsById: Record<string, AlbumListItem> = nextSourceMode === "input" ? {} : { ...this.state.baseAlbumsById };
    const nextDetailsById: Record<string, AlbumDetailState> = {};
    const nextBaseDetailsById: Record<string, AlbumDetailState> = nextSourceMode === "input" ? {} : { ...this.state.baseDetailsById };
    const nextDetailVersions: Record<string, number> = {};
    const nextSourcesById: Record<string, WorkspaceAlbumSource> = {};
    const nextOrder: string[] = [];

    for (const album of payload.albums) {
      nextOrder.push(album.id);
      const existingSource = this.state.sourcesById[album.id];
      const baseAlbum = nextSourceMode === "input" ? clearRuntimeAlbumFields(album) : album;
      if (nextSourceMode === "input") {
        nextBaseAlbumsById[album.id] = baseAlbum;
      }
      const nextAlbum = {
        ...album,
        processingState: album.processingState ?? null,
        outputPath: album.outputPath ?? null,
        provider: album.provider ?? null,
        releaseType: album.releaseType ?? null,
        confidenceLevel: album.confidenceLevel ?? null,
        lowConfidence: album.lowConfidence ?? false,
        metadataIntelligence: album.metadataIntelligence ?? null,
        topAction: album.topAction ?? null,
        actionSummary: album.actionSummary ?? [],
        actionCount: album.actionCount ?? 0,
      };
      nextAlbumsById[album.id] = nextAlbum;
      nextSourcesById[album.id] = {
        kind: resolvedSourceKind(nextAlbum, nextSourceMode),
        runId: nextSourceMode === "output"
          ? options?.displayRunId ?? this.state.displayRunId
          : null,
      };

      if (nextSourceMode !== "input") {
        continue;
      }

      const baseDetail = this.state.baseDetailsById[album.id];
      if (baseDetail && nextAlbum.processingState !== "completed") {
        const nextDetail = {
          inspector: mergeAlbumIntoInspector(baseDetail.inspector, nextAlbum),
          tracks: baseDetail.tracks,
        };
        nextDetailsById[album.id] = nextDetail;
        nextBaseDetailsById[album.id] = cloneDetailState(baseDetail);
        nextDetailVersions[album.id] = (this.state.detailVersions[album.id] ?? 0) + 1;
      } else if (this.state.detailsById[album.id]?.inspector && existingSource?.kind === "raw" && nextAlbum.processingState !== "completed") {
        const currentDetail = this.state.detailsById[album.id]!;
        const currentInspector = currentDetail.inspector!;
        nextDetailsById[album.id] = {
          inspector: mergeAlbumIntoInspector(clearRuntimeInspectorFields(currentInspector), nextAlbum),
          tracks: currentDetail.tracks,
        };
        nextBaseDetailsById[album.id] = cloneDetailState({
          inspector: clearRuntimeInspectorFields(currentInspector),
          tracks: currentDetail.tracks,
        });
        nextDetailVersions[album.id] = (this.state.detailVersions[album.id] ?? 0) + 1;
      }
    }

    this.state = {
      ...this.state,
      libraryPath: payload.libraryPath,
      sourceMode: options?.sourceMode ?? this.state.sourceMode,
      displayRunId: options?.displayRunId ?? this.state.displayRunId,
      outputRoot: options?.outputRoot ?? this.state.outputRoot,
      albumOrder: nextOrder,
      albumsById: nextAlbumsById,
      baseAlbumsById: nextBaseAlbumsById,
      detailsById: nextDetailsById,
      baseDetailsById: nextBaseDetailsById,
      sourcesById: nextSourcesById,
      detailVersions: nextDetailVersions,
      albumsVersion: this.state.albumsVersion + 1,
    };
    this.refreshAlbumsSnapshot();
    this.emitAlbums();
    for (const albumId of new Set([...previousDetailIds, ...Object.keys(nextDetailsById)])) {
      this.emitAlbumDetail(albumId);
    }
    this.emitAll();
  }

  hydrateAlbumDetail(albumId: string, detailPayload: AlbumDetailPayload, tracksPayload: TracksPayload) {
    const current = this.state.detailsById[albumId] ?? defaultDetailState();
    const currentSource = this.state.sourcesById[albumId];
    const rawDetailState = {
      inspector: clearRuntimeInspectorFields(detailPayload.album),
      tracks: tracksPayload.tracks,
    };
    const preserveProcessedDetail = this.state.sourceMode === "input"
      && currentSource?.kind === "runtime_processed"
      && Boolean(this.state.activeRunId);
    const preserveRunOutputDetail = this.state.sourceMode === "output" && currentSource?.kind === "run_output";
    const nextDetailState = preserveProcessedDetail || preserveRunOutputDetail
      ? {
        inspector: current.inspector ?? detailPayload.album,
        tracks: current.tracks.length ? current.tracks : tracksPayload.tracks,
      }
      : {
        inspector: detailPayload.album,
        tracks: tracksPayload.tracks,
      };
    this.state = {
      ...this.state,
      detailsById: {
        ...this.state.detailsById,
        [albumId]: nextDetailState,
      },
      baseDetailsById: this.state.sourceMode === "input"
        ? {
          ...this.state.baseDetailsById,
          [albumId]: rawDetailState,
        }
        : this.state.baseDetailsById,
      sourcesById: (!currentSource || currentSource.kind === "raw" || detailPayload.album.processingState === "missing_output")
        || !this.state.activeRunId
        ? {
          ...this.state.sourcesById,
          [albumId]: {
            kind: resolvedSourceKind(this.state.albumsById[albumId], this.state.sourceMode),
            runId: this.state.sourceMode === "output" ? this.state.displayRunId : null,
          },
        }
        : this.state.sourcesById,
      detailVersions: {
        ...this.state.detailVersions,
        [albumId]: (this.state.detailVersions[albumId] ?? 0) + 1,
      },
    };
    this.emitAlbumDetail(albumId);
    this.emitAll();
  }

  private applyRuntimeEvent(event: LogEntry) {
    const payload = asRecord(event.payload);
    let changed = false;
    devLog(this.developerMode, "Frontend applying runtime update", {
      type: event.type,
      albumId: event.albumId,
      runId: event.runId,
    });

    if (event.type === "run_started") {
      this.resetActiveRun(event.runId ?? null);
      changed = true;
    } else if (event.runId && this.state.activeRunId && event.runId !== this.state.activeRunId) {
      return;
    } else if (event.type === "pipeline_completed" || event.type === "run_completed") {
      this.state = { ...this.state, activeRunId: null };
      changed = this.finishActiveRun("completed") || changed;
    } else if (event.type === "run_failed") {
      this.state = { ...this.state, activeRunId: null };
      changed = this.finishActiveRun("failed") || changed;
    } else if (!this.state.activeRunId && event.type !== "output_ready") {
      return;
    }

    if (event.type === "stage_started" && event.stage === "scan_stage") {
      changed = this.setAllAlbumProcessingStates("scanning") || changed;
    }

    if (event.type === "output_ready" && event.runId) {
      const outputRoot = typeof payload?.outputRoot === "string" ? payload.outputRoot : null;
      this.state = { ...this.state, outputRoot };
      changed = true;
    }

    if (event.type === "pipeline_completed" || event.type === "run_completed") {
      if (this.state.sourceMode !== "output") {
        if (changed) {
          this.emitAll();
        }
        return;
      }
      const albums = Array.isArray(payload?.albums) ? payload.albums : [];
      for (const albumPayload of albums) {
        changed = this.applyAlbumPayload(asRecord(albumPayload)) || changed;
      }
      if (changed) {
        this.emitAll();
      }
      return;
    }

    if (this.state.sourceMode === "output") {
      if (changed) {
        this.emitAll();
      }
      return;
    }

    if (payload) {
      changed = this.applyAlbumPayload(payload) || changed;
    } else if (event.albumId) {
      changed = this.patchAlbum(event.albumId, {
        processingState: this.progressFromEvent(event),
      }) || changed;
    }

    if (changed) {
      this.emitAll();
    }
  }

  private applyAlbumPayload(payload: Record<string, unknown> | null) {
    if (!payload) {
      return false;
    }
    const fallbackAlbumId = typeof payload.albumId === "string" ? payload.albumId : null;
    const albumPatch = asAlbumListItem(payload.processedAlbum) ?? asAlbumListItem(payload.albumPatch);
    const albumId = albumPatch?.id ?? fallbackAlbumId;
    if (!albumId) {
      return false;
    }

    let changed = false;
    if (albumPatch) {
      changed = this.patchAlbum(albumId, albumPatch, {
        kind: this.state.sourceMode === "output" ? "run_output" : "runtime_processed",
        runId: this.state.activeRunId,
      }) || changed;
    } else {
      changed = this.patchAlbum(albumId, {
        processingState: typeof payload.progress === "string" ? payload.progress : null,
      }, {
        kind: this.state.sourceMode === "output" ? "run_output" : "runtime_processed",
        runId: this.state.activeRunId,
      }) || changed;
    }

    const inspectorPatch = asInspector(payload.inspectorPatch);
    const tracksPatch = asTrackRows(payload.tracksPatch);
    if (inspectorPatch || tracksPatch) {
      const current = this.state.detailsById[albumId] ?? defaultDetailState();
      const mergedInspector = inspectorPatch
        ? { ...(current.inspector ?? {}), ...inspectorPatch }
        : current.inspector;
      this.state = {
        ...this.state,
        detailsById: {
          ...this.state.detailsById,
          [albumId]: {
            inspector: mergedInspector,
            tracks: tracksPatch ?? current.tracks,
          },
        },
        sourcesById: {
          ...this.state.sourcesById,
          [albumId]: {
            kind: this.state.sourceMode === "output" ? "run_output" : "runtime_processed",
            runId: this.state.activeRunId,
          },
        },
        detailVersions: {
          ...this.state.detailVersions,
          [albumId]: (this.state.detailVersions[albumId] ?? 0) + 1,
        },
      };
      this.emitAlbumDetail(albumId);
      changed = true;
    }
    return changed;
  }

  private patchAlbum(
    albumId: string,
    patch: Partial<AlbumListItem>,
    source?: WorkspaceAlbumSource,
  ) {
    const current = this.state.albumsById[albumId];
    if (!current && !patch.id) {
      return false;
    }
    const nextAlbum = {
      ...current,
      ...patch,
      id: albumId,
    } as AlbumListItem;
    if (current && shallowAlbumEqual(current, nextAlbum)) {
      return false;
    }
    const nextOrder = current || this.state.albumOrder.includes(albumId)
      ? this.state.albumOrder
      : [...this.state.albumOrder, albumId];
    this.state = {
      ...this.state,
      albumOrder: nextOrder,
      albumsById: {
        ...this.state.albumsById,
        [albumId]: nextAlbum,
      },
      detailsById: {
        ...this.state.detailsById,
        ...(this.state.detailsById[albumId]
          ? {
            [albumId]: {
              inspector: mergeAlbumIntoInspector(this.state.detailsById[albumId]?.inspector ?? null, nextAlbum),
              tracks: this.state.detailsById[albumId]?.tracks ?? [],
            },
          }
          : {}),
      },
      sourcesById: source
        ? {
          ...this.state.sourcesById,
          [albumId]: source,
        }
        : this.state.sourcesById,
      detailVersions: this.state.detailsById[albumId]
        ? {
          ...this.state.detailVersions,
          [albumId]: (this.state.detailVersions[albumId] ?? 0) + 1,
        }
        : this.state.detailVersions,
      albumsVersion: this.state.albumsVersion + 1,
    };
    this.refreshAlbumsSnapshot();
    this.emitAlbums();
    if (this.state.detailsById[albumId]) {
      this.emitAlbumDetail(albumId);
    }
    return true;
  }

  private refreshAlbumsSnapshot() {
    this.albumsSnapshot = {
      libraryPath: this.state.libraryPath,
      albumOrder: this.state.albumOrder,
      albumsById: this.state.albumsById,
      albumsVersion: this.state.albumsVersion,
    };
  }

  private progressFromEvent(event: LogEntry): string {
    if (event.type === "album_output_ready" || event.type === "album_processed" || event.type === "album_completed") {
      return "completed";
    }
    if (event.type === "tags_written" || event.type === "organize_completed") {
      return "writing";
    }
    if (event.type === "album_processing_started" && event.stage === "organize_stage") {
      return "writing";
    }
    if (event.type === "album_processing_started" && event.stage === "metadata_stage") {
      return "matching";
    }
    if (event.type === "metadata_match" || event.type === "fallback_triggered" || event.type === "issue_detected" || event.type === "metadata_resolved") {
      return "matching";
    }
    if (event.type === "run_failed") {
      return "failed";
    }
    return event.stage ?? "idle";
  }

  private resetActiveRun(runId: string | null) {
    const nextAlbumsById = Object.fromEntries(
      this.state.albumOrder.flatMap((albumId) => {
        const baseAlbum = this.state.baseAlbumsById[albumId] ?? this.state.albumsById[albumId];
        if (!baseAlbum) {
          return [];
        }
        return [[albumId, clearRuntimeAlbumFields(baseAlbum)]];
      }),
    );
    const nextDetailsById = Object.fromEntries(
      Object.entries(this.state.baseDetailsById).map(([albumId, detail]) => [
        albumId,
        cloneDetailState({
          inspector: detail.inspector ? clearRuntimeInspectorFields(detail.inspector) : detail.inspector,
          tracks: detail.tracks,
        }),
      ]),
    );
    const nextSourcesById = Object.fromEntries(
      Object.keys(nextAlbumsById).map((albumId) => [albumId, { kind: "raw", runId: null } satisfies WorkspaceAlbumSource]),
    );
    this.state = {
      ...this.state,
      activeRunId: runId,
      outputRoot: null,
      albumsById: nextAlbumsById,
      detailsById: nextDetailsById,
      sourcesById: nextSourcesById,
      albumsVersion: this.state.albumsVersion + (Object.keys(nextAlbumsById).length ? 1 : 0),
    };
    this.refreshAlbumsSnapshot();
    this.emitAlbums();
    for (const albumId of Object.keys(nextDetailsById)) {
      this.emitAlbumDetail(albumId);
    }
  }

  private finishActiveRun(finalState: "completed" | "failed") {
    if (this.state.sourceMode !== "output") {
      const nextState = finalState === "completed" ? "completed" : "failed";
      return this.setAllAlbumProcessingStates(nextState);
    }

    const nextState = finalState === "completed" ? "completed" : "failed";
    let changed = false;
    for (const albumId of this.state.albumOrder) {
      const album = this.state.albumsById[albumId];
      if (!album || album.processingState === "completed") {
        continue;
      }
      changed = this.patchAlbum(albumId, { processingState: nextState }) || changed;
      const detail = this.state.detailsById[albumId];
      if (detail?.inspector && detail.inspector.processingState !== nextState) {
        this.state = {
          ...this.state,
          detailsById: {
            ...this.state.detailsById,
            [albumId]: {
              inspector: { ...detail.inspector, processingState: nextState },
              tracks: detail.tracks,
            },
          },
          detailVersions: {
            ...this.state.detailVersions,
            [albumId]: (this.state.detailVersions[albumId] ?? 0) + 1,
          },
        };
        this.emitAlbumDetail(albumId);
        changed = true;
      }
    }
    return changed;
  }

  private setAllAlbumProcessingStates(processingState: string) {
    let changed = false;
    for (const albumId of this.state.albumOrder) {
      changed = this.patchAlbum(albumId, { processingState }) || changed;
      const detail = this.state.detailsById[albumId];
      if (detail?.inspector && detail.inspector.processingState !== processingState) {
        this.state = {
          ...this.state,
          detailsById: {
            ...this.state.detailsById,
            [albumId]: {
              inspector: { ...detail.inspector, processingState },
              tracks: detail.tracks,
            },
          },
          detailVersions: {
            ...this.state.detailVersions,
            [albumId]: (this.state.detailVersions[albumId] ?? 0) + 1,
          },
        };
        this.emitAlbumDetail(albumId);
        changed = true;
      }
    }
    return changed;
  }

  private emitAll() {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private emitAlbums() {
    for (const listener of this.albumListeners) {
      listener();
    }
  }

  private emitAlbumDetail(albumId: string) {
    const listeners = this.detailListenersByAlbum.get(albumId);
    if (!listeners) {
      return;
    }
    for (const listener of listeners) {
      listener();
    }
  }
}

export const workspaceRuntimeStore = new WorkspaceRuntimeStore();

function shallowAlbumEqual(left: AlbumListItem, right: AlbumListItem) {
  return left.title === right.title
    && left.artist === right.artist
    && left.year === right.year
    && left.trackCount === right.trackCount
    && left.coverUrl === right.coverUrl
    && left.status === right.status
    && left.processingState === right.processingState
    && left.outputPath === right.outputPath
    && left.provider === right.provider
    && left.releaseType === right.releaseType
    && left.confidenceLevel === right.confidenceLevel
    && Boolean(left.lowConfidence) === Boolean(right.lowConfidence)
    && JSON.stringify(left.metadataIntelligence ?? null) === JSON.stringify(right.metadataIntelligence ?? null)
    && JSON.stringify(left.releaseIntelligence ?? null) === JSON.stringify(right.releaseIntelligence ?? null)
    && JSON.stringify(left.topAction ?? null) === JSON.stringify(right.topAction ?? null)
    && JSON.stringify(left.actionSummary ?? []) === JSON.stringify(right.actionSummary ?? [])
    && (left.actionCount ?? 0) === (right.actionCount ?? 0)
    && left.issueCounts.danger === right.issueCounts.danger
    && left.issueCounts.warning === right.issueCounts.warning
    && left.issueCounts.success === right.issueCounts.success;
}
