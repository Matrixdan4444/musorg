import { sampleAlbumCover } from "@/lib/sample-cover";
import type {
  AlbumFolderPreset,
  DiscHandlingMode,
  FilenameCompatibilityMode,
  FileNamingMode,
  OutputFormatSettings,
  OutputFormatToken,
  SeparatorStyle,
  TrackRow,
} from "@/types/music";

export interface OutputPreviewAlbum {
  title: string;
  artist: string;
  albumArtist: string;
  year: string;
  genre: string;
  coverUrl: string;
  tracks: Array<{
    title: string;
    artist: string;
    trackNumber: number;
    discNumber: number;
  }>;
}

export interface PreviewNode {
  kind: "folder" | "file";
  label: string;
  depth: number;
}

export interface PreviewWarning {
  id: string;
  title: string;
  message: string;
}

export interface OutputPreviewTree {
  albumRootLabel: string;
  tree: PreviewNode[];
  warnings: PreviewWarning[];
}

export interface OutputPreviewMockupModel {
  albumRootLabel: string;
  pathSegments: string[];
  sampleTrackFilenames: string[];
  discFolders: string[];
  warningSummary: string | null;
  warnings: PreviewWarning[];
  hasArtwork: boolean;
  totalTracks: number;
  discCount: number;
}

export function defaultOutputFormatSettings(): OutputFormatSettings {
  return {
    albumFolderPreset: "artist_year_album",
    discHandling: "keep_together",
    fileNaming: "track_title",
    separatorStyle: "dot",
    customAlbumPattern: ["artist", "folder_break", "year", "album"],
    customAdvancedTemplate: null,
  };
}

export function buildOutputPreviewTree(
  album: OutputPreviewAlbum,
  settings: OutputFormatSettings,
  filenameCompatibility: FilenameCompatibilityMode = "preserve_original",
): OutputPreviewTree {
  const folderSegments = albumFolderSegments(album, settings).map((segment) => previewSafeName(segment, filenameCompatibility));
  const maxDisc = Math.max(1, ...album.tracks.map((track) => track.discNumber || 1));
  const tree: PreviewNode[] = folderSegments.map((label, index) => ({ kind: "folder", label, depth: index }));
  const warnings = previewWarnings(album, settings);
  const discFolders = new Set<string>();

  for (const track of orderedTracks(album.tracks)) {
    const discFolder = settings.discHandling === "keep_together" && maxDisc > 1 ? `CD${track.discNumber || 1}` : null;
    if (discFolder && !discFolders.has(discFolder)) {
      discFolders.add(discFolder);
      tree.push({ kind: "folder", label: discFolder, depth: folderSegments.length });
    }
    tree.push({
      kind: "file",
      label: previewSafeName(formatTrackFilename(track, album, settings, maxDisc), filenameCompatibility),
      depth: folderSegments.length + (discFolder ? 1 : 0),
    });
  }

  if (album.coverUrl) {
    tree.push({ kind: "file", label: "Cover.jpg", depth: folderSegments.length });
  }

  return {
    albumRootLabel: folderSegments.join(" / "),
    tree,
    warnings,
  };
}

export function buildOutputPreviewMockupModel(
  album: OutputPreviewAlbum,
  preview: OutputPreviewTree,
): OutputPreviewMockupModel {
  const pathSegments = preview.albumRootLabel ? preview.albumRootLabel.split(" / ").filter(Boolean) : [];
  const discFolders: string[] = [];
  const sampleTrackFilenames: string[] = [];

  for (const node of preview.tree) {
    if (node.kind === "folder") {
      if (node.depth >= pathSegments.length) {
        discFolders.push(node.label);
      }
      continue;
    }

    if (node.label.toLowerCase().endsWith(".flac")) {
      sampleTrackFilenames.push(node.label);
    }
  }

  const discCount = Math.max(1, ...album.tracks.map((track) => track.discNumber || 1));

  return {
    albumRootLabel: preview.albumRootLabel,
    pathSegments,
    sampleTrackFilenames: sampleTrackFilenames.slice(0, 4),
    discFolders,
    warningSummary: preview.warnings[0]?.title ?? null,
    warnings: preview.warnings,
    hasArtwork: Boolean(album.coverUrl),
    totalTracks: album.tracks.length,
    discCount,
  };
}

function previewSafeName(value: string, mode: FilenameCompatibilityMode): string {
  if (!value) {
    return "Unknown";
  }
  const [stem, extension] = splitExtension(value);
  const normalizedStem = mode === "cross_platform_safe"
    ? stem.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    : stem;
  const replaced = normalizedStem
    .replaceAll("/", mode === "cross_platform_safe" ? "_" : "／")
    .replaceAll("\\", mode === "cross_platform_safe" ? "_" : "＼")
    .replaceAll(":", mode === "cross_platform_safe" ? "_" : ".")
    .replace(/["*?<>|]+/g, "_")
    .replace(/\u0000/g, "")
    .replace(/\s+/g, " ")
    .replace(/_+/g, "_")
    .trim();
  return `${replaced || "Unknown"}${extension}`;
}

function splitExtension(value: string): [string, string] {
  const match = value.match(/^(.*?)(\.[^.]+)?$/);
  return [match?.[1] ?? value, match?.[2] ?? ""];
}

export function samplePreviewAlbum(): OutputPreviewAlbum {
  const artist = "Pink Floyd";
  return {
    title: "The Dark Side of the Moon",
    artist,
    albumArtist: artist,
    year: "1973",
    genre: "Progressive Rock",
    coverUrl: sampleAlbumCover,
    tracks: [
      { title: "Speak to Me", artist, trackNumber: 1, discNumber: 1 },
      { title: "Breathe (In the Air)", artist, trackNumber: 2, discNumber: 1 },
      { title: "On the Run", artist, trackNumber: 3, discNumber: 1 },
      { title: "Time", artist, trackNumber: 4, discNumber: 1 },
      { title: "The Great Gig in the Sky", artist, trackNumber: 5, discNumber: 1 },
      { title: "Money", artist, trackNumber: 6, discNumber: 1 },
      { title: "Us and Them", artist, trackNumber: 7, discNumber: 1 },
      { title: "Any Colour You Like", artist, trackNumber: 8, discNumber: 1 },
      { title: "Brain Damage", artist, trackNumber: 9, discNumber: 1 },
      { title: "Eclipse", artist, trackNumber: 10, discNumber: 1 },
    ],
  };
}

export function previewAlbumFromWorkspace(input: {
  title: string;
  artist: string;
  albumArtist?: string;
  year: string;
  genre: string;
  coverUrl: string;
  disc?: string;
  tracks: TrackRow[];
} | null): OutputPreviewAlbum | null {
  if (!input) {
    return null;
  }
  return {
    title: input.title,
    artist: input.artist,
    albumArtist: input.albumArtist || input.artist,
    year: input.year,
    genre: input.genre,
    coverUrl: input.coverUrl,
    tracks: input.tracks.map((track, index) => ({
      title: track.title,
      artist: track.artist || input.artist,
      trackNumber: track.index || index + 1,
      discNumber: inferDiscNumber(track.id, input.disc),
    })),
  };
}

const DUPLICATE_LEADING_YEAR_RE = /^(\d{4})(\s*[-–—_.]\s*)\1((?:[\s\-–—_.].*)?)$/;

export function collapseDuplicateLeadingYear(segment: string): string {
  const match = DUPLICATE_LEADING_YEAR_RE.exec(segment.trim());
  if (!match) {
    return segment;
  }
  return `${match[1]}${match[3] ?? ""}`.trim();
}

function albumFolderSegments(album: OutputPreviewAlbum, settings: OutputFormatSettings): string[] {
  const artist = album.albumArtist || album.artist || "Unknown Artist";
  const year = album.year && album.year !== "Unknown" ? album.year : "0000";
  const genre = album.genre && album.genre !== "Unknown" ? album.genre : "Unknown";

  switch (settings.albumFolderPreset) {
    case "artist_album_year":
      return [artist, `${album.title} (${year})`];
    case "artist_album":
      return [artist, album.title];
    case "genre_artist_album":
      return [genre, artist, album.title];
    case "custom":
      return customAlbumSegments(album, settings.customAlbumPattern);
    default:
      return [artist, collapseDuplicateLeadingYear(`${year} - ${album.title}`)];
  }
}

function customAlbumSegments(album: OutputPreviewAlbum, pattern: OutputFormatToken[]): string[] {
  const segments: string[][] = [[]];
  for (const token of pattern) {
    if (token === "folder_break") {
      if (segments[segments.length - 1]?.length) {
        segments.push([]);
      }
      continue;
    }
    const value = customTokenValue(album, token);
    if (value) {
      segments[segments.length - 1]?.push(value);
    }
  }
  return segments.map((segment) => collapseDuplicateLeadingYear(segment.join(" - "))).filter(Boolean);
}

function customTokenValue(album: OutputPreviewAlbum, token: OutputFormatToken): string {
  switch (token) {
    case "artist":
      return album.albumArtist || album.artist;
    case "album":
      return album.title;
    case "year":
      return album.year && album.year !== "Unknown" ? album.year : "0000";
    case "genre":
      return album.genre && album.genre !== "Unknown" ? album.genre : "Unknown";
    case "disc":
      return String(album.tracks[0]?.discNumber || 1);
    case "track_number":
      return String(album.tracks[0]?.trackNumber || 1).padStart(2, "0");
    case "title":
      return album.tracks[0]?.title || album.title;
    case "folder_break":
      return "";
  }
}

function formatTrackFilename(
  track: OutputPreviewAlbum["tracks"][number],
  album: OutputPreviewAlbum,
  settings: OutputFormatSettings,
  maxDisc: number,
): string {
  const separator = fileSeparator(settings.separatorStyle);
  const baseTrackNumber = String(track.trackNumber || 0).padStart(2, "0");
  const prefixedTrack = settings.discHandling === "prefix_disc" && maxDisc > 1
    ? `${track.discNumber || 1}-${baseTrackNumber}`
    : baseTrackNumber;

  let parts: string[];
  switch (settings.fileNaming) {
    case "artist_title":
      parts = [track.artist || album.artist, track.title];
      break;
    case "track_artist_title":
      parts = [prefixedTrack, track.artist || album.artist, track.title];
      break;
    case "title_only":
      parts = [track.title];
      break;
    default:
      parts = [prefixedTrack, track.title];
      break;
  }

  return `${parts.join(separator)}.flac`;
}

function fileSeparator(style: SeparatorStyle): string {
  switch (style) {
    case "hyphen":
      return " - ";
    case "space":
      return " ";
    case "minimal":
      return " ";
    default:
      return ". ";
  }
}

function previewWarnings(album: OutputPreviewAlbum, settings: OutputFormatSettings): PreviewWarning[] {
  if (settings.discHandling !== "flatten") {
    return [];
  }
  const seen = new Set<number>();
  const duplicates = new Set<number>();
  for (const track of album.tracks) {
    if (seen.has(track.trackNumber)) {
      duplicates.add(track.trackNumber);
    }
    seen.add(track.trackNumber);
  }
  if (!duplicates.size) {
    return [];
  }
  return [{
    id: "ambiguous_flattened_order",
    title: "Flattening can blur disc order",
    message: `Track numbers ${[...duplicates].sort((a, b) => a - b).map((value) => String(value).padStart(2, "0")).join(", ")} repeat across discs.`,
  }];
}

function orderedTracks(tracks: OutputPreviewAlbum["tracks"]) {
  return [...tracks].sort((left, right) => {
    if (left.discNumber !== right.discNumber) {
      return left.discNumber - right.discNumber;
    }
    if (left.trackNumber !== right.trackNumber) {
      return left.trackNumber - right.trackNumber;
    }
    return left.title.localeCompare(right.title);
  });
}

function inferDiscNumber(trackId: string, fallbackDisc?: string) {
  const match = trackId.match(/disc[:_-]?(\d+)/i);
  if (match) {
    return Number(match[1]);
  }
  const parsed = Number(fallbackDisc || "1");
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export const albumFolderPresetOrder: AlbumFolderPreset[] = [
  "artist_year_album",
  "artist_album_year",
  "artist_album",
  "genre_artist_album",
  "custom",
];

export const discHandlingOrder: DiscHandlingMode[] = ["keep_together", "flatten", "prefix_disc"];
export const fileNamingOrder: FileNamingMode[] = ["track_title", "artist_title", "track_artist_title", "title_only"];
export const separatorStyleOrder: SeparatorStyle[] = ["hyphen", "dot", "space", "minimal"];
