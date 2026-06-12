import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { FieldHelp } from "@/components/FieldHelp";
import { Panel } from "@/components/Panel";
import { useI18n } from "@/i18n/useI18n";
import { artworkQualityControlsEnabled, defaultMetadataPreservationSettings } from "@/lib/metadata-preservation";
import { cn } from "@/lib/cn";
import type { MetadataPreservationSettings } from "@/types/music";

interface MetadataPreservationCardProps {
  value: MetadataPreservationSettings | null | undefined;
  saving: boolean;
  onChange: (value: MetadataPreservationSettings) => Promise<void> | void;
}

type MetadataSectionKey = keyof MetadataPreservationSettings;
type MetadataFieldKey<T extends MetadataSectionKey> = keyof MetadataPreservationSettings[T];

interface ToggleField<T extends MetadataSectionKey> {
  key: MetadataFieldKey<T>;
  labelKey: string;
  helpLabelKey: string;
  helpKey: string;
  disabled?: boolean;
}

export function MetadataPreservationCard({ value, saving, onChange }: MetadataPreservationCardProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<MetadataPreservationSettings>(value ?? defaultMetadataPreservationSettings());

  useEffect(() => {
    setDraft(value ?? defaultMetadataPreservationSettings());
  }, [value]);

  const artworkPowerEnabled = artworkQualityControlsEnabled(draft);

  async function toggleField<T extends MetadataSectionKey>(section: T, key: MetadataFieldKey<T>, disabled = false) {
    if (disabled) {
      return;
    }

    const next = {
      ...draft,
      [section]: {
        ...draft[section],
        [key]: !draft[section][key],
      },
    } as MetadataPreservationSettings;

    setDraft(next);
    await onChange(next);
  }

  const coreFields: ToggleField<"core">[] = [
    { key: "trackTitle", labelKey: "settings.metadataPreservation.fields.trackTitle.label", helpLabelKey: "settings.metadataPreservation.fields.trackTitle.helpLabel", helpKey: "settings.metadataPreservation.fields.trackTitle.help" },
    { key: "trackArtist", labelKey: "settings.metadataPreservation.fields.trackArtist.label", helpLabelKey: "settings.metadataPreservation.fields.trackArtist.helpLabel", helpKey: "settings.metadataPreservation.fields.trackArtist.help" },
    { key: "albumTitle", labelKey: "settings.metadataPreservation.fields.albumTitle.label", helpLabelKey: "settings.metadataPreservation.fields.albumTitle.helpLabel", helpKey: "settings.metadataPreservation.fields.albumTitle.help" },
    { key: "albumArtist", labelKey: "settings.metadataPreservation.fields.albumArtist.label", helpLabelKey: "settings.metadataPreservation.fields.albumArtist.helpLabel", helpKey: "settings.metadataPreservation.fields.albumArtist.help" },
    { key: "trackNumber", labelKey: "settings.metadataPreservation.fields.trackNumber.label", helpLabelKey: "settings.metadataPreservation.fields.trackNumber.helpLabel", helpKey: "settings.metadataPreservation.fields.trackNumber.help" },
    { key: "discNumber", labelKey: "settings.metadataPreservation.fields.discNumber.label", helpLabelKey: "settings.metadataPreservation.fields.discNumber.helpLabel", helpKey: "settings.metadataPreservation.fields.discNumber.help" },
    { key: "discTotal", labelKey: "settings.metadataPreservation.fields.discTotal.label", helpLabelKey: "settings.metadataPreservation.fields.discTotal.helpLabel", helpKey: "settings.metadataPreservation.fields.discTotal.help" },
  ];

  const releaseFields: ToggleField<"release">[] = [
    { key: "releaseDate", labelKey: "settings.metadataPreservation.fields.releaseDate.label", helpLabelKey: "settings.metadataPreservation.fields.releaseDate.helpLabel", helpKey: "settings.metadataPreservation.fields.releaseDate.help" },
    { key: "genre", labelKey: "settings.metadataPreservation.fields.genre.label", helpLabelKey: "settings.metadataPreservation.fields.genre.helpLabel", helpKey: "settings.metadataPreservation.fields.genre.help" },
    { key: "releaseType", labelKey: "settings.metadataPreservation.fields.releaseType.label", helpLabelKey: "settings.metadataPreservation.fields.releaseType.helpLabel", helpKey: "settings.metadataPreservation.fields.releaseType.help" },
    { key: "explicit", labelKey: "settings.metadataPreservation.fields.explicit.label", helpLabelKey: "settings.metadataPreservation.fields.explicit.helpLabel", helpKey: "settings.metadataPreservation.fields.explicit.help" },
    { key: "compilation", labelKey: "settings.metadataPreservation.fields.compilation.label", helpLabelKey: "settings.metadataPreservation.fields.compilation.helpLabel", helpKey: "settings.metadataPreservation.fields.compilation.help" },
  ];

  const artworkFields: ToggleField<"artwork">[] = [
    { key: "embedArtwork", labelKey: "settings.metadataPreservation.fields.embedArtwork.label", helpLabelKey: "settings.metadataPreservation.fields.embedArtwork.helpLabel", helpKey: "settings.metadataPreservation.fields.embedArtwork.help" },
    { key: "saveCoverJpg", labelKey: "settings.metadataPreservation.fields.saveCoverJpg.label", helpLabelKey: "settings.metadataPreservation.fields.saveCoverJpg.helpLabel", helpKey: "settings.metadataPreservation.fields.saveCoverJpg.help" },
    {
      key: "replaceLowQualityArtwork",
      labelKey: "settings.metadataPreservation.fields.replaceLowQualityArtwork.label",
      helpLabelKey: "settings.metadataPreservation.fields.replaceLowQualityArtwork.helpLabel",
      helpKey: "settings.metadataPreservation.fields.replaceLowQualityArtwork.help",
      disabled: !artworkPowerEnabled,
    },
    {
      key: "preserveHigherQualityArtwork",
      labelKey: "settings.metadataPreservation.fields.preserveHigherQualityArtwork.label",
      helpLabelKey: "settings.metadataPreservation.fields.preserveHigherQualityArtwork.helpLabel",
      helpKey: "settings.metadataPreservation.fields.preserveHigherQualityArtwork.help",
      disabled: !artworkPowerEnabled,
    },
  ];

  const libraryFields: ToggleField<"library">[] = [
    { key: "replayGain", labelKey: "settings.metadataPreservation.fields.replayGain.label", helpLabelKey: "settings.metadataPreservation.fields.replayGain.helpLabel", helpKey: "settings.metadataPreservation.fields.replayGain.help" },
    { key: "singleOriginalTrackNumber", labelKey: "settings.metadataPreservation.fields.singleOriginalTrackNumber.label", helpLabelKey: "settings.metadataPreservation.fields.singleOriginalTrackNumber.helpLabel", helpKey: "settings.metadataPreservation.fields.singleOriginalTrackNumber.help" },
  ];

  const advancedIdFields: ToggleField<"advancedIds">[] = [
    { key: "musicBrainzReleaseId", labelKey: "settings.metadataPreservation.fields.musicBrainzReleaseId.label", helpLabelKey: "settings.metadataPreservation.fields.musicBrainzReleaseId.helpLabel", helpKey: "settings.metadataPreservation.fields.musicBrainzReleaseId.help" },
    { key: "musicBrainzTrackId", labelKey: "settings.metadataPreservation.fields.musicBrainzTrackId.label", helpLabelKey: "settings.metadataPreservation.fields.musicBrainzTrackId.helpLabel", helpKey: "settings.metadataPreservation.fields.musicBrainzTrackId.help" },
  ];

  return (
    <Panel elevated className="overflow-hidden rounded-[30px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-subtle)/0.96),hsl(var(--surface-soft)/0.92))] px-0 py-0">
      <div className="border-b border-border-soft/75 px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("settings.metadataPreservation.eyebrow")}
            </p>
            <h2 className="text-[18px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
              {t("settings.metadataPreservation.title")}
            </h2>
            <p className="max-w-[640px] text-[13px] text-muted-foreground">
              {t("settings.metadataPreservation.subtitle")}
            </p>
          </div>
          <div className="app-pill rounded-full px-3 py-1.5 text-[11px]">
            {saving ? t("common.saving") : t("common.ready")}
          </div>
        </div>
      </div>

      <div className="space-y-7 px-6 py-7">
        <MetadataGroup
          title={t("settings.metadataPreservation.groups.core.title")}
          tone="primary"
        >
          {coreFields.map((field) => (
            <ToggleRow
              key={String(field.key)}
              label={t(field.labelKey as never)}
              helpLabel={t(field.helpLabelKey as never)}
              help={t(field.helpKey as never)}
              checked={draft.core[field.key]}
              disabled={Boolean(field.disabled)}
              onToggle={() => void toggleField("core", field.key, field.disabled)}
            />
          ))}
        </MetadataGroup>

        <MetadataGroup
          title={t("settings.metadataPreservation.groups.release.title")}
          tone="secondary"
        >
          {releaseFields.map((field) => (
            <ToggleRow
              key={String(field.key)}
              label={t(field.labelKey as never)}
              helpLabel={t(field.helpLabelKey as never)}
              help={t(field.helpKey as never)}
              checked={draft.release[field.key]}
              disabled={Boolean(field.disabled)}
              onToggle={() => void toggleField("release", field.key, field.disabled)}
            />
          ))}
        </MetadataGroup>

        <MetadataGroup
          title={t("settings.metadataPreservation.groups.artwork.title")}
          tone="primary"
        >
          {artworkFields.map((field) => (
            <ToggleRow
              key={String(field.key)}
              label={t(field.labelKey as never)}
              helpLabel={t(field.helpLabelKey as never)}
              help={t(field.helpKey as never)}
              checked={draft.artwork[field.key]}
              disabled={Boolean(field.disabled)}
              onToggle={() => void toggleField("artwork", field.key, field.disabled)}
            />
          ))}
        </MetadataGroup>

        <MetadataGroup
          title={t("settings.metadataPreservation.groups.library.title")}
          tone="secondary"
        >
          {libraryFields.map((field) => (
            <ToggleRow
              key={String(field.key)}
              label={t(field.labelKey as never)}
              helpLabel={t(field.helpLabelKey as never)}
              help={t(field.helpKey as never)}
              checked={draft.library[field.key]}
              disabled={Boolean(field.disabled)}
              onToggle={() => void toggleField("library", field.key, field.disabled)}
            />
          ))}
        </MetadataGroup>

        <MetadataGroup
          title={t("settings.metadataPreservation.groups.advancedIds.title")}
          description={t("settings.metadataPreservation.groups.advancedIds.description")}
          tone="advanced"
        >
          {advancedIdFields.map((field) => (
            <ToggleRow
              key={String(field.key)}
              label={t(field.labelKey as never)}
              helpLabel={t(field.helpLabelKey as never)}
              help={t(field.helpKey as never)}
              checked={draft.advancedIds[field.key]}
              disabled={Boolean(field.disabled)}
              onToggle={() => void toggleField("advancedIds", field.key, field.disabled)}
            />
          ))}
        </MetadataGroup>
      </div>
    </Panel>
  );
}

function MetadataGroup({
  title,
  description,
  tone,
  children,
}: {
  title: string;
  description?: string;
  tone: "primary" | "secondary" | "advanced";
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="space-y-1">
        <h3
          className={cn(
            "text-[15px] font-semibold tracking-tight",
            tone === "advanced" ? "text-[hsl(var(--text-base))]" : "text-[hsl(var(--text-strong))]",
          )}
        >
          {title}
        </h3>
        {description ? (
          <p className="max-w-[580px] text-[12px] text-muted-foreground">{description}</p>
        ) : null}
      </div>

      <div
        className={cn(
          "overflow-hidden rounded-[24px] border",
          tone === "primary" && "border-border-soft/85 bg-surface-subtle/85",
          tone === "secondary" && "border-border-soft/75 bg-surface-soft/85",
          tone === "advanced" && "border-border-soft/70 bg-surface-contrast/75",
        )}
      >
        {children}
      </div>
    </section>
  );
}

function ToggleRow({
  label,
  helpLabel,
  help,
  checked,
  disabled,
  onToggle,
}: {
  label: string;
  helpLabel: string;
  help: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 border-b border-border-soft/75 px-4 py-3.5 transition last:border-b-0",
        disabled ? "opacity-55" : "hover:bg-surface-subtle/60",
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <p className="min-w-0 text-[13px] font-medium text-[hsl(var(--text-strong))]">{label}</p>
        <FieldHelp label={helpLabel} description={help} />
      </div>

      <motion.button
        {...(disabled ? {} : { whileTap: { scale: 0.97 } })}
        className={cn(
          "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition",
          checked
            ? "border-[hsl(var(--accent-hue)_70%_60%)] bg-[linear-gradient(180deg,hsl(var(--accent)),hsl(var(--accent)/0.88))]"
            : "border-border-soft/80 bg-surface-strong/80",
          disabled && "cursor-not-allowed",
        )}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={onToggle}
        disabled={disabled}
      >
        <motion.span
          animate={{ x: checked ? 20 : 2 }}
          transition={{ type: "spring", stiffness: 520, damping: 34 }}
          className="absolute h-5 w-5 rounded-full bg-[hsl(var(--accent-foreground))] shadow-[0_2px_8px_hsl(var(--surface-overlay)/0.28)]"
        />
      </motion.button>
    </div>
  );
}
