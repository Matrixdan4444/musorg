import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ChevronDown, FileMusic, Folder, FolderOpen, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { FieldHelp } from "@/components/FieldHelp";
import { Panel } from "@/components/Panel";
import { useI18n } from "@/i18n/useI18n";
import {
  albumFolderPresetOrder,
  buildOutputPreviewTree,
  collapseDuplicateLeadingYear,
  defaultOutputFormatSettings,
  discHandlingOrder,
  fileNamingOrder,
  previewAlbumFromWorkspace,
  samplePreviewAlbum,
  separatorStyleOrder,
} from "@/lib/output-format";
import { cn } from "@/lib/cn";
import type { AlbumFolderPreset, AlbumInspectorData, FilenameCompatibilityMode, OutputFormatSettings, OutputFormatToken, TrackRow } from "@/types/music";

interface OutputFolderFormatCardProps {
  value: OutputFormatSettings | null | undefined;
  saving: boolean;
  onChange: (value: OutputFormatSettings) => Promise<void> | void;
  previewInspector: AlbumInspectorData | null;
  previewTracks: TrackRow[];
  filenameCompatibility?: FilenameCompatibilityMode;
}

const tokenPalette: OutputFormatToken[] = ["artist", "album", "year", "genre", "disc", "track_number", "title"];
const recommendedPreset: AlbumFolderPreset = "artist_year_album";

export function OutputFolderFormatCard({
  value,
  saving,
  onChange,
  previewInspector,
  previewTracks,
  filenameCompatibility = "preserve_original",
}: OutputFolderFormatCardProps) {
  const { t } = useI18n();
  const translate = (key: string, values?: Record<string, string | number>) => t(key as never, values);
  const [draft, setDraft] = useState<OutputFormatSettings>(value ?? defaultOutputFormatSettings());
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);

  useEffect(() => {
    setDraft(value ?? defaultOutputFormatSettings());
  }, [value]);

  const previewAlbum = useMemo(
    () => previewAlbumFromWorkspace(previewInspector ? {
      title: previewInspector.title,
      artist: previewInspector.artist,
      albumArtist: previewInspector.albumArtist,
      year: previewInspector.year,
      genre: previewInspector.genre,
      coverUrl: previewInspector.coverUrl,
      disc: previewInspector.disc,
      tracks: previewTracks,
    } : null) ?? samplePreviewAlbum(),
    [previewInspector, previewTracks],
  );

  const preview = useMemo(
    () => buildOutputPreviewTree(previewAlbum, draft, filenameCompatibility),
    [draft, filenameCompatibility, previewAlbum],
  );
  const folderPresetCards = useMemo(() => buildFolderPresetCards(translate, previewAlbum), [previewAlbum, t]);
  const discOptions = useMemo(() => buildDiscOptions(translate), [t]);
  const fileNamingOptions = useMemo(() => buildFileNamingOptions(translate), [t]);
  const separatorOptions = useMemo(() => buildSeparatorOptions(translate), [t]);

  async function update(next: OutputFormatSettings) {
    setDraft(next);
    await onChange(next);
  }

  async function appendToken(token: OutputFormatToken) {
    await update({
      ...draft,
      customAlbumPattern: [...draft.customAlbumPattern, token],
      albumFolderPreset: "custom",
    });
  }

  async function removeToken(index: number) {
    await update({
      ...draft,
      customAlbumPattern: draft.customAlbumPattern.filter((_, tokenIndex) => tokenIndex !== index),
      albumFolderPreset: "custom",
    });
  }

  async function addFolderBreak() {
    await update({
      ...draft,
      customAlbumPattern: [...draft.customAlbumPattern, "folder_break"],
      albumFolderPreset: "custom",
    });
  }

  return (
    <Panel elevated className="overflow-hidden rounded-[30px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-subtle)/0.96),hsl(var(--surface-soft)/0.92))] px-0 py-0">
      <div className="border-b border-border-soft/75 px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("settings.outputFormat.eyebrow")}
            </p>
            <h2 className="text-[18px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
              {t("settings.outputFormat.title")}
            </h2>
            <p className="max-w-[620px] text-[13px] text-muted-foreground">
              {t("settings.outputFormat.subtitle")}
            </p>
          </div>
          <div className="app-pill rounded-full px-3 py-1.5 text-[11px]">
            {saving ? t("common.saving") : t("common.ready")}
          </div>
        </div>
      </div>

      <div className="space-y-8 px-6 py-7">
        <section className="space-y-5">
          <SectionLabel label={t("settings.outputFormat.simpleLabel")} />
          <div className="space-y-4">
            <SectionHeader
              title={t("settings.outputFormat.albumFormatTitle")}
              helpLabel={t("settings.outputFormat.albumFormatHelpLabel")}
              helpDescription={t("settings.outputFormat.albumFormatHelp")}
            />

            <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {albumFolderPresetOrder.map((preset) => {
                const card = folderPresetCards[preset];
                const selected = draft.albumFolderPreset === preset;
                return (
                  <motion.button
                    key={preset}
                    whileHover={{ y: -1 }}
                    whileTap={{ scale: 0.995 }}
                    className={cn(
                      "rounded-[22px] border px-4 py-4 text-left transition",
                      selected
                        ? "border-[hsl(var(--info-border)/0.48)] bg-surface-selected/90 shadow-card"
                        : "border-border-soft/80 bg-surface-subtle/80 hover:border-border-strong/80 hover:bg-surface-subtle",
                    )}
                    type="button"
                    onClick={() => void update({ ...draft, albumFolderPreset: preset })}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-[14px] font-semibold text-[hsl(var(--text-strong))]">{card.title}</p>
                          {preset === recommendedPreset ? (
                            <span className="rounded-full border border-[hsl(var(--info-border)/0.44)] bg-info px-2 py-0.5 text-[10px] font-medium text-info-foreground">
                              {t("settings.outputFormat.recommended")}
                            </span>
                          ) : null}
                        </div>
                        <p className="text-[12px] text-muted-foreground">{card.description}</p>
                      </div>
                      {selected ? (
                        <span className="rounded-full bg-surface-strong px-2 py-1 text-[10px] text-[hsl(var(--text-strong))]">
                          {t("settings.outputFormat.selected")}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-4 rounded-[18px] bg-surface-contrast/85 px-3 py-2.5">
                      {card.preview.map((line) => (
                        <p key={line} className="break-words font-mono text-[11px] leading-5 text-[hsl(var(--text-base))]">
                          {line}
                        </p>
                      ))}
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <SectionHeader
            title={t("settings.outputFormat.previewTitle")}
            helpLabel={t("settings.outputFormat.previewHelpLabel")}
            helpDescription={t("settings.outputFormat.previewHelp")}
          />

          <div className="overflow-hidden rounded-[28px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-contrast)/0.95),hsl(var(--surface-soft)/0.92))]">
            <div className="border-b border-border-soft/75 px-5 py-4">
              <p className="text-[12px] text-muted-foreground">{t("settings.outputFormat.previewSubtitle")}</p>
            </div>

            <div className="space-y-3 px-5 py-5">
              <div className="space-y-0.5">
                {preview.tree.map((node, index) => (
                  <div
                    key={`${node.label}-${index}`}
                    className="flex items-start gap-2.5"
                    style={{ paddingLeft: `${node.depth * 16}px` }}
                  >
                    <span className="mt-[3px] shrink-0">
                      {node.kind === "folder"
                        ? index === preview.tree.findIndex((entry) => entry.label === node.label && entry.depth === node.depth)
                          ? <FolderOpen className="h-4 w-4 text-[hsl(var(--info-fg))]" />
                          : <Folder className="h-4 w-4 text-[hsl(var(--info-fg))]" />
                        : <FileMusic className="h-4 w-4 text-muted-foreground" />}
                    </span>
                    <span
                      className={cn(
                        "min-w-0 break-words text-[13px] leading-6",
                        node.kind === "folder" ? "text-[hsl(var(--text-strong))]" : "text-[hsl(var(--text-base))]",
                      )}
                    >
                      {node.label}
                    </span>
                  </div>
                ))}
              </div>

              {preview.warnings.length ? (
                <div className="border-t border-border-soft/75 pt-3">
                  {preview.warnings.map((warning) => (
                    <div key={warning.id} className="flex items-start gap-2 text-[12px] leading-5 text-[hsl(var(--warning-fg))]">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--warning-fg))]" />
                      <div>
                        <p className="font-medium text-[hsl(var(--warning-fg))]">{warning.title}</p>
                        <p>{warning.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <section className="border-t border-border-soft/75 pt-6">
          <button
            className="flex w-full items-center justify-between gap-3 text-left"
            type="button"
            onClick={() => setAdvancedOpen((current) => !current)}
          >
            <div className="space-y-1">
              <SectionLabel label={t("settings.outputFormat.advancedLabel")} />
              <p className="text-[12px] text-muted-foreground">{t("settings.outputFormat.advancedSubtitle")}</p>
            </div>
            <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition", advancedOpen && "rotate-180")} />
          </button>

          <AnimatePresence initial={false}>
            {advancedOpen ? (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="space-y-6 pt-5">
                  <AdvancedSection
                    title={t("settings.outputFormat.discTitle")}
                    helpLabel={t("settings.outputFormat.discHelpLabel")}
                    helpDescription={t("settings.outputFormat.discHelp")}
                  >
                    <div className="space-y-2">
                      {discHandlingOrder.map((option) => {
                        const config = discOptions[option];
                        const selected = draft.discHandling === option;
                        return (
                          <button
                            key={option}
                            className={cn(
                              "flex w-full items-center justify-between gap-4 rounded-[16px] border px-4 py-3 text-left transition",
                              selected ? "border-[hsl(var(--info-border)/0.5)] bg-surface-selected/90" : "border-border-soft/80 bg-surface-subtle/80 hover:bg-surface-subtle",
                            )}
                            type="button"
                            onClick={() => void update({ ...draft, discHandling: option })}
                          >
                            <div className="min-w-0">
                              <p className="text-[13px] font-medium text-[hsl(var(--text-strong))]">{config.title}</p>
                              <p className="mt-1 font-mono text-[11px] text-muted-foreground">{config.preview.join("  ")}</p>
                            </div>
                            {config.warning ? <AlertTriangle className="h-4 w-4 shrink-0 text-[hsl(var(--warning-fg))]" /> : null}
                          </button>
                        );
                      })}
                    </div>
                  </AdvancedSection>

                  <AdvancedSection
                    title={t("settings.outputFormat.fileNamingTitle")}
                    helpLabel={t("settings.outputFormat.fileNamingHelpLabel")}
                    helpDescription={t("settings.outputFormat.fileNamingHelp")}
                  >
                    <div className="flex flex-wrap gap-2">
                      {fileNamingOrder.map((option) => {
                        const config = fileNamingOptions[option];
                        const selected = draft.fileNaming === option;
                        return (
                          <button
                            key={option}
                            className={cn(
                              "rounded-[16px] border px-3 py-2 text-left transition",
                              selected ? "border-[hsl(var(--info-border)/0.5)] bg-surface-selected/90" : "border-border-soft/80 bg-surface-subtle/80 hover:bg-surface-subtle",
                            )}
                            type="button"
                            onClick={() => void update({ ...draft, fileNaming: option })}
                          >
                            <p className="text-[12px] font-medium text-[hsl(var(--text-strong))]">{config.title}</p>
                            <p className="mt-1 font-mono text-[11px] text-muted-foreground">{config.preview}</p>
                          </button>
                        );
                      })}
                    </div>
                  </AdvancedSection>

                  <AdvancedSection
                    title={t("settings.outputFormat.separatorTitle")}
                    helpLabel={t("settings.outputFormat.separatorHelpLabel")}
                    helpDescription={t("settings.outputFormat.separatorHelp")}
                  >
                    <div className="inline-flex flex-wrap gap-2 rounded-[18px] border border-border-soft/80 bg-surface-subtle/85 p-2">
                      {separatorStyleOrder.map((option) => {
                        const config = separatorOptions[option];
                        const selected = draft.separatorStyle === option;
                        return (
                          <button
                            key={option}
                            className={cn(
                              "rounded-[14px] px-3 py-1.5 text-left transition",
                              selected ? "bg-surface-strong text-[hsl(var(--text-strong))]" : "text-muted-foreground hover:bg-surface-subtle",
                            )}
                            type="button"
                            onClick={() => void update({ ...draft, separatorStyle: option })}
                          >
                            <p className="text-[12px] font-medium">{config.title}</p>
                            <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">{config.preview}</p>
                          </button>
                        );
                      })}
                    </div>
                  </AdvancedSection>

                  <AdvancedSection
                    title={t("settings.outputFormat.customTitle")}
                    helpLabel={t("settings.outputFormat.customHelpLabel")}
                    helpDescription={t("settings.outputFormat.customHelp")}
                  >
                    <div className="rounded-[20px] border border-border-soft/80 bg-surface-subtle/85 p-4">
                      <button
                        className="flex w-full items-center justify-between gap-3 text-left"
                        type="button"
                        onClick={() => setCustomOpen((current) => !current)}
                      >
                        <div>
                          <p className="text-[13px] font-medium text-[hsl(var(--text-strong))]">{t("settings.outputFormat.customBuilderTitle")}</p>
                          <p className="mt-1 text-[12px] text-muted-foreground">{t("settings.outputFormat.customSubtitle")}</p>
                        </div>
                        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition", customOpen && "rotate-180")} />
                      </button>

                      <AnimatePresence initial={false}>
                        {customOpen ? (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="mt-4 space-y-4 border-t border-border-soft/75 pt-4">
                              <div className="space-y-2">
                                <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                                  {t("settings.outputFormat.customStructureLabel")}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                  {draft.customAlbumPattern.length === 0 ? (
                                    <span className="text-[12px] text-muted-foreground">{t("settings.outputFormat.customEmpty")}</span>
                                  ) : null}
                                  {draft.customAlbumPattern.map((token, index) => (
                                    <button
                                      key={`${token}-${index}`}
                                      className={cn(
                                        "group inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] transition",
                                        token === "folder_break"
                                          ? "border-[hsl(var(--info-border)/0.44)] bg-info text-info-foreground"
                                          : "border-border-soft/80 bg-surface-soft/90 text-[hsl(var(--text-strong))]",
                                      )}
                                      type="button"
                                      onClick={() => void removeToken(index)}
                                    >
                                      {token === "folder_break" ? "/" : t(`settings.outputFormat.tokens.${token}` as never)}
                                      <X className="h-3 w-3 opacity-50 transition group-hover:opacity-100" />
                                    </button>
                                  ))}
                                </div>
                              </div>

                              <div className="rounded-[14px] border border-border-soft/70 bg-surface-soft/70 px-3 py-2.5">
                                <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                                  {t("settings.outputFormat.customPathPreviewLabel")}
                                </p>
                                <p className="mt-1 break-all font-mono text-[12px] text-[hsl(var(--text-strong))]">
                                  {preview.albumRootLabel || "—"}
                                </p>
                              </div>

                              <div className="space-y-2">
                                <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                                  {t("settings.outputFormat.customAddLabel")}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                  {tokenPalette.map((token) => (
                                    <button
                                      key={token}
                                      className="rounded-full border border-border-soft/80 bg-surface-soft/90 px-3 py-1.5 text-[12px] text-[hsl(var(--text-base))] transition hover:bg-surface-subtle"
                                      type="button"
                                      onClick={() => void appendToken(token)}
                                    >
                                      {t(`settings.outputFormat.tokens.${token}` as never)}
                                    </button>
                                  ))}
                                  <button
                                    className="rounded-full border border-[hsl(var(--info-border)/0.44)] bg-info px-3 py-1.5 text-[12px] text-info-foreground transition hover:brightness-110"
                                    type="button"
                                    onClick={() => void addFolderBreak()}
                                  >
                                    {t("settings.outputFormat.addFolderBreak")}
                                  </button>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                  {t("settings.outputFormat.customHint")}
                                </p>
                              </div>
                            </div>
                          </motion.div>
                        ) : null}
                      </AnimatePresence>
                    </div>
                  </AdvancedSection>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </section>
      </div>
    </Panel>
  );
}

function SectionLabel({ label }: { label: string }) {
  return <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>;
}

function SectionHeader({ title, helpLabel, helpDescription }: { title: string; helpLabel: string; helpDescription: string }) {
  return (
    <div className="flex items-center gap-2">
      <h3 className="text-[15px] font-semibold text-[hsl(var(--text-strong))]">{title}</h3>
      <FieldHelp label={helpLabel} description={helpDescription} />
    </div>
  );
}

function AdvancedSection({
  title,
  helpLabel,
  helpDescription,
  children,
}: {
  title: string;
  helpLabel: string;
  helpDescription: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-3">
      <SectionHeader title={title} helpLabel={helpLabel} helpDescription={helpDescription} />
      {children}
    </div>
  );
}

function buildFolderPresetCards(t: (key: string, values?: Record<string, string | number>) => string, album: ReturnType<typeof samplePreviewAlbum>) {
  return {
    artist_year_album: {
      title: t("settings.outputFormat.presets.artistYearAlbum.title"),
      description: t("settings.outputFormat.presets.artistYearAlbum.description"),
      preview: [`${album.albumArtist}/${collapseDuplicateLeadingYear(`${album.year} - ${album.title}`)}`],
    },
    artist_album_year: {
      title: t("settings.outputFormat.presets.artistAlbumYear.title"),
      description: t("settings.outputFormat.presets.artistAlbumYear.description"),
      preview: [`${album.albumArtist}/${album.title} (${album.year})`],
    },
    artist_album: {
      title: t("settings.outputFormat.presets.artistAlbum.title"),
      description: t("settings.outputFormat.presets.artistAlbum.description"),
      preview: [`${album.albumArtist}/${album.title}`],
    },
    genre_artist_album: {
      title: t("settings.outputFormat.presets.genreArtistAlbum.title"),
      description: t("settings.outputFormat.presets.genreArtistAlbum.description"),
      preview: [`${album.genre}/${album.albumArtist}/${album.title}`],
    },
    custom: {
      title: t("settings.outputFormat.presets.custom.title"),
      description: t("settings.outputFormat.presets.custom.description"),
      preview: [t("settings.outputFormat.presets.custom.preview")],
    },
  } as const;
}

function buildDiscOptions(t: (key: string, values?: Record<string, string | number>) => string) {
  return {
    keep_together: {
      title: t("settings.outputFormat.discOptions.keepTogether.title"),
      preview: ["CD1/", "CD2/"],
      warning: false,
    },
    flatten: {
      title: t("settings.outputFormat.discOptions.flatten.title"),
      preview: ["01. Track.flac", "02. Track.flac"],
      warning: true,
    },
    prefix_disc: {
      title: t("settings.outputFormat.discOptions.prefixDisc.title"),
      preview: ["1-01 - Track.flac", "2-01 - Track.flac"],
      warning: false,
    },
  } as const;
}

function buildFileNamingOptions(t: (key: string, values?: Record<string, string | number>) => string) {
  return {
    track_title: { title: t("settings.outputFormat.fileNamingOptions.trackTitle.title"), preview: "01. Track.flac" },
    artist_title: { title: t("settings.outputFormat.fileNamingOptions.artistTitle.title"), preview: "Artist. Track.flac" },
    track_artist_title: { title: t("settings.outputFormat.fileNamingOptions.trackArtistTitle.title"), preview: "01. Artist. Track.flac" },
    title_only: { title: t("settings.outputFormat.fileNamingOptions.titleOnly.title"), preview: "Track.flac" },
  } as const;
}

function buildSeparatorOptions(t: (key: string, values?: Record<string, string | number>) => string) {
  return {
    hyphen: { title: t("settings.outputFormat.separatorOptions.hyphen.title"), preview: "01 - Track" },
    dot: { title: t("settings.outputFormat.separatorOptions.dot.title"), preview: "01. Track" },
    space: { title: t("settings.outputFormat.separatorOptions.space.title"), preview: "01 Track" },
    minimal: { title: t("settings.outputFormat.separatorOptions.minimal.title"), preview: "01 Track" },
  } as const;
}
