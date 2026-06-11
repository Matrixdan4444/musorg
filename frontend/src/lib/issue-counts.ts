import type { AlbumListItem } from "@/types/music";


export interface ActionableIssueCounts {
  danger: number;
  warning: number;
  success: number;
}


export function getAlbumActionableIssueCounts(album: Pick<AlbumListItem, "issueCounts"> | null | undefined): ActionableIssueCounts {
  return {
    danger: Math.max(0, Number(album?.issueCounts?.danger ?? 0)),
    warning: Math.max(0, Number(album?.issueCounts?.warning ?? 0)),
    success: Math.max(0, Number(album?.issueCounts?.success ?? 0)),
  };
}


export function getAlbumActionableIssueCount(album: Pick<AlbumListItem, "issueCounts"> | null | undefined): number {
  const counts = getAlbumActionableIssueCounts(album);
  return counts.danger + counts.warning;
}


export function hasAlbumActionableIssues(album: Pick<AlbumListItem, "issueCounts"> | null | undefined): boolean {
  return getAlbumActionableIssueCount(album) > 0;
}


export function summarizeLibraryIssues(albums: Array<Pick<AlbumListItem, "issueCounts">> | null | undefined) {
  const safeAlbums = albums ?? [];
  return safeAlbums.reduce(
    (totals, album) => {
      const counts = getAlbumActionableIssueCounts(album);
      totals.danger += counts.danger;
      totals.warning += counts.warning;
      totals.total += counts.danger + counts.warning;
      return totals;
    },
    { danger: 0, warning: 0, total: 0 },
  );
}
