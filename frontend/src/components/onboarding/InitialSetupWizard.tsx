import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  FileMusic,
  Folder,
  FolderTree,
  Languages,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ComponentType, CSSProperties, ReactNode } from "react";
import { BrandLogo } from "@/components/layout/BrandLogo";
import { Panel } from "@/components/Panel";
import { OutputPreviewMockup } from "@/components/preview/OutputPreviewMockup";
import type { PreviewFocusSection } from "@/components/preview/OutputPreviewMockup";
import { useLibrarySettings } from "@/hooks/useLibrarySettings";
import { useI18n } from "@/i18n/useI18n";
import { useTheme } from "@/theme/useTheme";
import {
  buildOutputPreviewTree,
  defaultOutputFormatSettings,
  samplePreviewAlbum,
} from "@/lib/output-format";
import { cn } from "@/lib/cn";
import type {
  AccentColor,
  DuplicateHandlingMode,
  FilenameCompatibilityMode,
  FileNamingMode,
  LibrarySettingsPayload,
  OutputFormatSettings,
  SeparatorStyle,
  ThemeMode,
} from "@/types/music";

type SwatchStyle = CSSProperties & {
  "--swatch-ring"?: string;
  "--swatch-fill"?: string;
  "--swatch-glow"?: string;
};

const THEME_MODE_OPTIONS: Array<{
  value: ThemeMode;
  previewClassName: string;
  labelKey: "settings.themeModeOptions.light" | "settings.themeModeOptions.dark";
}> = [
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

type WizardEntrySource = "startup" | "settings";
type WizardExitReason = "skip" | "finish";

interface InitialSetupWizardProps {
  entrySource: WizardEntrySource;
  onExit: (reason: WizardExitReason, payload: LibrarySettingsPayload | null) => void;
}

const STEP_IDS = ["welcome", "appearance", "folders", "albums", "tracks", "safety", "review"] as const;
type WizardStepId = typeof STEP_IDS[number];

const PRESET_OPTIONS: Array<{
  value: OutputFormatSettings["albumFolderPreset"];
  titleKey:
    | "settings.outputFormat.presets.artistYearAlbum.title"
    | "settings.outputFormat.presets.artistAlbumYear.title"
    | "settings.outputFormat.presets.artistAlbum.title"
    | "settings.outputFormat.presets.genreArtistAlbum.title";
  descriptionKey:
    | "settings.outputFormat.presets.artistYearAlbum.description"
    | "settings.outputFormat.presets.artistAlbumYear.description"
    | "settings.outputFormat.presets.artistAlbum.description"
    | "settings.outputFormat.presets.genreArtistAlbum.description";
}> = [
  {
    value: "artist_year_album",
    titleKey: "settings.outputFormat.presets.artistYearAlbum.title",
    descriptionKey: "settings.outputFormat.presets.artistYearAlbum.description",
  },
  {
    value: "artist_album_year",
    titleKey: "settings.outputFormat.presets.artistAlbumYear.title",
    descriptionKey: "settings.outputFormat.presets.artistAlbumYear.description",
  },
  {
    value: "artist_album",
    titleKey: "settings.outputFormat.presets.artistAlbum.title",
    descriptionKey: "settings.outputFormat.presets.artistAlbum.description",
  },
  {
    value: "genre_artist_album",
    titleKey: "settings.outputFormat.presets.genreArtistAlbum.title",
    descriptionKey: "settings.outputFormat.presets.genreArtistAlbum.description",
  },
];

const FILE_NAMING_OPTIONS: Array<{
  fileNaming: FileNamingMode;
  separatorStyle: SeparatorStyle;
  titleKey:
    | "settings.outputFormat.fileNamingOptions.trackTitle.title"
    | "settings.outputFormat.fileNamingOptions.artistTitle.title"
    | "settings.outputFormat.fileNamingOptions.trackArtistTitle.title"
    | "settings.outputFormat.fileNamingOptions.titleOnly.title";
  preview: string;
}> = [
  {
    fileNaming: "track_title",
    separatorStyle: "dot",
    titleKey: "settings.outputFormat.fileNamingOptions.trackTitle.title",
    preview: "01. Track Title.flac",
  },
  {
    fileNaming: "artist_title",
    separatorStyle: "hyphen",
    titleKey: "settings.outputFormat.fileNamingOptions.artistTitle.title",
    preview: "Artist - Track Title.flac",
  },
  {
    fileNaming: "track_artist_title",
    separatorStyle: "hyphen",
    titleKey: "settings.outputFormat.fileNamingOptions.trackArtistTitle.title",
    preview: "01 - Artist - Track Title.flac",
  },
  {
    fileNaming: "title_only",
    separatorStyle: "minimal",
    titleKey: "settings.outputFormat.fileNamingOptions.titleOnly.title",
    preview: "Track Title.flac",
  },
];

const DISC_HANDLING_OPTIONS: Array<{
  value: OutputFormatSettings["discHandling"];
  titleKey:
    | "settings.outputFormat.discOptions.keepTogether.title"
    | "settings.outputFormat.discOptions.flatten.title"
    | "settings.outputFormat.discOptions.prefixDisc.title";
}> = [
  { value: "keep_together", titleKey: "settings.outputFormat.discOptions.keepTogether.title" },
  { value: "flatten", titleKey: "settings.outputFormat.discOptions.flatten.title" },
  { value: "prefix_disc", titleKey: "settings.outputFormat.discOptions.prefixDisc.title" },
];

const DUPLICATE_OPTIONS: Array<{
  value: DuplicateHandlingMode;
  titleKey:
    | "settings.duplicateHandling.options.keepEverything.title"
    | "settings.duplicateHandling.options.preferBestVersion.title"
    | "settings.duplicateHandling.options.moveDuplicatesToArchive.title";
  descriptionKey:
    | "settings.duplicateHandling.options.keepEverything.description"
    | "settings.duplicateHandling.options.preferBestVersion.description"
    | "settings.duplicateHandling.options.moveDuplicatesToArchive.description";
}> = [
  {
    value: "keep_everything",
    titleKey: "settings.duplicateHandling.options.keepEverything.title",
    descriptionKey: "settings.duplicateHandling.options.keepEverything.description",
  },
  {
    value: "prefer_best_version",
    titleKey: "settings.duplicateHandling.options.preferBestVersion.title",
    descriptionKey: "settings.duplicateHandling.options.preferBestVersion.description",
  },
  {
    value: "move_duplicates_to_archive",
    titleKey: "settings.duplicateHandling.options.moveDuplicatesToArchive.title",
    descriptionKey: "settings.duplicateHandling.options.moveDuplicatesToArchive.description",
  },
];

const COMPATIBILITY_OPTIONS: Array<{
  value: FilenameCompatibilityMode;
  titleKey:
    | "settings.filenameCompatibility.options.preserveOriginal.title"
    | "settings.filenameCompatibility.options.crossPlatformSafe.title";
  descriptionKey:
    | "settings.filenameCompatibility.options.preserveOriginal.description"
    | "settings.filenameCompatibility.options.crossPlatformSafe.description";
}> = [
  {
    value: "preserve_original",
    titleKey: "settings.filenameCompatibility.options.preserveOriginal.title",
    descriptionKey: "settings.filenameCompatibility.options.preserveOriginal.description",
  },
  {
    value: "cross_platform_safe",
    titleKey: "settings.filenameCompatibility.options.crossPlatformSafe.title",
    descriptionKey: "settings.filenameCompatibility.options.crossPlatformSafe.description",
  },
];

export function InitialSetupWizard({ entrySource, onExit }: InitialSetupWizardProps) {
  const { t, language, setLanguage } = useI18n();
  const { themeMode, accentColor, setThemeMode, setAccentColor } = useTheme();
  const librarySettings = useLibrarySettings();
  const [stepIndex, setStepIndex] = useState(0);
  const [folderDraft, setFolderDraft] = useState({ libraryRoot: "", outputRoot: "" });

  const settings = librarySettings.data;
  const stepId = STEP_IDS[stepIndex] as WizardStepId;
  const translate = (key: string) => t(key as never);
  const previewFilenameCompatibility = settings?.filenameCompatibility ?? "preserve_original";
  const previewOutputFormat = settings?.outputFormat ?? defaultOutputFormatSettings();

  useEffect(() => {
    if (!settings) {
      return;
    }
    setFolderDraft({
      libraryRoot: settings.libraryRoot || "",
      outputRoot: settings.outputRoot || "",
    });
  }, [settings]);

  const outputFormat = previewOutputFormat;
  const previewAlbum = useMemo(() => samplePreviewAlbum(), []);
  const preview = useMemo(
    () => buildOutputPreviewTree(previewAlbum, outputFormat, previewFilenameCompatibility),
    [outputFormat, previewAlbum, previewFilenameCompatibility],
  );
  async function handleLanguageChange(nextLanguage: "en" | "ru") {
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

  async function handleSkip() {
    const payload = await librarySettings.saveOnboardingState(
      settings?.onboardingCompleted ?? false,
      settings?.onboardingCompleted ? false : true,
    );
    onExit("skip", payload);
  }

  async function handleFinish() {
    const payload = await librarySettings.saveOnboardingState(true, false);
    onExit("finish", payload);
  }

  async function handleFoldersNext() {
    if (!folderDraft.libraryRoot || !folderDraft.outputRoot) {
      return;
    }
    const payload = await librarySettings.saveLibraryRoots(folderDraft.libraryRoot, folderDraft.outputRoot);
    if (payload) {
      setStepIndex((current) => Math.min(current + 1, STEP_IDS.length - 1));
    }
  }

  if (librarySettings.loading && !settings) {
    return (
      <WizardShell>
        <Panel className="mx-auto w-full max-w-[560px] px-8 py-8 text-center">
          <h1 className="text-[22px] font-semibold text-[hsl(var(--text-strong))]">{t("app.onboarding.loadingTitle")}</h1>
          <p className="mt-3 text-[14px] leading-6 text-muted-foreground">{t("app.onboarding.loadingDetail")}</p>
        </Panel>
      </WizardShell>
    );
  }

  if (!settings) {
    return null;
  }

  const canAdvanceFromFolders = Boolean(folderDraft.libraryRoot && folderDraft.outputRoot);
  const isCanvasStep = stepId === "welcome" || stepId === "appearance";
  const previewFocus: PreviewFocusSection =
    stepId === "folders"
      ? "source"
      : stepId === "albums"
        ? "path"
        : stepId === "tracks"
          ? "tracks"
          : stepId === "safety"
            ? "rules"
            : "all";

  return (
    <WizardShell>
      <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-6 py-8 lg:px-8 xl:h-full xl:py-6">
        <div className="flex shrink-0 flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <BrandLogo className="h-14 w-14 shrink-0 rounded-[18px] shadow-card" />
            <div className="space-y-1.5">
              <p className="text-[12px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {t("app.onboarding.eyebrow")}
              </p>
              <h1 className="text-[28px] font-semibold leading-tight tracking-tight text-[hsl(var(--text-strong))]">
                {t(`app.onboarding.steps.${stepId}.title` as never)}
              </h1>
              <p className="max-w-[640px] text-[14px] leading-7 text-muted-foreground">
                {t(`app.onboarding.steps.${stepId}.description` as never)}
              </p>
            </div>
          </div>

          <button
            className="inline-flex h-10 shrink-0 items-center justify-center whitespace-nowrap rounded-full px-4 text-[13px] font-medium text-muted-foreground transition hover:bg-surface-subtle/70 hover:text-[hsl(var(--text-strong))]"
            type="button"
            onClick={() => void handleSkip()}
            disabled={librarySettings.saving}
          >
            {entrySource === "settings" ? t("app.onboarding.closeForNow") : t("app.onboarding.skip")}
          </button>
        </div>

        <div className="grid gap-6 xl:h-full xl:min-h-0 xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
          <Panel elevated className="flex flex-col overflow-hidden rounded-[30px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-subtle)/0.96),hsl(var(--surface-soft)/0.92))] px-0 py-0 xl:min-h-0">
            <div className="shrink-0 border-b border-border-soft/75 px-6 py-4">
              <WizardStepper
                steps={STEP_IDS.map((id) => ({ id, label: t(`app.onboarding.stepNames.${id}` as never) }))}
                currentIndex={stepIndex}
                counterLabel={t("app.onboarding.stepCounter", { current: stepIndex + 1, total: STEP_IDS.length })}
              />
            </div>

            <div className="flex-1 space-y-5 px-6 py-5 xl:min-h-0 xl:overflow-y-auto">
              {stepId === "welcome" ? (
                <div className="grid gap-4">
                  <LanguageCard
                    title="English"
                    detail={t("app.onboarding.languageEnglish")}
                    selected={settings.language === "en"}
                    onClick={() => void handleLanguageChange("en")}
                  />
                  <LanguageCard
                    title="Русский"
                    detail={t("app.onboarding.languageRussian")}
                    selected={settings.language === "ru"}
                    onClick={() => void handleLanguageChange("ru")}
                  />
                </div>
              ) : null}

              {stepId === "appearance" ? (
                <div className="space-y-5">
                  <section className="space-y-3">
                    <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      {t("app.onboarding.appearance.themeLabel")}
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {THEME_MODE_OPTIONS.map((option) => (
                        <ThemeModeCard
                          key={option.value}
                          label={t(option.labelKey)}
                          previewClassName={option.previewClassName}
                          selected={(settings.themeMode ?? themeMode) === option.value}
                          onClick={() => void handleThemeModeChange(option.value)}
                        />
                      ))}
                    </div>
                  </section>

                  <section className="space-y-3">
                    <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      {t("app.onboarding.appearance.accentLabel")}
                    </p>
                    <div className="appearance-swatch-group" role="radiogroup" aria-label={t("app.onboarding.appearance.accentLabel")}>
                      {ACCENT_OPTIONS.map((option) => (
                        <AppearanceSwatchButton
                          key={option.value}
                          disabled={librarySettings.saving}
                          label={t(option.labelKey)}
                          previewClassName="appearance-swatch-accent"
                          previewStyle={option.previewStyle}
                          selected={(settings.accentColor ?? accentColor) === option.value}
                          onClick={() => void handleAccentColorChange(option.value)}
                        />
                      ))}
                    </div>
                  </section>
                </div>
              ) : null}

              {stepId === "folders" ? (
                <div className="grid gap-4">
                  <FolderPickerCard
                    label={t("app.onboarding.folders.library")}
                    value={folderDraft.libraryRoot}
                    buttonLabel={t("app.onboarding.folders.pickLibrary")}
                    pickerAvailable={settings.pickerAvailable}
                    onPick={async () => {
                      const payload = await librarySettings.pickLibraryRoot();
                      if (payload?.libraryRoot) {
                        setFolderDraft((current) => ({ ...current, libraryRoot: payload.libraryRoot || "" }));
                      }
                    }}
                  />
                  <FolderPickerCard
                    label={t("app.onboarding.folders.output")}
                    value={folderDraft.outputRoot}
                    buttonLabel={t("app.onboarding.folders.pickOutput")}
                    pickerAvailable={settings.pickerAvailable}
                    onPick={async () => {
                      const payload = await librarySettings.pickOutputRoot();
                      if (payload?.libraryRoot) {
                        setFolderDraft((current) => ({ ...current, outputRoot: payload.libraryRoot || "" }));
                      }
                    }}
                  />
                </div>
              ) : null}

              {stepId === "albums" ? (
                <div className="grid gap-3">
                  {PRESET_OPTIONS.map((option) => (
                    <SelectionCard
                      key={option.value}
                      title={t(option.titleKey as never)}
                      description={t(option.descriptionKey as never)}
                      selected={settings.outputFormat.albumFolderPreset === option.value}
                      onClick={() => void librarySettings.saveOutputFormat({
                        ...settings.outputFormat,
                        albumFolderPreset: option.value,
                      })}
                    />
                  ))}
                </div>
              ) : null}

              {stepId === "tracks" ? (
                <div className="space-y-4">
                  <section className="space-y-3">
                    <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      {t("app.onboarding.trackNaming.patternLabel")}
                    </p>
                    <div className="grid gap-3">
                      {FILE_NAMING_OPTIONS.map((option) => (
                        <SelectionCard
                          key={option.titleKey}
                          title={t(option.titleKey as never)}
                          description={option.preview}
                          selected={settings.outputFormat.fileNaming === option.fileNaming && settings.outputFormat.separatorStyle === option.separatorStyle}
                          monospaceDescription
                          onClick={() => void librarySettings.saveOutputFormat({
                            ...settings.outputFormat,
                            fileNaming: option.fileNaming,
                            separatorStyle: option.separatorStyle,
                          })}
                        />
                      ))}
                    </div>
                  </section>

                  <section className="space-y-3">
                    <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      {t("app.onboarding.trackNaming.discsLabel")}
                    </p>
                    <div className="grid gap-3">
                      {DISC_HANDLING_OPTIONS.map((option) => (
                        <SelectionCard
                          key={option.value}
                          title={t(option.titleKey as never)}
                          selected={settings.outputFormat.discHandling === option.value}
                          onClick={() => void librarySettings.saveOutputFormat({
                            ...settings.outputFormat,
                            discHandling: option.value,
                          })}
                        />
                      ))}
                    </div>
                  </section>
                </div>
              ) : null}

              {stepId === "safety" ? (
                <div className="space-y-4">
                  <section className="space-y-3">
                    <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      {t("app.onboarding.safety.duplicatesLabel")}
                    </p>
                    <div className="grid gap-3">
                      {DUPLICATE_OPTIONS.map((option) => (
                        <SelectionCard
                          key={option.value}
                          title={t(option.titleKey as never)}
                          description={t(option.descriptionKey as never)}
                          selected={settings.duplicateHandling === option.value}
                          onClick={() => void librarySettings.saveDuplicateHandling(option.value)}
                        />
                      ))}
                    </div>
                  </section>

                  <section className="space-y-3">
                    <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                      {t("app.onboarding.safety.compatibilityLabel")}
                    </p>
                    <div className="grid gap-3">
                      {COMPATIBILITY_OPTIONS.map((option) => (
                        <SelectionCard
                          key={option.value}
                          title={t(option.titleKey as never)}
                          description={t(option.descriptionKey as never)}
                          selected={settings.filenameCompatibility === option.value}
                          onClick={() => void librarySettings.saveFilenameCompatibility(option.value)}
                        />
                      ))}
                    </div>
                  </section>
                </div>
              ) : null}

              {stepId === "review" ? (
                <div className="grid gap-4">
                  <SummaryCard label={t("app.onboarding.review.library")} value={settings.libraryRoot || "—"} />
                  <SummaryCard label={t("app.onboarding.review.output")} value={settings.outputRoot || "—"} />
                  <SummaryCard label={t("app.onboarding.review.albumFormat")} value={presetTitle(translate, settings.outputFormat.albumFolderPreset)} />
                  <SummaryCard label={t("app.onboarding.review.trackNaming")} value={trackNamingTitle(translate, settings.outputFormat.fileNaming)} />
                  <SummaryCard label={t("app.onboarding.review.duplicates")} value={duplicateHandlingTitle(translate, settings.duplicateHandling)} />
                  <SummaryCard label={t("app.onboarding.review.compatibility")} value={filenameCompatibilityTitle(translate, settings.filenameCompatibility)} />
                </div>
              ) : null}

              {librarySettings.error ? (
                <div className="flex items-start gap-2 rounded-[18px] border border-[hsl(var(--warning-border)/0.45)] bg-warning/10 px-4 py-3 text-[13px] text-[hsl(var(--warning-fg))]">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{librarySettings.error}</span>
                </div>
              ) : null}
            </div>

            <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border-soft/75 px-6 py-4">
              <button
                className="app-button-secondary inline-flex h-11 items-center justify-center gap-2 rounded-2xl px-4 text-[13px] font-semibold transition"
                type="button"
                onClick={() => setStepIndex((current) => Math.max(current - 1, 0))}
                disabled={stepIndex === 0 || librarySettings.saving}
              >
                <ArrowLeft className="h-4 w-4" />
                {t("app.onboarding.back")}
              </button>

              {stepId === "review" ? (
                <button
                  className="app-button-primary inline-flex h-11 items-center justify-center gap-2 rounded-2xl px-5 text-[13px] font-semibold transition"
                  type="button"
                  onClick={() => void handleFinish()}
                  disabled={librarySettings.saving}
                >
                  <Check className="h-4 w-4" />
                  {t("app.onboarding.finish")}
                </button>
              ) : (
                <button
                  className="app-button-primary inline-flex h-11 items-center justify-center gap-2 rounded-2xl px-5 text-[13px] font-semibold transition"
                  type="button"
                  onClick={() => {
                    if (stepId === "folders") {
                      void handleFoldersNext();
                      return;
                    }
                    setStepIndex((current) => Math.min(current + 1, STEP_IDS.length - 1));
                  }}
                  disabled={(stepId === "folders" && !canAdvanceFromFolders) || librarySettings.saving}
                >
                  {t("app.onboarding.next")}
                  <ArrowRight className="h-4 w-4" />
                </button>
              )}
            </div>
          </Panel>

          <Panel
            elevated
            className="flex min-h-0 flex-col overflow-hidden rounded-[30px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-contrast)/0.95),hsl(var(--surface-soft)/0.92))] px-0 py-0"
          >
            {isCanvasStep ? (
              <div className="flex-1 overflow-y-auto px-6 py-6 xl:min-h-0">
                {stepId === "welcome" ? (
                  <WelcomeCanvas
                    eyebrow={t("app.onboarding.eyebrow")}
                    features={[
                      { icon: FolderTree, title: t("app.onboarding.hero.feature1Title"), detail: t("app.onboarding.hero.feature1Detail") },
                      { icon: FileMusic, title: t("app.onboarding.hero.feature2Title"), detail: t("app.onboarding.hero.feature2Detail") },
                      { icon: ShieldCheck, title: t("app.onboarding.hero.feature3Title"), detail: t("app.onboarding.hero.feature3Detail") },
                    ]}
                  />
                ) : (
                  <AppearanceCanvas
                    themeModeName={t(themeMode === "light" ? "settings.themeModeOptions.light" : "settings.themeModeOptions.dark")}
                  />
                )}
              </div>
            ) : (
              <>
                <div className="shrink-0 border-b border-border-soft/75 px-6 py-4">
                  <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    {t("app.onboarding.previewLabel")}
                  </p>
                  <p className="mt-1 text-[13px] text-muted-foreground">{t("app.onboarding.previewDetail")}</p>
                </div>
                <div data-preview-scroll className="flex-1 overflow-y-auto px-6 py-6 xl:min-h-0">
                  <OutputPreviewMockup
                    album={previewAlbum}
                    albumFolderPreset={settings.outputFormat.albumFolderPreset}
                    discHandling={settings.outputFormat.discHandling}
                    duplicateHandling={settings.duplicateHandling}
                    fileNaming={settings.outputFormat.fileNaming}
                    filenameCompatibility={settings.filenameCompatibility}
                    focusSection={previewFocus}
                    outputRoot={folderDraft.outputRoot || settings.outputRoot}
                    preview={preview}
                    sourceRoot={folderDraft.libraryRoot || settings.libraryRoot}
                  />
                </div>
              </>
            )}
          </Panel>
        </div>
      </div>
    </WizardShell>
  );
}

function WizardShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground antialiased xl:h-screen">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-70"
        style={{
          background:
            "radial-gradient(120% 100% at 50% -10%, hsl(var(--accent) / 0.18), transparent 60%)",
        }}
      />
      <div className="relative xl:h-full">{children}</div>
    </div>
  );
}

function WizardStepper({
  steps,
  currentIndex,
  counterLabel,
}: {
  steps: Array<{ id: string; label: string }>;
  currentIndex: number;
  counterLabel: string;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[hsl(var(--text-strong))]">
          {steps[currentIndex]?.label}
        </p>
        <p className="text-[11px] font-medium text-muted-foreground">{counterLabel}</p>
      </div>
      <div className="flex items-center gap-1.5">
        {steps.map((step, index) => {
          const done = index < currentIndex;
          const active = index === currentIndex;
          return (
            <div
              key={step.id}
              className={cn(
                "h-1.5 flex-1 rounded-full transition-colors duration-300",
                done
                  ? "bg-[hsl(var(--accent)/0.55)]"
                  : active
                    ? "bg-[hsl(var(--accent))]"
                    : "bg-surface-strong/70",
              )}
            />
          );
        })}
      </div>
    </div>
  );
}

function WelcomeCanvas({
  eyebrow,
  features,
}: {
  eyebrow: string;
  features: Array<{ icon: ComponentType<{ className?: string }>; title: string; detail: string }>;
}) {
  return (
    <div className="flex flex-col gap-5">
      <div className="relative overflow-hidden rounded-[26px] border border-border-soft/70 bg-[linear-gradient(180deg,hsl(var(--surface-soft)/0.92),hsl(var(--surface-contrast)/0.82))] px-8 py-10 text-center">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-40"
          style={{ background: "radial-gradient(120% 80% at 50% -20%, hsl(var(--accent)/0.28), transparent 65%)" }}
        />
        <BrandLogo className="relative mx-auto h-[88px] w-[88px] rounded-[24px] shadow-card" />
        <p className="relative mt-6 text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">{eyebrow}</p>
        <p className="relative mt-2 text-[26px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">Musorg</p>
      </div>

      <div className="grid gap-3">
        {features.map((feature) => (
          <div
            key={feature.title}
            className="flex items-start gap-3 rounded-[20px] border border-border-soft/70 bg-surface-subtle/70 px-4 py-3.5"
          >
            <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[13px] border border-border-soft/60 bg-surface-contrast/70 text-[hsl(var(--brand-fg))]">
              <feature.icon className="h-[18px] w-[18px]" />
            </span>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-[hsl(var(--text-strong))]">{feature.title}</p>
              <p className="mt-0.5 text-[12px] leading-5 text-muted-foreground">{feature.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AppearanceCanvas({
  themeModeName,
}: {
  themeModeName: string;
}) {
  return (
    <div className="overflow-hidden rounded-[26px] border border-border-soft/75 bg-[linear-gradient(180deg,hsl(var(--surface-soft)/0.98),hsl(var(--surface-contrast)/0.9))] shadow-card">
      <div className="flex items-center gap-3 border-b border-border-soft/75 px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--danger-fg)/0.9)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--warning-fg)/0.9)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--success-fg)/0.9)]" />
        </div>
        <p className="text-[12px] font-medium text-muted-foreground">Musorg · {themeModeName}</p>
      </div>

      <div className="space-y-5 px-5 py-5">
        <div className="space-y-2">
          <div className="h-2.5 w-1/2 rounded-full bg-surface-strong/80" />
          <div className="h-2 w-3/4 rounded-full bg-surface-strong/55" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="relative rounded-[18px] border border-[hsl(var(--accent)/0.7)] bg-surface-selected/90 p-4 ring-1 ring-[hsl(var(--accent)/0.45)]">
            <SelectedBadge />
            <BrandLogo className="h-8 w-8 rounded-[10px]" />
            <div className="mt-3 h-2 w-3/4 rounded-full bg-surface-strong/70" />
            <div className="mt-1.5 h-2 w-1/2 rounded-full bg-surface-strong/45" />
          </div>
          <div className="rounded-[18px] border border-border-soft/70 bg-surface-subtle/70 p-4">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-[11px] border border-border-soft/60 bg-surface-contrast/70 text-muted-foreground">
              <FileMusic className="h-4 w-4" />
            </span>
            <div className="mt-3 h-2 w-3/4 rounded-full bg-surface-strong/55" />
            <div className="mt-1.5 h-2 w-1/2 rounded-full bg-surface-strong/35" />
          </div>
        </div>

        <div className="h-2 overflow-hidden rounded-full bg-surface-strong/40">
          <div className="h-full w-2/3 rounded-full bg-[hsl(var(--accent))]" />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-9 items-center rounded-full bg-[hsl(var(--accent))] px-4 text-[12px] font-semibold text-[hsl(var(--accent-foreground))]">Musorg</span>
          <span className="inline-flex h-9 items-center rounded-full border border-border-soft/70 bg-surface-field px-4 text-[12px] font-medium text-[hsl(var(--text-base))]">
            {themeModeName}
          </span>
          <span className="h-6 w-6 rounded-full bg-[hsl(var(--accent))]" />
          <span className="h-6 w-6 rounded-full bg-[hsl(var(--accent)/0.55)]" />
          <span className="h-6 w-6 rounded-full bg-[hsl(var(--accent)/0.3)]" />
        </div>
      </div>
    </div>
  );
}

function SelectedBadge() {
  return (
    <span className="absolute right-3 top-3 inline-flex h-6 w-6 items-center justify-center rounded-full bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))] shadow-card">
      <Check className="h-3.5 w-3.5" strokeWidth={3} />
    </span>
  );
}

function ThemeModeCard({
  label,
  previewClassName,
  selected,
  onClick,
}: {
  label: string;
  previewClassName: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        "group relative flex items-center gap-4 rounded-[22px] border px-4 py-3.5 text-left transition duration-200 hover:-translate-y-0.5",
        selected
          ? "border-[hsl(var(--accent)/0.7)] bg-surface-selected/90 shadow-card ring-1 ring-[hsl(var(--accent)/0.45)]"
          : "border-border-soft/80 bg-surface-subtle/80 hover:border-border-strong/80 hover:bg-surface-subtle hover:shadow-card",
      )}
      type="button"
      onClick={onClick}
    >
      {selected ? <SelectedBadge /> : null}
      <span className={cn("h-12 w-16 shrink-0 rounded-[14px] border shadow-card", previewClassName)} />
      <span className="text-[14px] font-semibold text-[hsl(var(--text-strong))]">{label}</span>
    </button>
  );
}

function AppearanceSwatchButton({
  disabled,
  label,
  onClick,
  previewClassName,
  previewStyle,
  selected,
}: {
  disabled: boolean;
  label: string;
  onClick: () => void;
  previewClassName: string;
  previewStyle?: SwatchStyle;
  selected: boolean;
}) {
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
      <span className={cn("appearance-swatch-circle", previewClassName)} style={previewStyle} />
      <span className="appearance-swatch-label">{label}</span>
    </button>
  );
}

function LanguageCard({
  title,
  detail,
  selected,
  onClick,
}: {
  title: string;
  detail: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        "group relative rounded-[24px] border px-5 py-5 text-left transition duration-200 hover:-translate-y-0.5",
        selected
          ? "border-[hsl(var(--accent)/0.7)] bg-surface-selected/90 shadow-card ring-1 ring-[hsl(var(--accent)/0.45)]"
          : "border-border-soft/80 bg-surface-subtle/85 hover:border-border-strong/70 hover:bg-surface-subtle hover:shadow-card",
      )}
      type="button"
      onClick={onClick}
    >
      {selected ? <SelectedBadge /> : null}
      <span
        className={cn(
          "inline-flex h-10 w-10 items-center justify-center rounded-[14px] border transition",
          selected
            ? "border-[hsl(var(--accent)/0.5)] bg-[hsl(var(--accent)/0.16)] text-[hsl(var(--brand-fg))]"
            : "border-border-soft/60 bg-surface-contrast/70 text-muted-foreground",
        )}
      >
        <Languages className="h-5 w-5" />
      </span>
      <p className="mt-3 text-[18px] font-semibold text-[hsl(var(--text-strong))]">{title}</p>
      <p className="mt-1.5 text-[13px] leading-6 text-muted-foreground">{detail}</p>
    </button>
  );
}

function FolderPickerCard({
  label,
  value,
  buttonLabel,
  pickerAvailable,
  onPick,
}: {
  label: string;
  value: string;
  buttonLabel: string;
  pickerAvailable: boolean;
  onPick: () => Promise<void>;
}) {
  const hasValue = Boolean(value);
  return (
    <div className="rounded-[24px] border border-border-soft/80 bg-surface-subtle/85 p-4">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex h-8 w-8 items-center justify-center rounded-[12px] border transition",
            hasValue
              ? "border-[hsl(var(--accent)/0.5)] bg-[hsl(var(--accent)/0.16)] text-[hsl(var(--brand-fg))]"
              : "border-border-soft/60 bg-surface-contrast/70 text-muted-foreground",
          )}
        >
          <Folder className="h-4 w-4" />
        </span>
        <p className="text-[12px] font-medium uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      </div>
      <div className="mt-3 flex min-h-[56px] items-center rounded-[18px] border border-border-soft/70 bg-surface-contrast/85 px-4 py-3">
        <p
          className={cn(
            "break-all text-[13px] leading-6",
            hasValue ? "text-[hsl(var(--text-base))]" : "text-muted-foreground",
          )}
        >
          {value || "—"}
        </p>
      </div>
      <button
        className="app-button-secondary mt-3 inline-flex h-11 w-full items-center justify-center rounded-2xl px-4 text-[13px] font-semibold transition"
        type="button"
        onClick={() => void onPick()}
        disabled={!pickerAvailable}
      >
        {buttonLabel}
      </button>
    </div>
  );
}

function SelectionCard({
  title,
  description,
  selected,
  onClick,
  monospaceDescription = false,
  footer,
}: {
  title: string;
  description?: string;
  selected: boolean;
  onClick: () => void;
  monospaceDescription?: boolean;
  footer?: ReactNode;
}) {
  return (
    <button
      className={cn(
        "group relative rounded-[22px] border px-4 py-3.5 text-left transition duration-200 hover:-translate-y-0.5",
        selected
          ? "border-[hsl(var(--accent)/0.7)] bg-surface-selected/90 shadow-card ring-1 ring-[hsl(var(--accent)/0.45)]"
          : "border-border-soft/80 bg-surface-subtle/80 hover:border-border-strong/80 hover:bg-surface-subtle hover:shadow-card",
      )}
      type="button"
      onClick={onClick}
    >
      {selected ? <SelectedBadge /> : null}
      <p className="pr-7 text-[14px] font-semibold text-[hsl(var(--text-strong))]">{title}</p>
      {description ? (
        <p
          className={cn(
            "mt-2 text-[12px] leading-6 text-muted-foreground",
            monospaceDescription &&
              "inline-block rounded-[10px] border border-border-soft/60 bg-surface-contrast/70 px-2 py-1 font-mono text-[hsl(var(--text-base))]",
          )}
        >
          {description}
        </p>
      ) : null}
      {footer}
    </button>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-border-soft/80 bg-surface-subtle/85 px-4 py-4">
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mt-2 break-all text-[14px] text-[hsl(var(--text-strong))]">{value}</p>
    </div>
  );
}

function presetTitle(t: (key: string) => string, value: OutputFormatSettings["albumFolderPreset"]) {
  return {
    artist_year_album: t("settings.outputFormat.presets.artistYearAlbum.title"),
    artist_album_year: t("settings.outputFormat.presets.artistAlbumYear.title"),
    artist_album: t("settings.outputFormat.presets.artistAlbum.title"),
    genre_artist_album: t("settings.outputFormat.presets.genreArtistAlbum.title"),
    custom: t("settings.outputFormat.presets.custom.title"),
  }[value];
}

function trackNamingTitle(t: (key: string) => string, value: FileNamingMode) {
  return {
    track_title: t("settings.outputFormat.fileNamingOptions.trackTitle.title"),
    artist_title: t("settings.outputFormat.fileNamingOptions.artistTitle.title"),
    track_artist_title: t("settings.outputFormat.fileNamingOptions.trackArtistTitle.title"),
    title_only: t("settings.outputFormat.fileNamingOptions.titleOnly.title"),
  }[value];
}

function duplicateHandlingTitle(t: (key: string) => string, value: DuplicateHandlingMode) {
  return {
    keep_everything: t("settings.duplicateHandling.options.keepEverything.title"),
    prefer_best_version: t("settings.duplicateHandling.options.preferBestVersion.title"),
    move_duplicates_to_archive: t("settings.duplicateHandling.options.moveDuplicatesToArchive.title"),
  }[value];
}

function filenameCompatibilityTitle(t: (key: string) => string, value: FilenameCompatibilityMode) {
  return {
    preserve_original: t("settings.filenameCompatibility.options.preserveOriginal.title"),
    cross_platform_safe: t("settings.filenameCompatibility.options.crossPlatformSafe.title"),
  }[value];
}
