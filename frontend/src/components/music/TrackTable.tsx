import { Pencil } from "lucide-react";
import { Panel } from "@/components/Panel";
import { IssueBadge } from "@/components/music/IssueBadge";
import { useI18n } from "@/i18n/useI18n";
import type { TrackRow } from "@/types/music";

interface TrackTableProps {
  title: string;
  artist: string;
  year: string;
  tracks: TrackRow[];
  selectedTrackIds: Set<string>;
  trackIssueFilter: "all" | "issues" | "clean";
  onToggleTrack: (trackId: string) => void;
  onClearSelection: () => void;
  onTrackIssueFilterChange: (value: "all" | "issues" | "clean") => void;
  onOpenBulkEdit: () => void;
}

export function TrackTable({
  title,
  artist,
  year,
  tracks,
  selectedTrackIds,
  trackIssueFilter,
  onToggleTrack,
  onClearSelection,
  onTrackIssueFilterChange,
  onOpenBulkEdit,
}: TrackTableProps) {
  const { t } = useI18n();
  return (
    <Panel className="flex h-full min-h-0 flex-col p-0">
      <div className="flex items-center justify-between border-b border-border-soft/75 px-4 py-3">
        <div className="min-w-0">
          <h2 className="overflow-hidden text-ellipsis whitespace-nowrap text-[15px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
            {title}
          </h2>
          <p className="overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-muted-foreground">
            {artist} • {year}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            className="app-button-secondary inline-flex items-center gap-2 rounded-xl px-3 py-2 text-[12px] transition"
            type="button"
            onClick={onOpenBulkEdit}
          >
            <Pencil className="h-3.5 w-3.5" />
            {t("tracks.editAll")}
          </button>
          <span className="text-[11px] text-muted-foreground">{t("tracks.editAllHint")}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto [scrollbar-gutter:stable]">
        <table className="w-full table-fixed border-collapse">
          <thead className="sticky top-0 z-10 bg-surface-contrast/95 backdrop-blur-sm">
            <tr className="border-b border-border-soft/75 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              <th className="w-10 px-4 py-3 font-medium"> </th>
              <th className="w-12 px-2 py-3 font-medium">{t("tracks.number")}</th>
              <th className="w-[42%] px-2 py-3 font-medium">{t("tracks.titleHeader")}</th>
              <th className="w-[32%] px-2 py-3 font-medium">{t("tracks.artist")}</th>
              <th className="w-16 px-2 py-3 font-medium text-right">{t("tracks.duration")}</th>
              <th className="w-20 px-4 py-3 font-medium text-right">{t("tracks.issues")}</th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((track) => (
              <tr
                key={track.id}
                className="border-b border-border-soft/65 text-[13px] text-[hsl(var(--text-base))] transition hover:bg-surface-subtle/70"
              >
                <td className="px-4 py-3">
                  <button
                    className="inline-flex h-5 w-5 items-center justify-center rounded-md bg-accent text-[11px] text-accent-foreground"
                    type="button"
                    onClick={() => onToggleTrack(track.id)}
                  >
                    {selectedTrackIds.has(track.id) ? "✓" : ""}
                  </button>
                </td>
                <td className="px-2 py-3 text-muted-foreground">{track.index}</td>
                <td className="overflow-hidden text-ellipsis whitespace-nowrap px-2 py-3 text-[hsl(var(--text-strong))]">{track.title}</td>
                <td className="overflow-hidden text-ellipsis whitespace-nowrap px-2 py-3">{track.artist}</td>
                <td className="px-2 py-3 text-right text-[hsl(var(--text-strong))]">{track.duration}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    {track.issues.length === 0 ? (
                      <span className="text-[12px] text-[hsl(var(--success-fg))]">{t("tracks.ok")}</span>
                    ) : (
                      track.issues.map((issue) => (
                        <IssueBadge
                          key={issue.id}
                          compact
                          issue={issue}
                          className="px-1.5"
                        />
                      ))
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-border-soft/75 px-4 py-3 text-[12px] text-muted-foreground">
        <div className="flex items-center gap-2">
          <span className="rounded-xl bg-accent px-3 py-2 text-accent-foreground">{t("tracks.selected", { count: selectedTrackIds.size })}</span>
          <button
            className="app-button-secondary rounded-xl px-3 py-2"
            type="button"
            onClick={onClearSelection}
          >
            {t("tracks.selectNone")}
          </button>
        </div>
        <label className="flex items-center gap-2">
          <span>{t("tracks.show")}</span>
          <select
            className="app-control rounded-xl px-2 py-1 text-[12px]"
            value={trackIssueFilter}
            onChange={(event) => onTrackIssueFilterChange(event.target.value as "all" | "issues" | "clean")}
          >
            <option value="all">{t("import.trackFilters.all")}</option>
            <option value="issues">{t("import.trackFilters.issues")}</option>
            <option value="clean">{t("import.trackFilters.clean")}</option>
          </select>
        </label>
      </div>
    </Panel>
  );
}
