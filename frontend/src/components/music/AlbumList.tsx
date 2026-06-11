import { Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Panel } from "@/components/Panel";
import { AlbumCard } from "@/components/music/AlbumCard";
import { warmCoverImage } from "@/components/music/CoverImage";
import { useI18n } from "@/i18n/useI18n";
import { cn } from "@/lib/cn";
import type { AlbumListItem } from "@/types/music";

export type AlbumSortMode = "title" | "artist" | "issueCount" | "year";
export type SortDirection = "asc" | "desc";

export interface AlbumFilterState {
  issuesOnly: boolean;
  cleanOnly: boolean;
  changedOnly: boolean;
  sortBy: AlbumSortMode;
  sortDirection: SortDirection;
}

interface AlbumListProps {
  albums: AlbumListItem[];
  search: string;
  filters: AlbumFilterState;
  onSearchChange: (value: string) => void;
  onFiltersChange: (value: AlbumFilterState) => void;
  onSelect?: (albumId: string) => void;
}

export function AlbumList({
  albums,
  search,
  filters,
  onSearchChange,
  onFiltersChange,
  onSelect,
}: AlbumListProps) {
  const { t } = useI18n();
  const [popoverOpen, setPopoverOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!popoverOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!popoverRef.current?.contains(event.target as Node)) {
        setPopoverOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [popoverOpen]);

  useEffect(() => {
    const nextCovers = albums
      .slice(0, 20)
      .map((album) => album.coverUrl)
      .filter(Boolean);

    if (nextCovers.length === 0 || typeof window === "undefined") {
      return;
    }

    const warm = () => {
      nextCovers.forEach((coverUrl) => {
        void warmCoverImage(coverUrl);
      });
    };

    if (typeof window.requestIdleCallback === "function") {
      const idleId = window.requestIdleCallback(warm, { timeout: 180 });
      return () => window.cancelIdleCallback(idleId);
    }

    const timeoutId = window.setTimeout(warm, 60);
    return () => window.clearTimeout(timeoutId);
  }, [albums]);

  const summaryLabel = useMemo(() => {
    const labels: string[] = [];
    if (filters.issuesOnly) {
      labels.push(t("albumList.filtersSummaryIssues"));
    }
    if (filters.cleanOnly) {
      labels.push(t("albumList.filtersSummaryClean"));
    }
    if (filters.changedOnly) {
      labels.push(t("albumList.filtersSummaryEdited"));
    }
    return labels.length ? labels.join(", ") : t("albumList.filtersSummaryAll");
  }, [filters, t]);

  return (
    <Panel className="flex h-full min-h-0 flex-col overflow-hidden p-3">
      <div
        ref={popoverRef}
        className="relative flex items-center gap-2 rounded-2xl border border-border-soft/75 bg-surface-contrast/80 px-3 py-2.5 transition-[border-color,box-shadow,background-color] focus-within:border-[hsl(var(--ring)/0.52)] focus-within:bg-surface-contrast focus-within:shadow-[0_0_0_2px_hsl(var(--ring)/0.14)]"
      >
        <Search className="h-4 w-4 text-muted-foreground" />
        <input
          className="min-w-0 flex-1 bg-transparent text-[13px] text-[hsl(var(--text-base))] outline-none placeholder:text-muted-foreground"
          placeholder={t("albumList.searchPlaceholder")}
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
        />
        <button
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-full transition",
            popoverOpen
              ? "bg-[hsl(var(--accent)/0.16)] text-[hsl(var(--brand-fg))]"
              : "text-muted-foreground hover:bg-surface-subtle/80 hover:text-[hsl(var(--text-strong))]",
          )}
          type="button"
          onClick={() => setPopoverOpen((value) => !value)}
        >
          <SlidersHorizontal className="h-4 w-4" />
        </button>
        {popoverOpen ? (
          <div className="absolute right-0 top-[calc(100%+8px)] z-20 w-[240px] rounded-2xl border border-border-soft/80 bg-panel p-3 shadow-panel">
            <div className="space-y-2 text-[12px] text-[hsl(var(--text-base))]">
              <label className="flex items-center justify-between gap-3">
                <span>{t("albumList.withIssues")}</span>
                <input
                  checked={filters.issuesOnly}
                  type="checkbox"
                  onChange={(event) => onFiltersChange({
                    ...filters,
                    issuesOnly: event.target.checked,
                    cleanOnly: event.target.checked ? false : filters.cleanOnly,
                  })}
                />
              </label>
              <label className="flex items-center justify-between gap-3">
                <span>{t("albumList.withoutIssues")}</span>
                <input
                  checked={filters.cleanOnly}
                  type="checkbox"
                  onChange={(event) => onFiltersChange({
                    ...filters,
                    cleanOnly: event.target.checked,
                    issuesOnly: event.target.checked ? false : filters.issuesOnly,
                  })}
                />
              </label>
              <label className="flex items-center justify-between gap-3">
                <span>{t("albumList.changed")}</span>
                <input
                  checked={filters.changedOnly}
                  type="checkbox"
                  onChange={(event) => onFiltersChange({ ...filters, changedOnly: event.target.checked })}
                />
              </label>
            </div>
            <div className="mt-3 space-y-3 border-t border-border-soft/75 pt-3">
              <label className="block text-[12px] text-muted-foreground">
                {t("albumList.sort")}
                <select
                  className="app-control mt-1.5 w-full rounded-xl px-2 py-2 text-[12px]"
                  value={filters.sortBy}
                  onChange={(event) => onFiltersChange({ ...filters, sortBy: event.target.value as AlbumSortMode })}
                >
                  <option value="title">{t("albumList.sortAlbumTitle")}</option>
                  <option value="artist">{t("albumList.sortArtist")}</option>
                  <option value="issueCount">{t("albumList.sortIssueCount")}</option>
                  <option value="year">{t("albumList.sortYear")}</option>
                </select>
              </label>
              <button
                className="app-button-secondary w-full rounded-xl px-3 py-2 text-[12px]"
                type="button"
                onClick={() => onFiltersChange({
                  ...filters,
                  sortDirection: filters.sortDirection === "asc" ? "desc" : "asc",
                })}
              >
                {filters.sortDirection === "asc" ? t("albumList.ascending") : t("albumList.descending")}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-x-hidden overflow-y-auto pr-1 [scrollbar-gutter:stable]">
        <div className="space-y-2">
          {albums.map((album) => (
            <button
              key={album.id}
              className="album-list-item block w-full text-left"
              onClick={() => onSelect?.(album.id)}
              type="button"
            >
              <AlbumCard album={album} />
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border-soft/75 px-1 pt-3 text-[12px] text-muted-foreground">
        <span>{t("albumList.albumCount", { count: albums.length })}</span>
        <span>{summaryLabel}</span>
      </div>
    </Panel>
  );
}
