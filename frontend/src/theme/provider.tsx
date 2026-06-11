import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import type { AccentColor, AppearanceSettings, ThemeMode } from "@/types/music";

const allowedThemeModes = ["light", "dark"] as const;
const allowedAccentColors = ["violet", "indigo", "blue", "teal", "sky", "emerald", "amber", "rose"] as const;
const STORAGE_KEY = "musorg.appearance";
const LEGACY_THEME_STORAGE_KEY = "musorg.theme";
const DEFAULT_APPEARANCE: AppearanceSettings = {
  themeMode: "dark",
  accentColor: "violet",
};

interface ThemeContextValue {
  themeMode: ThemeMode;
  accentColor: AccentColor;
  setThemeMode: (themeMode: ThemeMode) => void;
  setAccentColor: (accentColor: AccentColor) => void;
  setAppearance: (appearance: AppearanceSettings) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function normalizeThemeMode(themeMode: string | null | undefined): ThemeMode {
  return allowedThemeModes.includes(themeMode as ThemeMode) ? (themeMode as ThemeMode) : DEFAULT_APPEARANCE.themeMode;
}

export function normalizeAccentColor(accentColor: string | null | undefined): AccentColor {
  const normalized = String(accentColor || "").trim().toLowerCase();
  if (normalized === "cyan") {
    return "sky";
  }
  return allowedAccentColors.includes(normalized as AccentColor) ? (normalized as AccentColor) : DEFAULT_APPEARANCE.accentColor;
}

function resolveLegacyAppearance(theme: string | null | undefined): AppearanceSettings {
  const value = String(theme || "").trim().toLowerCase();
  const appearances: Record<string, AppearanceSettings> = {
    light: { themeMode: "light", accentColor: "violet" },
    dark: { themeMode: "dark", accentColor: "violet" },
    dark_teal: { themeMode: "dark", accentColor: "teal" },
    dark_blue: { themeMode: "dark", accentColor: "blue" },
  };
  return appearances[value] ?? DEFAULT_APPEARANCE;
}

export function normalizeAppearance(appearance: Partial<AppearanceSettings> | null | undefined): AppearanceSettings {
  return {
    themeMode: normalizeThemeMode(appearance?.themeMode),
    accentColor: normalizeAccentColor(appearance?.accentColor),
  };
}

export function readStoredAppearance(): AppearanceSettings {
  if (typeof window === "undefined") {
    return DEFAULT_APPEARANCE;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed && typeof parsed === "object") {
        return normalizeAppearance(parsed as Partial<AppearanceSettings>);
      }
    }
  } catch {
    // Ignore malformed cache and fall back to defaults.
  }

  return resolveLegacyAppearance(window.localStorage.getItem(LEGACY_THEME_STORAGE_KEY));
}

export function applyAppearance(appearance: AppearanceSettings) {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.setAttribute("data-theme-mode", appearance.themeMode);
  document.documentElement.setAttribute("data-accent-color", appearance.accentColor);
}

export function bootstrapStoredAppearance() {
  const appearance = readStoredAppearance();
  applyAppearance(appearance);
  return appearance;
}

export function ThemeProvider({ children }: PropsWithChildren) {
  const [appearance, setAppearanceState] = useState<AppearanceSettings>(() => readStoredAppearance());

  useEffect(() => {
    applyAppearance(appearance);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(appearance));
      window.localStorage.removeItem(LEGACY_THEME_STORAGE_KEY);
    }
  }, [appearance]);

  const setAppearance = useCallback((nextAppearance: AppearanceSettings) => {
    setAppearanceState(normalizeAppearance(nextAppearance));
  }, []);

  const setThemeMode = useCallback((nextThemeMode: ThemeMode) => {
    setAppearanceState((current) => ({
      ...current,
      themeMode: normalizeThemeMode(nextThemeMode),
    }));
  }, []);

  const setAccentColor = useCallback((nextAccentColor: AccentColor) => {
    setAppearanceState((current) => ({
      ...current,
      accentColor: normalizeAccentColor(nextAccentColor),
    }));
  }, []);

  const value = useMemo(() => ({
    themeMode: appearance.themeMode,
    accentColor: appearance.accentColor,
    setThemeMode,
    setAccentColor,
    setAppearance,
  }), [appearance, setAccentColor, setAppearance, setThemeMode]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
