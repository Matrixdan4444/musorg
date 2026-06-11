import { Check } from "lucide-react";
import { memo } from "react";
import { CoverImage } from "@/components/music/CoverImage";
import { IssueBadge } from "@/components/music/IssueBadge";
import { cn } from "@/lib/cn";
import { useI18n } from "@/i18n/useI18n";
import type { AlbumListItem } from "@/types/music";

interface AlbumCardProps {
  album: AlbumListItem;
}

function AlbumCardView({ album }: AlbumCardProps) {
  const { t } = useI18n();
  const processingLabel = translateProcessingState(album.processingState, t);
  const processingTone = processingToneClassName(album.processingState);

  return (
    <article
      className={cn(
        "group grid grid-cols-[60px_minmax(0,1fr)] gap-3 rounded-2xl border border-border-soft/75 bg-surface-soft px-3 py-3 transition-[transform,background-color,box-shadow,border-color] duration-150 ease-apple hover:-translate-y-px hover:bg-surface-subtle hover:shadow-card",
        album.selected && "border-[hsl(var(--info-border)/0.72)] bg-surface-selected/90",
        processingTone.container,
      )}
    >
      <CoverImage
        alt={t("albumCard.coverAlt", { title: album.title })}
        className="h-[60px] w-[60px] rounded-xl"
        compact
        priority
        src={album.coverUrl}
      />

      <div className="min-w-0 space-y-1.5">
        <div className="space-y-0.5">
          <h3 className="overflow-hidden text-ellipsis whitespace-nowrap text-[14px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
            {album.title}
          </h3>
          <p className="overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-[hsl(var(--text-base))]">
            {album.artist} <span className="text-muted-foreground">• {album.year}</span>
          </p>
          <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <span>{t("albumCard.tracks", { count: album.trackCount })}</span>
            {album.dirty ? <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] text-accent-foreground">{t("common.edited")}</span> : null}
            {album.lowConfidence ? (
              <span className="rounded-full border border-[hsl(var(--warning-border)/0.72)] bg-warning px-2 py-0.5 text-[10px] text-warning-foreground">
                {t("common.lowConfidence")}
              </span>
            ) : null}
            {processingLabel ? (
              <span className={cn(
                "rounded-full border px-2 py-0.5 text-[10px]",
                processingTone.badge,
              )}>
                {processingLabel}
              </span>
            ) : null}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          {album.issueCounts.danger > 0 ? (
            <IssueBadge compact severity="danger" value={album.issueCounts.danger} />
          ) : null}
          {album.issueCounts.warning > 0 ? (
            <IssueBadge compact severity="warning" value={album.issueCounts.warning} />
          ) : null}
          {album.issueCounts.success > 0 ? (
            <IssueBadge compact severity="success" value={album.issueCounts.success} />
          ) : null}
          {album.status === "ready" ? (
            <span className="ml-auto flex items-center gap-1 text-[11px] text-[hsl(var(--success-fg))]">
              <Check className="h-3.5 w-3.5" />
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export const AlbumCard = memo(AlbumCardView, (prev, next) => (
  prev.album.id === next.album.id
  && prev.album.title === next.album.title
  && prev.album.artist === next.album.artist
  && prev.album.year === next.album.year
  && prev.album.trackCount === next.album.trackCount
  && prev.album.coverUrl === next.album.coverUrl
  && prev.album.selected === next.album.selected
  && prev.album.dirty === next.album.dirty
  && prev.album.status === next.album.status
  && prev.album.processingState === next.album.processingState
  && prev.album.outputPath === next.album.outputPath
  && prev.album.provider === next.album.provider
  && prev.album.releaseType === next.album.releaseType
  && Boolean(prev.album.lowConfidence) === Boolean(next.album.lowConfidence)
  && prev.album.issueCounts.danger === next.album.issueCounts.danger
  && prev.album.issueCounts.warning === next.album.issueCounts.warning
  && prev.album.issueCounts.success === next.album.issueCounts.success
));

function translateProcessingState(
  processingState: string | null | undefined,
  t: (key: never, values?: Record<string, string | number>) => string,
) {
  if (!processingState || processingState === "idle") {
    return "";
  }

  const translated = t(`albumCard.processing.${processingState}` as never);
  return translated.startsWith("albumCard.processing.")
    ? processingState.replace(/_/g, " ")
    : translated;
}

function processingToneClassName(processingState: string | null | undefined) {
  if (processingState === "matching") {
    return {
      container: "border-[hsl(var(--info-border)/0.44)] bg-info/55",
      badge: "border-[hsl(var(--info-border)/0.44)] bg-info text-info-foreground animate-pulse",
    };
  }
  if (processingState === "writing") {
    return {
      container: "border-[hsl(var(--info-border)/0.44)] bg-info/45",
      badge: "border-[hsl(var(--info-border)/0.44)] bg-info text-info-foreground",
    };
  }
  if (processingState === "completed") {
    return {
      container: "border-[hsl(var(--success-border)/0.5)] bg-success/55",
      badge: "border-[hsl(var(--success-border)/0.5)] bg-success text-success-foreground",
    };
  }
  if (processingState === "failed") {
    return {
      container: "border-[hsl(var(--danger-border)/0.5)] bg-danger/60",
      badge: "border-[hsl(var(--danger-border)/0.52)] bg-danger text-danger-foreground",
    };
  }
  if (processingState === "missing_output") {
    return {
      container: "border-[hsl(var(--warning-border)/0.5)] bg-warning/60",
      badge: "border-[hsl(var(--warning-border)/0.52)] bg-warning text-warning-foreground",
    };
  }
  if (processingState === "scanning") {
    return {
      container: "border-border-soft/85 bg-surface-contrast/80",
      badge: "border-border-soft/80 bg-surface-subtle text-[hsl(var(--text-base))]",
    };
  }
  return {
    container: "",
    badge: "border-[hsl(var(--info-border)/0.44)] bg-info text-info-foreground",
  };
}
