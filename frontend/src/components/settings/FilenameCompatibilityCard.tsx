import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { FieldHelp } from "@/components/FieldHelp";
import { Panel } from "@/components/Panel";
import { useI18n } from "@/i18n/useI18n";
import { cn } from "@/lib/cn";
import type { FilenameCompatibilityMode } from "@/types/music";

interface FilenameCompatibilityCardProps {
  value: FilenameCompatibilityMode | null | undefined;
  saving: boolean;
  onChange: (value: FilenameCompatibilityMode) => Promise<void> | void;
}

const recommendedMode: FilenameCompatibilityMode = "preserve_original";

export function FilenameCompatibilityCard({ value, saving, onChange }: FilenameCompatibilityCardProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<FilenameCompatibilityMode>(value ?? recommendedMode);

  useEffect(() => {
    setDraft(value ?? recommendedMode);
  }, [value]);

  async function update(next: FilenameCompatibilityMode) {
    setDraft(next);
    await onChange(next);
  }

  const options: Array<{ value: FilenameCompatibilityMode; title: string; description: string; example: string[] }> = [
    {
      value: "preserve_original",
      title: t("settings.filenameCompatibility.options.preserveOriginal.title"),
      description: t("settings.filenameCompatibility.options.preserveOriginal.description"),
      example: ["Björk", "Sigur Rós", "Françoise Hardy"],
    },
    {
      value: "cross_platform_safe",
      title: t("settings.filenameCompatibility.options.crossPlatformSafe.title"),
      description: t("settings.filenameCompatibility.options.crossPlatformSafe.description"),
      example: ["Björk → Bjork", "Sigur Rós → Sigur Ros", "AC/DC → AC_DC"],
    },
  ];

  return (
    <Panel elevated className="overflow-hidden rounded-[30px] border border-border-soft/80 bg-[linear-gradient(180deg,hsl(var(--surface-subtle)/0.96),hsl(var(--surface-soft)/0.92))] px-0 py-0">
      <div className="border-b border-border-soft/75 px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {t("settings.filenameCompatibility.eyebrow")}
            </p>
            <div className="flex items-center gap-2">
              <h2 className="text-[18px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
                {t("settings.filenameCompatibility.title")}
              </h2>
              <FieldHelp
                label={t("settings.filenameCompatibility.helpLabel")}
                description={t("settings.filenameCompatibility.help")}
              />
            </div>
            <p className="max-w-[640px] text-[13px] text-muted-foreground">
              {t("settings.filenameCompatibility.subtitle")}
            </p>
          </div>
          <div className="app-pill rounded-full px-3 py-1.5 text-[11px]">
            {saving ? t("common.saving") : t("common.ready")}
          </div>
        </div>
      </div>

      <div className="grid gap-3 px-6 py-7 lg:grid-cols-2">
        {options.map((option) => {
          const selected = draft === option.value;
          return (
            <motion.button
              key={option.value}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.995 }}
              className={cn(
                "rounded-[22px] border px-4 py-4 text-left transition",
                selected
                  ? "border-[hsl(var(--accent-hue)_70%_60%)] bg-surface-selected/90 shadow-card"
                  : "border-border-soft/80 bg-surface-subtle/80 hover:border-border-strong/80 hover:bg-surface-subtle",
              )}
              type="button"
              onClick={() => void update(option.value)}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[14px] font-semibold text-[hsl(var(--text-strong))]">{option.title}</p>
                    {option.value === recommendedMode ? (
                      <span className="rounded-full border border-[hsl(var(--info-border)/0.44)] bg-info px-2 py-0.5 text-[10px] font-medium text-info-foreground">
                        {t("settings.outputFormat.recommended")}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-[12px] text-muted-foreground">{option.description}</p>
                </div>
                {selected ? (
                  <span className="rounded-full bg-surface-strong px-2 py-1 text-[10px] text-[hsl(var(--text-strong))]">
                    {t("settings.outputFormat.selected")}
                  </span>
                ) : null}
              </div>
              <div className="mt-4 rounded-[18px] bg-surface-contrast/85 px-3 py-2.5">
                {option.example.map((line) => (
                  <p key={line} className="text-[11px] leading-5 text-[hsl(var(--text-base))]">{line}</p>
                ))}
              </div>
            </motion.button>
          );
        })}
      </div>
    </Panel>
  );
}
