import { useEffect, useSyncExternalStore } from "react";
import { useI18n } from "@/i18n/useI18n";
import { batchEditStore } from "@/lib/batch-edit-store";


export function useBatchEditAlbums(refreshKey = 0, enabled = true) {
  const { t } = useI18n();
  const snapshot = useSyncExternalStore(
    enabled ? batchEditStore.subscribeAlbums : () => () => undefined,
    batchEditStore.getAlbumsSnapshot,
  );

  useEffect(() => {
    if (!enabled) {
      return;
    }
    void batchEditStore.ensureAlbums(t("import.failedAlbums"), refreshKey > 0);
  }, [enabled, refreshKey, t]);

  return snapshot;
}
