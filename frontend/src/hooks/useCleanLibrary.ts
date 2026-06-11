import { useCallback, useState } from "react";
import { useI18n } from "@/i18n/useI18n";
import { cleanLibrary } from "@/lib/api/music";
import type { AlbumMetadataOverride, CleanLibraryPayload } from "@/types/music";


export function useCleanLibrary() {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (overrides: AlbumMetadataOverride[] = []): Promise<CleanLibraryPayload | null> => {
    try {
      setLoading(true);
      setError(null);
      return await cleanLibrary(overrides);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.cleanLibrary");
      setError(nextError);
      return null;
    } finally {
      setLoading(false);
    }
  }, [t]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return { run, loading, error, clearError };
}
