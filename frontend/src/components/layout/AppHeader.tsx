import { motion } from "framer-motion";
import { ChevronDown, FolderClosed, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/i18n/useI18n";
import type { SummaryStat } from "@/types/music";

const statTone: Record<SummaryStat["severity"], string> = {
  neutral: "text-[hsl(var(--text-strong))]",
  danger: "text-[hsl(var(--danger-fg))]",
  warning: "text-[hsl(var(--warning-fg))]",
  success: "text-[hsl(var(--success-fg))]",
};

interface AppHeaderProps {
  libraryPath: string;
  libraryStatusLabel: string;
  libraryStatusTone: "neutral" | "warning" | "success";
  onOpenLibraryPicker: () => void;
  onRescan: () => void;
  onClean: () => void;
  onReset: () => void;
  cleaning?: boolean;
  cleanDisabled?: boolean;
  summary: SummaryStat[];
}

export function AppHeader({
  libraryPath,
  libraryStatusLabel,
  libraryStatusTone,
  onOpenLibraryPicker,
  onRescan,
  onClean,
  onReset,
  cleaning = false,
  cleanDisabled = false,
  summary,
}: AppHeaderProps) {
  const { t } = useI18n();
  const statusTone = {
    neutral: "text-muted-foreground",
    warning: "text-[hsl(var(--warning-fg))]",
    success: "text-[hsl(var(--success-fg))]",
  }[libraryStatusTone];

  return (
    <header className="glass-chrome space-y-4 border-b border-border-soft/75 px-4 py-5 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="space-y-1">
          <h1 className="text-[17px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
            {t("import.title")}
          </h1>
          <p className="text-[13px] text-muted-foreground">
            {t("import.subtitle")}
          </p>
        </div>

        <div className="flex flex-col gap-3 xl:min-w-[720px] xl:max-w-[820px]">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_140px_190px_96px]">
            <motion.button
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="app-control flex h-12 items-center gap-3 rounded-2xl px-4 text-left text-[13px]"
              type="button"
              onClick={onOpenLibraryPicker}
            >
              <FolderClosed className="h-5 w-5 shrink-0 text-muted-foreground" />
              <span className="truncate">{libraryPath}</span>
              <span className={cn("hidden text-[11px] sm:inline", statusTone)}>{libraryStatusLabel}</span>
              <ChevronDown className="ml-auto h-4 w-4 text-muted-foreground" />
            </motion.button>
            <button
              className="app-button-secondary h-12 rounded-2xl px-4 text-[13px] transition"
              type="button"
              onClick={onRescan}
            >
              {t("import.rescan")}
            </button>
            <button
              className="app-button-primary inline-flex h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[13px] font-semibold transition"
              type="button"
              onClick={onClean}
              disabled={cleanDisabled || cleaning}
            >
              <Sparkles className="h-4 w-4" />
              {cleaning ? t("import.cleaning") : t("import.clean")}
            </button>
            <button
              className="app-button-secondary h-12 rounded-2xl px-4 text-[13px]"
              type="button"
              onClick={onReset}
            >
              {t("import.reset")}
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-2.5 xl:grid-cols-5">
        {summary.map((item) => (
          <div
            key={item.id}
            className="rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-4"
          >
            <div className="flex items-center justify-between gap-3">
              <span className={cn("text-[28px] font-semibold leading-none", statTone[item.severity])}>
                {item.value}
              </span>
              <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                {item.hint}
              </span>
            </div>
            <p className="mt-2 text-[13px] text-[hsl(var(--text-base))]">{item.label}</p>
          </div>
        ))}
      </div>
    </header>
  );
}
