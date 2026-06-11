import { useEffect, useState, useSyncExternalStore } from "react";
import { useI18n } from "@/i18n/useI18n";
import { workspaceRuntimeStore } from "@/lib/workspace-runtime-store";
import type { AlbumsPayload } from "@/types/music";


export function useAlbums(refreshKey = 0, developerMode = false, enabled = true) {
  const { t } = useI18n();
  const snapshot = useSyncExternalStore(
    enabled ? workspaceRuntimeStore.subscribeAlbums : () => () => undefined,
    workspaceRuntimeStore.getAlbumsSnapshot,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        await workspaceRuntimeStore.ensureConnected(developerMode);
        await workspaceRuntimeStore.bootstrapAlbums();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("import.failedAlbums"));
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
  }, [developerMode, enabled, refreshKey, t]);
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
    }
  }, [enabled]);

  const data: AlbumsPayload | null = snapshot.albumOrder.length || snapshot.libraryPath
    ? {
      libraryPath: snapshot.libraryPath,
      albums: snapshot.albumOrder
        .map((albumId) => snapshot.albumsById[albumId])
        .filter((album): album is NonNullable<typeof album> => Boolean(album)),
    }
    : null;

  return { data, loading: enabled ? loading : false, error: enabled ? error : null };
}
