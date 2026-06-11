import { useEffect, useState } from "react";
import { getAlbumActions } from "@/lib/api/music";
import { useI18n } from "@/i18n/useI18n";
import type { AlbumActionsPayload } from "@/types/music";


export function useAlbumActions(albumId: string | null, refreshKey = 0, enabled = true) {
  const { t } = useI18n();
  const [data, setData] = useState<AlbumActionsPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !albumId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;

    async function load() {
      if (!albumId) {
        return;
      }
      try {
        setLoading(true);
        setError(null);
        const payload = await getAlbumActions(albumId);
        if (!cancelled) {
          setData(payload);
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
  }, [albumId, enabled, refreshKey, t]);

  return { data, loading: enabled ? loading : false, error: enabled ? error : null };
}
