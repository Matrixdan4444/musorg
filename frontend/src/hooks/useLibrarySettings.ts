import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/i18n/useI18n";
import {
  clearSettingsCache,
  getLibrarySettings,
  pickLibrarySettings,
  pickOutputSettings,
  setLibrarySettings,
} from "@/lib/api/music";
import { defaultMetadataPreservationSettings } from "@/lib/metadata-preservation";
import { useTheme } from "@/theme/useTheme";
import type {
  AccentColor,
  DuplicateHandlingMode,
  FilenameCompatibilityMode,
  LanguageCode,
  LibrarySettingsPayload,
  MetadataPreservationSettings,
  OutputFormatSettings,
  ThemeMode,
  UpdateLibrarySettingsPayload,
} from "@/types/music";

const DEFAULT_THEME_MODE: ThemeMode = "dark";
const DEFAULT_ACCENT_COLOR: AccentColor = "violet";

export function useLibrarySettings() {
  const { setLanguage, t } = useI18n();
  const { setAppearance } = useTheme();
  const [data, setData] = useState<LibrarySettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [picking, setPicking] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const applyResolvedPayload = useCallback((payload: LibrarySettingsPayload) => {
    setData(payload);
    setLanguage(payload.language);
    setAppearance({
      themeMode: payload.themeMode,
      accentColor: payload.accentColor,
    });
    return payload;
  }, [setAppearance, setLanguage]);

  const buildSettingsPayload = useCallback((overrides: Partial<UpdateLibrarySettingsPayload>): UpdateLibrarySettingsPayload => ({
    libraryRoot: overrides.libraryRoot ?? data?.libraryRoot ?? "",
    outputRoot: overrides.outputRoot ?? data?.outputRoot ?? "",
    developerMode: overrides.developerMode ?? data?.developerMode ?? false,
    language: overrides.language ?? data?.language ?? "en",
    themeMode: overrides.themeMode ?? data?.themeMode ?? DEFAULT_THEME_MODE,
    accentColor: overrides.accentColor ?? data?.accentColor ?? DEFAULT_ACCENT_COLOR,
    duplicateHandling: overrides.duplicateHandling ?? data?.duplicateHandling ?? "keep_everything",
    filenameCompatibility: overrides.filenameCompatibility ?? data?.filenameCompatibility ?? "preserve_original",
    outputFormat: overrides.outputFormat ?? data?.outputFormat ?? defaultOutputFormatSettings(),
    metadataPreservation: overrides.metadataPreservation ?? data?.metadataPreservation ?? defaultMetadataPreservationSettings(),
    onboardingCompleted: overrides.onboardingCompleted ?? data?.onboardingCompleted ?? false,
    onboardingDismissed: overrides.onboardingDismissed ?? data?.onboardingDismissed ?? false,
  }), [data]);

  const refetch = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      setMessage(null);
      const payload = await getLibrarySettings();
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.load");
      setError(nextError);
      return null;
    } finally {
      setLoading(false);
    }
  }, [applyResolvedPayload, t]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const saveLibraryRoots = useCallback(async (libraryRoot: string, outputRoot: string) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ libraryRoot, outputRoot }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveLanguage = useCallback(async (language: LanguageCode) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ language }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.saveLanguage");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveThemeMode = useCallback(async (themeMode: ThemeMode) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ themeMode }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveAccentColor = useCallback(async (accentColor: AccentColor) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ accentColor }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveOutputFormat = useCallback(async (outputFormat: OutputFormatSettings) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ outputFormat }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveMetadataPreservation = useCallback(async (metadataPreservation: MetadataPreservationSettings) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ metadataPreservation }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveDuplicateHandling = useCallback(async (duplicateHandling: DuplicateHandlingMode) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ duplicateHandling }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveFilenameCompatibility = useCallback(async (filenameCompatibility: FilenameCompatibilityMode) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ filenameCompatibility }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const saveOnboardingState = useCallback(async (onboardingCompleted: boolean, onboardingDismissed: boolean) => {
    try {
      setSaving(true);
      setError(null);
      setMessage(null);
      const payload = await setLibrarySettings(buildSettingsPayload({ onboardingCompleted, onboardingDismissed }));
      return applyResolvedPayload(payload);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.save");
      setError(nextError);
      return null;
    } finally {
      setSaving(false);
    }
  }, [applyResolvedPayload, buildSettingsPayload, t]);

  const pickLibraryRoot = useCallback(async () => {
    try {
      setPicking(true);
      setError(null);
      setMessage(null);
      const payload = await pickLibrarySettings();
      if (payload.error) {
        setError(payload.error);
      }
      return payload;
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.pickLibrary");
      setError(nextError);
      return null;
    } finally {
      setPicking(false);
    }
  }, [t]);

  const pickOutputRoot = useCallback(async () => {
    try {
      setPicking(true);
      setError(null);
      setMessage(null);
      const payload = await pickOutputSettings();
      if (payload.error) {
        setError(payload.error);
      }
      return payload;
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.pickOutput");
      setError(nextError);
      return null;
    } finally {
      setPicking(false);
    }
  }, [t]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const clearCache = useCallback(async () => {
    try {
      setClearingCache(true);
      setError(null);
      setMessage(null);
      const payload = await clearSettingsCache();
      if (payload.cleared) {
        setMessage(
          payload.metadataEntriesCleared > 0
            ? t("settings.cacheClearedCount", { count: payload.metadataEntriesCleared })
            : t("settings.cacheCleared"),
        );
      }
      return payload;
    } catch (err) {
      const nextError = err instanceof Error ? err.message : t("settings.errors.clearCache");
      setError(nextError);
      return null;
    } finally {
      setClearingCache(false);
    }
  }, [t]);

  return {
    data,
    loading,
    saving,
    picking,
    clearingCache,
    error,
    message,
    clearError,
    refetch,
    saveLibraryRoots,
    saveLanguage,
    saveThemeMode,
    saveAccentColor,
    saveDuplicateHandling,
    saveFilenameCompatibility,
    saveOnboardingState,
    saveOutputFormat,
    saveMetadataPreservation,
    clearCache,
    pickLibraryRoot,
    pickOutputRoot,
  };
}

function defaultOutputFormatSettings(): OutputFormatSettings {
  return {
    albumFolderPreset: "artist_year_album",
    discHandling: "keep_together",
    fileNaming: "track_title",
    separatorStyle: "dot",
    customAlbumPattern: ["artist", "folder_break", "year", "album"],
    customAdvancedTemplate: null,
  };
}
