import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, ArrowRight, Disc3, FileMusic, FolderTree, HardDriveDownload, Sparkles } from "lucide-react";
import { CoverImage } from "@/components/music/CoverImage";
import { useI18n } from "@/i18n/useI18n";
import { cn } from "@/lib/cn";
import { buildOutputPreviewMockupModel } from "@/lib/output-format";
import type {
  DuplicateHandlingMode,
  FilenameCompatibilityMode,
  FileNamingMode,
  OutputFormatSettings,
} from "@/types/music";
import type { OutputPreviewAlbum, OutputPreviewTree } from "@/lib/output-format";

interface OutputPreviewMockupProps {
  album: OutputPreviewAlbum;
  preview: OutputPreviewTree;
  albumFolderPreset: OutputFormatSettings["albumFolderPreset"];
  fileNaming: FileNamingMode;
  discHandling: OutputFormatSettings["discHandling"];
  duplicateHandling?: DuplicateHandlingMode | undefined;
  filenameCompatibility: FilenameCompatibilityMode;
  sourceRoot?: string | undefined;
  outputRoot?: string | undefined;
  className?: string | undefined;
  focusSection?: PreviewFocusSection | undefined;
}

export type PreviewFocusSection = "source" | "path" | "tracks" | "rules" | "all";

interface OutputPresetMiniPreviewProps {
  pathSegments: string[];
  fileExample?: string | undefined;
  className?: string | undefined;
}

export function OutputPreviewMockup({
  album,
  preview,
  albumFolderPreset,
  fileNaming,
  discHandling,
  duplicateHandling,
  filenameCompatibility,
  sourceRoot,
  outputRoot,
  className,
  focusSection = "all",
}: OutputPreviewMockupProps) {
  const { t } = useI18n();
  const translate = (key: string, values?: Record<string, string | number>) => t(key as never, values);
  const model = buildOutputPreviewMockupModel(album, preview);
  const fileExample = model.sampleTrackFilenames[0] ?? "01. Track Title.flac";
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = rootRef.current;
    const container = root?.closest("[data-preview-scroll]") as HTMLElement | null;
    if (!root || !container) {
      return;
    }
    const frame = requestAnimationFrame(() => {
      if (focusSection === "all") {
        container.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      const el = root.querySelector<HTMLElement>(`[data-section="${focusSection}"]`);
      if (!el) {
        return;
      }
      const containerRect = container.getBoundingClientRect();
      const elementRect = el.getBoundingClientRect();
      const pad = 20;
      const topWithin = elementRect.top - containerRect.top + container.scrollTop;
      const bottomWithin = topWithin + elementRect.height;
      const viewTop = container.scrollTop;
      const viewBottom = viewTop + container.clientHeight;
      let target = viewTop;
      if (elementRect.height + pad * 2 >= container.clientHeight) {
        target = topWithin - pad;
      } else if (bottomWithin > viewBottom - pad) {
        target = bottomWithin - container.clientHeight + pad;
      } else if (topWithin < viewTop + pad) {
        target = topWithin - pad;
      }
      container.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusSection]);
  const sectionClass = (id: PreviewFocusSection) =>
    cn(
      "rounded-[22px]",
      focusSection === "all" || focusSection === id ? "opacity-100" : "opacity-35",
      focusSection !== "all" && focusSection === id
        ? "outline outline-[1.5px] outline-offset-[3px] outline-[hsl(var(--accent)/0.7)]"
        : "outline-none",
    );
  const badges = [
    presetTitle(translate, albumFolderPreset),
    fileNamingTitle(translate, fileNaming),
    discHandlingTitle(translate, discHandling),
    filenameCompatibilityTitle(translate, filenameCompatibility),
    duplicateHandling ? duplicateHandlingTitle(translate, duplicateHandling) : null,
  ].filter(Boolean) as string[];

  return (
    <div
      ref={rootRef}
      data-testid="output-preview-mockup"
      className={cn(
        "overflow-hidden rounded-[26px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-soft)/0.98),hsl(var(--surface-contrast)/0.92))] shadow-card",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-border-soft/75 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--danger-fg)/0.9)]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--warning-fg)/0.9)]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--success-fg)/0.9)]" />
          </div>
          <p className="truncate text-[12px] font-medium text-muted-foreground">
            {t("settings.outputFormat.previewMockup.windowTitle")}
          </p>
        </div>
        <div className="app-pill rounded-full px-3 py-1 text-[10px]">
          {t("settings.outputFormat.previewMockup.liveLabel")}
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <div className="grid gap-4 md:grid-cols-[92px_minmax(0,1fr)]">
          <CoverImage
            alt={album.title}
            className="aspect-square h-[92px] w-[92px] rounded-[22px] border border-border-soft/75"
            compact
            src={album.coverUrl}
          />

          <div className="space-y-3">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[16px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">{album.title}</p>
                {!model.hasArtwork ? (
                  <span className="rounded-full border border-border-soft/75 bg-surface-contrast/80 px-2 py-0.5 text-[10px] text-muted-foreground">
                    {t("settings.outputFormat.previewMockup.noArtwork")}
                  </span>
                ) : null}
              </div>
              <p className="text-[13px] text-muted-foreground">
                {album.albumArtist} · {album.year} · {album.genre}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <StatPill icon={<FileMusic className="h-3.5 w-3.5" />} value={String(model.totalTracks)} label={t("settings.outputFormat.previewMockup.tracksStat")} />
              <StatPill icon={<Disc3 className="h-3.5 w-3.5" />} value={String(model.discCount)} label={t("settings.outputFormat.previewMockup.discsStat")} />
              <StatPill icon={<Sparkles className="h-3.5 w-3.5" />} value={String(badges.length)} label={t("settings.outputFormat.previewMockup.rulesStat")} />
            </div>
          </div>
        </div>

        <div data-section="source" className={cn("grid gap-3 md:grid-cols-2", sectionClass("source"))}>
          <SourceCard
            icon={<FolderTree className="h-4 w-4 text-[hsl(var(--info-fg))]" />}
            label={t("settings.outputFormat.previewMockup.sourceLabel")}
            value={sourceRoot || t("settings.outputFormat.previewMockup.sourcePlaceholder")}
            muted={!sourceRoot}
          />
          <SourceCard
            icon={<HardDriveDownload className="h-4 w-4 text-[hsl(var(--success-fg))]" />}
            label={t("settings.outputFormat.previewMockup.destinationLabel")}
            value={outputRoot || t("settings.outputFormat.previewMockup.destinationPlaceholder")}
            muted={!outputRoot}
          />
        </div>

        <div data-section="path" className={cn("rounded-[22px] border border-border-soft/75 bg-surface-subtle/80 p-4", sectionClass("path"))}>
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t("settings.outputFormat.previewMockup.pathLabel")}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="output-preview-path">
            {model.pathSegments.map((segment, index) => (
              <PathSegment key={`${segment}-${index}`} label={segment} showArrow={index < model.pathSegments.length - 1} />
            ))}
          </div>
          <div className="mt-4 rounded-[18px] border border-border-soft/70 bg-surface-contrast/80 px-3 py-3">
            <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
              {t("settings.outputFormat.previewMockup.fileExampleLabel")}
            </p>
            <p className="mt-1 break-all font-mono text-[12px] text-[hsl(var(--text-strong))]">{fileExample}</p>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div data-section="tracks" className={cn("rounded-[22px] border border-border-soft/75 bg-surface-subtle/80 p-4", sectionClass("tracks"))}>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {t("settings.outputFormat.previewMockup.trackExamplesLabel")}
            </p>
            <div className="mt-3 space-y-2">
              {model.sampleTrackFilenames.map((filename, index) => (
                <div
                  key={`${filename}-${index}`}
                  className="flex items-center gap-2 rounded-[14px] border border-border-soft/70 bg-surface-contrast/75 px-3 py-2.5"
                >
                  <FileMusic className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 truncate font-mono text-[12px] text-[hsl(var(--text-base))]">{filename}</span>
                </div>
              ))}
              {model.discFolders.length ? (
                <div className="rounded-[14px] border border-[hsl(var(--info-border)/0.44)] bg-info px-3 py-2.5 text-[12px] text-info-foreground">
                  {t("settings.outputFormat.previewMockup.discFoldersLabel")}: {model.discFolders.join(", ")}
                </div>
              ) : null}
            </div>
          </div>

          <div data-section="rules" className={cn("space-y-3", sectionClass("rules"))}>
            <div className="rounded-[22px] border border-border-soft/75 bg-surface-subtle/80 p-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {t("settings.outputFormat.previewMockup.rulesLabel")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {badges.map((badge) => (
                  <span
                    key={badge}
                    className="rounded-full border border-border-soft/75 bg-surface-contrast/85 px-3 py-1.5 text-[11px] text-[hsl(var(--text-base))]"
                  >
                    {badge}
                  </span>
                ))}
              </div>
            </div>

            {model.warningSummary ? (
              <div className="rounded-[22px] border border-[hsl(var(--warning-border)/0.45)] bg-warning/10 p-4 text-[hsl(var(--warning-fg))]">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold">{t("settings.outputFormat.previewMockup.warningLabel")}</p>
                    <p className="mt-1 text-[12px] leading-5">{model.warningSummary}</p>
                    {model.warnings[0]?.message ? (
                      <p className="mt-1 text-[11px] leading-5 opacity-90">{model.warnings[0].message}</p>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-[22px] border border-[hsl(var(--success-border)/0.4)] bg-success/10 p-4 text-[hsl(var(--success-fg))]">
                <p className="text-[12px] font-semibold">{t("settings.outputFormat.previewMockup.readyLabel")}</p>
                <p className="mt-1 text-[12px] leading-5">{t("settings.outputFormat.previewMockup.readyDescription")}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function OutputPresetMiniPreview({ pathSegments, fileExample, className }: OutputPresetMiniPreviewProps) {
  return (
    <div className={cn("mt-4 rounded-[18px] border border-border-soft/70 bg-surface-contrast/80 p-3", className)}>
      <div className="flex flex-wrap items-center gap-1.5">
        {pathSegments.map((segment, index) => (
          <PathSegment key={`${segment}-${index}`} compact label={segment} showArrow={index < pathSegments.length - 1} />
        ))}
      </div>
      {fileExample ? (
        <div className="mt-3 flex items-center gap-2 rounded-[12px] border border-border-soft/60 bg-surface-soft/75 px-2.5 py-2">
          <FileMusic className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 truncate font-mono text-[11px] text-[hsl(var(--text-base))]">{fileExample}</span>
        </div>
      ) : null}
    </div>
  );
}

function StatPill({ icon, value, label }: { icon: ReactNode; value: string; label: string }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border-soft/75 bg-surface-contrast/80 px-3 py-1.5 text-[11px] text-[hsl(var(--text-base))]">
      <span className="text-muted-foreground">{icon}</span>
      <span className="font-semibold text-[hsl(var(--text-strong))]">{value}</span>
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

function SourceCard({
  icon,
  label,
  value,
  muted,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="rounded-[20px] border border-border-soft/75 bg-surface-subtle/80 p-4">
      <div className="flex items-center gap-2">
        {icon}
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      </div>
      <p className={cn("mt-3 break-all text-[12px] leading-6", muted ? "text-muted-foreground" : "text-[hsl(var(--text-strong))]")}>
        {value}
      </p>
    </div>
  );
}

function PathSegment({ label, compact = false, showArrow = true }: { label: string; compact?: boolean; showArrow?: boolean }) {
  return (
    <>
      <span
        className={cn(
          "rounded-full border border-border-soft/75 bg-surface-contrast/88 text-[hsl(var(--text-strong))]",
          compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-[11px]",
        )}
      >
        {label}
      </span>
      {!compact && showArrow ? <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" /> : null}
    </>
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

function fileNamingTitle(t: (key: string) => string, value: FileNamingMode) {
  return {
    track_title: t("settings.outputFormat.fileNamingOptions.trackTitle.title"),
    artist_title: t("settings.outputFormat.fileNamingOptions.artistTitle.title"),
    track_artist_title: t("settings.outputFormat.fileNamingOptions.trackArtistTitle.title"),
    title_only: t("settings.outputFormat.fileNamingOptions.titleOnly.title"),
  }[value];
}

function discHandlingTitle(t: (key: string) => string, value: OutputFormatSettings["discHandling"]) {
  return {
    keep_together: t("settings.outputFormat.discOptions.keepTogether.title"),
    flatten: t("settings.outputFormat.discOptions.flatten.title"),
    prefix_disc: t("settings.outputFormat.discOptions.prefixDisc.title"),
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
