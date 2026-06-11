import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useI18n } from "@/i18n/useI18n";
import { workspaceRuntimeStore } from "@/lib/workspace-runtime-store";
import type { AlbumInspectorData, TrackRow } from "@/types/music";


interface AlbumDetailState {
  inspector: AlbumInspectorData | null;
  tracks: TrackRow[];
}


export function useAlbumDetail(albumId: string | null, refreshKey = 0, developerMode = false, enabled = true) {
  const { t } = useI18n();
  const detailState = useSyncExternalStore(
    (listener) => (enabled && albumId ? workspaceRuntimeStore.subscribeAlbumDetail(albumId, listener) : () => undefined),
    () => workspaceRuntimeStore.getAlbumDetailSnapshot(albumId),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setError(null);
      return;
    }

    if (!albumId) {
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    const currentAlbumId = albumId;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        await workspaceRuntimeStore.ensureConnected(developerMode);
        const existing = workspaceRuntimeStore.getSnapshot().detailsById[currentAlbumId];
        if (!existing?.inspector || existing.tracks.length === 0 || refreshKey > 0) {
          await workspaceRuntimeStore.bootstrapAlbumDetail(currentAlbumId);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("import.failedInspector"));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [albumId, developerMode, enabled, refreshKey, t]);

  const data = useMemo<AlbumDetailState>(() => {
    if (!albumId) {
      return { inspector: null, tracks: [] };
    }
    return detailState;
  }, [albumId, detailState]);

  return { data, loading: enabled ? loading : false, error: enabled ? error : null };
}
