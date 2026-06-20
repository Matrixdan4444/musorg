import { motion } from "framer-motion";
import type { CSSProperties } from "react";
import { FieldHelp } from "@/components/FieldHelp";
import { Panel } from "@/components/Panel";
import { DuplicateHandlingCard } from "@/components/settings/DuplicateHandlingCard";
import { FilenameCompatibilityCard } from "@/components/settings/FilenameCompatibilityCard";
import { MetadataPreservationCard } from "@/components/settings/MetadataPreservationCard";
import { OutputFolderFormatCard } from "@/components/settings/OutputFolderFormatCard";
import { AppShell } from "@/components/layout/AppShell";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { useAlbumDetail } from "@/hooks/useAlbumDetail";
import { useAlbums } from "@/hooks/useAlbums";
import { useLibrarySettings } from "@/hooks/useLibrarySettings";
import { useI18n } from "@/i18n/useI18n";
import { cn } from "@/lib/cn";
import { useTheme } from "@/theme/useTheme";
import type { AppPage } from "@/types/layout";
import type { AccentColor, LanguageCode, ThemeMode } from "@/types/music";

interface SettingsPageProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
}

interface SwatchStyle extends CSSProperties {
  "--swatch-ring"?: string;
  "--swatch-fill"?: string;
  "--swatch-glow"?: string;
}

const THEME_MODE_OPTIONS: Array<{ value: ThemeMode; previewClassName: string; labelKey: "settings.themeModeOptions.light" | "settings.themeModeOptions.dark" }> = [
  { value: "light", previewClassName: "appearance-swatch-mode-light", labelKey: "settings.themeModeOptions.light" },
  { value: "dark", previewClassName: "appearance-swatch-mode-dark", labelKey: "settings.themeModeOptions.dark" },
];

const ACCENT_OPTIONS: Array<{
  value: AccentColor;
  labelKey:
    | "settings.accentColorOptions.violet"
    | "settings.accentColorOptions.indigo"
    | "settings.accentColorOptions.blue"
    | "settings.accentColorOptions.teal"
    | "settings.accentColorOptions.sky"
    | "settings.accentColorOptions.emerald"
    | "settings.accentColorOptions.amber"
    | "settings.accentColorOptions.rose";
  previewStyle: SwatchStyle;
}> = [
  { value: "violet", labelKey: "settings.accentColorOptions.violet", previewStyle: { "--swatch-ring": "260 83% 58%", "--swatch-fill": "273 92% 68%", "--swatch-glow": "220 90% 70%" } },
  { value: "indigo", labelKey: "settings.accentColorOptions.indigo", previewStyle: { "--swatch-ring": "246 76% 60%", "--swatch-fill": "232 90% 70%", "--swatch-glow": "224 92% 76%" } },
  { value: "blue", labelKey: "settings.accentColorOptions.blue", previewStyle: { "--swatch-ring": "214 84% 58%", "--swatch-fill": "201 92% 68%", "--swatch-glow": "199 92% 76%" } },
  { value: "teal", labelKey: "settings.accentColorOptions.teal", previewStyle: { "--swatch-ring": "182 76% 44%", "--swatch-fill": "174 78% 52%", "--swatch-glow": "196 88% 72%" } },
  { value: "sky", labelKey: "settings.accentColorOptions.sky", previewStyle: { "--swatch-ring": "201 88% 62%", "--swatch-fill": "193 92% 72%", "--swatch-glow": "214 94% 80%" } },
  { value: "emerald", labelKey: "settings.accentColorOptions.emerald", previewStyle: { "--swatch-ring": "158 66% 46%", "--swatch-fill": "167 70% 54%", "--swatch-glow": "176 70% 68%" } },
  { value: "amber", labelKey: "settings.accentColorOptions.amber", previewStyle: { "--swatch-ring": "38 86% 56%", "--swatch-fill": "48 94% 63%", "--swatch-glow": "24 90% 70%" } },
  { value: "rose", labelKey: "settings.accentColorOptions.rose", previewStyle: { "--swatch-ring": "344 78% 60%", "--swatch-fill": "354 88% 70%", "--swatch-glow": "12 90% 72%" } },
];

export function SettingsPage({ activePage, onNavigate }: SettingsPageProps) {
  const { language, setLanguage, t } = useI18n();
  const { themeMode, accentColor, setThemeMode, setAccentColor } = useTheme();
  const librarySettings = useLibrarySettings();
  const developerMode = librarySettings.data?.developerMode ?? false;
  const settingsActive = activePage === "settings";
  const { data: albumsPayload } = useAlbums(0, developerMode, settingsActive);
  const previewAlbumId = settingsActive ? albumsPayload?.albums[0]?.id ?? null : null;
  const { data: previewAlbumDetail } = useAlbumDetail(previewAlbumId, 0, developerMode, settingsActive);
  const statusLabel = librarySettings.data?.libraryRoot
    ? t("settings.workspaceReady")
    : t("settings.notConfigured");
  const sourceLabel = {
    environment: t("settings.sourceValues.environment"),
    settings: t("settings.sourceValues.settings"),
    none: t("settings.sourceValues.none"),
  }[librarySettings.data?.source ?? "none"];

  async function handleLanguageChange(nextLanguage: LanguageCode) {
    const previousLanguage = language;
    setLanguage(nextLanguage);
    const payload = await librarySettings.saveLanguage(nextLanguage);
    if (!payload) {
      setLanguage(previousLanguage);
    }
  }

  async function handleThemeModeChange(nextThemeMode: ThemeMode) {
    const previousThemeMode = themeMode;
    setThemeMode(nextThemeMode);
    const payload = await librarySettings.saveThemeMode(nextThemeMode);
    if (!payload) {
      setThemeMode(previousThemeMode);
    }
  }

  async function handleAccentColorChange(nextAccentColor: AccentColor) {
    const previousAccentColor = accentColor;
    setAccentColor(nextAccentColor);
    const payload = await librarySettings.saveAccentColor(nextAccentColor);
    if (!payload) {
      setAccentColor(previousAccentColor);
    }
  }

  async function handleClearCache() {
    await librarySettings.clearCache();
  }

  async function handleOutputFormatChange(nextValue: NonNullable<typeof librarySettings.data>["outputFormat"]) {
    await librarySettings.saveOutputFormat(nextValue);
  }

  async function handleDuplicateHandlingChange(nextValue: NonNullable<typeof librarySettings.data>["duplicateHandling"]) {
    await librarySettings.saveDuplicateHandling(nextValue);
  }

  async function handleFilenameCompatibilityChange(nextValue: NonNullable<typeof librarySettings.data>["filenameCompatibility"]) {
    await librarySettings.saveFilenameCompatibility(nextValue);
  }

  async function handleMetadataPreservationChange(nextValue: NonNullable<typeof librarySettings.data>["metadataPreservation"]) {
    await librarySettings.saveMetadataPreservation(nextValue);
  }

  return (
    <AppShell
      header={(
        <header className="space-y-4 border-b border-border-soft/75 px-4 py-5 lg:px-8">
          <div className="space-y-1">
            <h1 className="text-[17px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
              {t("settings.title")}
            </h1>
            <p className="text-[13px] text-muted-foreground">
              {t("settings.subtitle")}
            </p>
          </div>
        </header>
      )}
      sidebar={(
        <AppSidebar
          activePage={activePage}
          onNavigate={onNavigate}
          statusLabel={statusLabel}
        />
      )}
    >
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22 }}
        className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_320px]"
      >
        <Panel className="space-y-6 px-6 py-6">
          <div className="space-y-1">
            <h2 className="text-[16px] font-semibold text-[hsl(var(--text-strong))]">{t("settings.runtimeTitle")}</h2>
            <p className="text-[13px] text-muted-foreground">
              {t("settings.runtimeDescription")}
            </p>
          </div>

          <div className="rounded-3xl border border-border-soft/75 bg-surface-subtle/85 p-5">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-4 border-b border-border-soft/75 pb-4 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <h3 className="text-[15px] font-semibold text-[hsl(var(--text-strong))]">{t("settings.languageTitle")}</h3>
                  <p className="max-w-[560px] text-[13px] leading-6 text-muted-foreground">
                    {t("settings.languageDescription")}
                  </p>
                </div>

                <select
                  className="app-control h-11 min-w-[150px] rounded-2xl px-4 text-[13px] transition"
                  value={librarySettings.data?.language ?? language}
                  onChange={(event) => void handleLanguageChange(event.target.value as LanguageCode)}
                  disabled={librarySettings.loading || librarySettings.saving}
                >
                  <option value="en">{t("settings.languageOptionEnglish")}</option>
                  <option value="ru">{t("settings.languageOptionRussian")}</option>
                </select>
              </div>

              <div className="flex flex-col gap-4 border-b border-border-soft/75 pb-4 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <h3 className="text-[15px] font-semibold text-[hsl(var(--text-strong))]">{t("settings.themeModeTitle")}</h3>
                  <p className="max-w-[560px] text-[13px] leading-6 text-muted-foreground">
                    {t("settings.themeModeDescription")}
                  </p>
                </div>

                <div
                  className="appearance-swatch-group md:justify-end"
                  role="radiogroup"
                  aria-label={t("settings.themeModeTitle")}
                >
                  {THEME_MODE_OPTIONS.map((option) => (
                    <AppearanceSwatchButton
                      key={option.value}
                      label={t(option.labelKey)}
                      selected={(librarySettings.data?.themeMode ?? themeMode) === option.value}
                      previewClassName={option.previewClassName}
                      onClick={() => void handleThemeModeChange(option.value)}
                      disabled={librarySettings.loading || librarySettings.saving}
                    />
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-4 border-b border-border-soft/75 pb-4 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <h3 className="text-[15px] font-semibold text-[hsl(var(--text-strong))]">{t("settings.accentColorTitle")}</h3>
                  <p className="max-w-[560px] text-[13px] leading-6 text-muted-foreground">
                    {t("settings.accentColorDescription")}
                  </p>
                </div>

                <div
                  className="appearance-swatch-group md:justify-end"
                  role="radiogroup"
                  aria-label={t("settings.accentColorTitle")}
                >
                  {ACCENT_OPTIONS.map((option) => (
                    <AppearanceSwatchButton
                      key={option.value}
                      label={t(option.labelKey)}
                      selected={(librarySettings.data?.accentColor ?? accentColor) === option.value}
                      previewClassName="appearance-swatch-accent"
                      previewStyle={option.previewStyle}
                      onClick={() => void handleAccentColorChange(option.value)}
                      disabled={librarySettings.loading || librarySettings.saving}
                    />
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="text-[15px] font-semibold text-[hsl(var(--text-strong))]">{t("settings.clearCacheTitle")}</h3>
                  <FieldHelp label={t("settings.clearCacheTitle")} description={t("settings.clearCacheDescription")} />
                </div>

                <button
                  className="app-button-secondary inline-flex h-11 min-w-[150px] items-center justify-center rounded-2xl px-4 text-[13px] font-semibold transition"
                  type="button"
                  onClick={handleClearCache}
                  disabled={librarySettings.clearingCache}
                >
                  {librarySettings.clearingCache ? t("common.clearing") : t("settings.clearCacheAction")}
                </button>
              </div>
            </div>

            {librarySettings.error ? (
              <p className="mt-4 text-[12px] text-[hsl(var(--danger-fg))]">{librarySettings.error}</p>
            ) : null}
            {!librarySettings.error && librarySettings.message ? (
              <p className="mt-4 text-[12px] text-[hsl(var(--success-fg))]">{librarySettings.message}</p>
            ) : null}
          </div>

          <OutputFolderFormatCard
            value={librarySettings.data?.outputFormat}
            saving={librarySettings.saving}
            onChange={handleOutputFormatChange}
            previewInspector={previewAlbumDetail.inspector}
            previewTracks={previewAlbumDetail.tracks}
            filenameCompatibility={librarySettings.data?.filenameCompatibility ?? "preserve_original"}
          />

          <DuplicateHandlingCard
            value={librarySettings.data?.duplicateHandling}
            saving={librarySettings.saving}
            onChange={handleDuplicateHandlingChange}
          />

          <FilenameCompatibilityCard
            value={librarySettings.data?.filenameCompatibility}
            saving={librarySettings.saving}
            onChange={handleFilenameCompatibilityChange}
          />

          <MetadataPreservationCard
            value={librarySettings.data?.metadataPreservation}
            saving={librarySettings.saving}
            onChange={handleMetadataPreservationChange}
          />
        </Panel>

        <Panel className="space-y-4 px-5 py-5">
          <div className="space-y-1">
            <h2 className="text-[14px] font-semibold text-[hsl(var(--text-strong))]">{t("settings.currentSessionTitle")}</h2>
            <p className="text-[12px] text-muted-foreground">
              {t("settings.currentSessionDescription")}
            </p>
          </div>

          <div className="space-y-3 text-[13px]">
            <div className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t("settings.fields.library")}</p>
              <p className="mt-1 break-all text-[hsl(var(--text-base))]">
                {librarySettings.data?.libraryRoot || t("settings.notConfigured")}
              </p>
            </div>

            <div className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t("settings.fields.output")}</p>
              <p className="mt-1 break-all text-[hsl(var(--text-base))]">
                {librarySettings.data?.outputRoot || t("settings.notConfigured")}
              </p>
            </div>

            <div className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t("settings.fields.source")}</p>
              <p className="mt-1 text-[hsl(var(--text-base))]">
                {sourceLabel}
              </p>
            </div>
          </div>
        </Panel>
      </motion.div>
    </AppShell>
  );
}

interface AppearanceSwatchButtonProps {
  disabled: boolean;
  label: string;
  onClick: () => void;
  previewClassName: string;
  previewStyle?: SwatchStyle;
  selected: boolean;
}

function AppearanceSwatchButton({
  disabled,
  label,
  onClick,
  previewClassName,
  previewStyle,
  selected,
}: AppearanceSwatchButtonProps) {
  return (
    <button
      className="appearance-swatch-option disabled:cursor-not-allowed disabled:opacity-60"
      data-selected={selected ? "true" : "false"}
      type="button"
      role="radio"
      aria-checked={selected}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      <span
        className={cn("appearance-swatch-circle", previewClassName)}
        style={previewStyle}
      />
      <span className="appearance-swatch-label">{label}</span>
    </button>
  );
}
