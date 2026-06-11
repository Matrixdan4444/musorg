import { useEffect, useSyncExternalStore } from "react";
import { useI18n } from "@/i18n/useI18n";
import { batchEditStore } from "@/lib/batch-edit-store";


export function useBatchEditAlbumDetail(albumId: string | null, refreshKey = 0, enabled = true) {
  const { t } = useI18n();
  const snapshot = useSyncExternalStore(
    (listener) => (enabled && albumId ? batchEditStore.subscribeAlbumDetail(albumId, listener) : () => undefined),
    () => batchEditStore.getAlbumDetailSnapshot(albumId),
  );

  useEffect(() => {
    if (!enabled || !albumId) {
      return;
    }
    void batchEditStore.ensureAlbumDetail(albumId, t("import.failedInspector"), refreshKey > 0);
  }, [albumId, enabled, refreshKey, t]);

  return snapshot;
}
