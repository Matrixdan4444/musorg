import type {
  AlbumInspectorData,
  AlbumIssue,
  AlbumListItem,
  ImportWorkspaceData,
  LogEntry,
  LogStep,
  SummaryStat,
  TrackRow,
} from "@/types/music";

function coverArt(seed: string, from: string, to: string, label: string) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 360">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="${from}" />
          <stop offset="100%" stop-color="${to}" />
        </linearGradient>
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
          <feComponentTransfer>
            <feFuncA type="table" tableValues="0 0.07" />
          </feComponentTransfer>
        </filter>
      </defs>
      <rect width="360" height="360" rx="36" fill="url(#bg)" />
      <circle cx="255" cy="96" r="86" fill="rgba(255,255,255,0.08)" />
      <path d="M24 278C117 215 191 176 332 150V360H24Z" fill="rgba(8,10,20,0.48)" />
      <path d="M34 208C96 266 172 280 306 120" stroke="rgba(255,255,255,0.18)" stroke-width="14" stroke-linecap="round" />
      <rect width="360" height="360" rx="36" filter="url(#grain)" />
      <text x="30" y="56" fill="white" font-size="20" font-family="Arial, sans-serif" opacity="0.84">${seed}</text>
      <text x="30" y="320" fill="white" font-size="34" font-weight="700" font-family="Arial, sans-serif">${label}</text>
    </svg>
  `;

  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

const missingAlbumArtist: AlbumIssue = {
  id: "missing-album-artist",
  label: "Missing album artist",
  severity: "danger",
};

const missingTrackNumber: AlbumIssue = {
  id: "missing-track-number",
  label: "Missing track number",
  severity: "warning",
};

const coverResolution: AlbumIssue = {
  id: "cover-resolution",
  label: "Cover art could be higher resolution",
  severity: "warning",
};

const issues: AlbumIssue[] = [missingAlbumArtist, missingTrackNumber, coverResolution];

const albums: AlbumListItem[] = [
  {
    id: "fat-of-the-land",
    title: "1997 - The Fat of the Land",
    artist: "The Prodigy",
    year: "1997",
    trackCount: 10,
    coverUrl: coverArt("01", "#29a3d4", "#1f273f", "Land"),
    selected: true,
    issueCounts: { danger: 3, warning: 1, success: 0 },
    status: "issues",
  },
  {
    id: "experience",
    title: "1992 - Experience",
    artist: "The Prodigy",
    year: "1992",
    trackCount: 27,
    coverUrl: coverArt("02", "#f0f0f0", "#8b8b8b", "XP"),
    issueCounts: { danger: 2, warning: 1, success: 0 },
    status: "issues",
  },
  {
    id: "jilted",
    title: "1994 - Music for the Jilted Generation",
    artist: "The Prodigy",
    year: "1994",
    trackCount: 12,
    coverUrl: coverArt("03", "#4c5a6d", "#202229", "Jilted"),
    issueCounts: { danger: 4, warning: 0, success: 0 },
    status: "issues",
  },
  {
    id: "always-outnumbered",
    title: "2004 - Always Outnumbered...",
    artist: "The Prodigy",
    year: "2004",
    trackCount: 14,
    coverUrl: coverArt("04", "#27110f", "#6a3026", "AON"),
    issueCounts: { danger: 0, warning: 0, success: 1 },
    status: "ready",
  },
  {
    id: "invaders",
    title: "2009 - Invaders Must Die",
    artist: "The Prodigy",
    year: "2009",
    trackCount: 10,
    coverUrl: coverArt("05", "#ece7d0", "#a07c00", "Invaders"),
    issueCounts: { danger: 1, warning: 1, success: 1 },
    status: "issues",
  },
  {
    id: "day-is-my-enemy",
    title: "2015 - The Day Is My Enemy",
    artist: "The Prodigy",
    year: "2015",
    trackCount: 14,
    coverUrl: coverArt("06", "#f3b045", "#6f1d1f", "Enemy"),
    issueCounts: { danger: 0, warning: 0, success: 1 },
    status: "ready",
  },
];

const tracks: TrackRow[] = [
  { id: "1", checked: true, index: 1, title: "Smack My Bitch Up", artist: "The Prodigy", duration: "5:43", issues: [missingAlbumArtist, missingTrackNumber] },
  { id: "2", checked: true, index: 2, title: "Breathe", artist: "The Prodigy", duration: "5:36", issues: [] },
  { id: "3", checked: true, index: 3, title: "Diesel Power", artist: "The Prodigy", duration: "4:18", issues: [] },
  { id: "4", checked: true, index: 4, title: "Funky Shit", artist: "The Prodigy", duration: "5:16", issues: [] },
  { id: "5", checked: true, index: 5, title: "Serial Thrilla", artist: "The Prodigy", duration: "5:11", issues: [] },
  { id: "6", checked: true, index: 6, title: "Mindfields", artist: "The Prodigy", duration: "5:40", issues: [] },
  { id: "7", checked: true, index: 7, title: "Narayan", artist: "The Prodigy", duration: "9:06", issues: [] },
  { id: "8", checked: true, index: 8, title: "Firestarter", artist: "The Prodigy", duration: "4:40", issues: [] },
  { id: "9", checked: true, index: 9, title: "Climbatize", artist: "The Prodigy", duration: "6:38", issues: [] },
  { id: "10", checked: true, index: 10, title: "Fuel My Fire", artist: "The Prodigy", duration: "4:19", issues: [] },
];

const inspector: AlbumInspectorData = {
  id: "fat-of-the-land",
  coverUrl: coverArt("01", "#29a3d4", "#1f273f", "Land"),
  title: "1997 - The Fat of the Land",
  artist: "The Prodigy",
  year: "1997",
  albumArtist: "The Prodigy",
  genre: "Electronic",
  disc: "1",
  metrics: [
    { id: "info", label: "Info", value: "i", severity: "neutral" },
    { id: "danger", label: "Issues", value: "3", severity: "danger" },
    { id: "warning", label: "Metadata", value: "1", severity: "warning" },
    { id: "success", label: "Ready", value: "0", severity: "success" },
  ],
  issues,
};

const logs: LogEntry[] = [
  { id: "log-1", timestamp: "10:42:13", severity: "info", source: "Metadata", type: "log", message: "Ready: 21 tracks with cleaned tags", runId: "mock-run" },
  { id: "log-2", timestamp: "10:42:15", severity: "info", source: "Group", type: "log", message: "Prepared 3 albums", runId: "mock-run" },
  { id: "log-3", timestamp: "10:42:16", severity: "info", source: "Organize", type: "log", message: "Album 1/3: The Prodigy - 1997 - The Fat of the Land", runId: "mock-run" },
  { id: "log-4", timestamp: "10:42:18", severity: "info", source: "Organize", type: "log", message: "Album 2/3: The Prodigy - 1992 - Experience", runId: "mock-run" },
  { id: "log-5", timestamp: "10:42:20", severity: "info", source: "Organize", type: "log", message: "Album 3/3: The Prodigy - itty bitty titty committee", runId: "mock-run" },
];

const logSteps: LogStep[] = [
  { id: "scan", title: "Scanning", status: "Complete" },
  { id: "metadata", title: "Reading Metadata", status: "Complete" },
  { id: "matching", title: "Matching", status: "Complete" },
  { id: "organize", title: "Organizing", status: "Complete" },
  { id: "done", title: "All done", status: "Complete" },
];

const summary: SummaryStat[] = [
  { id: "albums", label: "Albums", value: "14", hint: "Library batch", severity: "neutral" },
  { id: "tracks", label: "Tracks", value: "173", hint: "Selected rows", severity: "neutral" },
  { id: "issues", label: "Issues", value: "28", hint: "Need attention", severity: "danger" },
  { id: "fixes", label: "Can be fixed", value: "12", hint: "Auto-safe", severity: "warning" },
  { id: "preview", label: "Preview", value: "On", hint: "Read-only", severity: "success" },
];

export const importWorkspaceMock: ImportWorkspaceData = {
  libraryPath: "/Users/daniil/MusicTest/test_musorg_organized",
  albums,
  selectedAlbumId: "fat-of-the-land",
  inspector,
  tracks,
  logs,
  logSteps,
  summary,
};
