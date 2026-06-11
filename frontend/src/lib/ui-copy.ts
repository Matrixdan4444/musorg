import type { CleanupAction, LogEntry, MatchReason, MetadataDiffField, SuspiciousMetadataItem } from "@/types/music";

type Translator = (key: any, values?: Record<string, string | number>) => string;

function resolveTranslation(t: Translator, key: string, fallback: string, values?: Record<string, string | number>) {
  const translated = t(key as never, values);
  return translated.startsWith(`${key.split(".")[0]}.`) ? fallback : translated;
}

export function translateIssueLabel(issueId: string, fallback: string, t: Translator) {
  return resolveTranslation(t, `inspector.issueLabels.${issueId}`, fallback);
}

export function translateDiffLabel(row: MetadataDiffField, t: Translator) {
  return resolveTranslation(t, `inspector.diffLabels.${row.id}`, row.label);
}

export function translateCleanupAction(action: CleanupAction, t: Translator): { title: string; description?: string } {
  const resolveStructured = (baseKey: string, fallbackTitle: string, fallbackDescription?: string) => {
    const title = resolveTranslation(t, `${baseKey}.title`, fallbackTitle);
    const description = resolveTranslation(t, `${baseKey}.description`, fallbackDescription ?? "");
    return description
      ? { title, description }
      : { title };
  };

  if (action.origin === "manual_override") {
    return resolveStructured(
      "inspector.cleanupActions.manualOverride",
      "Applied a manual change",
      "Musorg applied a staged manual override for this album.",
    );
  }
  if (action.kind === "provider_selection") {
    if (action.source === "deezer") {
      return resolveStructured(
        "inspector.cleanupActions.providerSelectionDeezer",
        "Deezer was trusted",
        "Musorg trusted Deezer because its release passed the current validation checks.",
      );
    }
    if (action.source === "musicbrainz") {
      return resolveStructured(
        "inspector.cleanupActions.providerSelectionMusicBrainz",
        "MusicBrainz was chosen",
        "Musorg switched to MusicBrainz because it provided a more complete release.",
      );
    }
  }
  return resolveStructured(`inspector.cleanupActions.${action.kind}`, action.label);
}

export function translateConfidenceLabel(level: string | null | undefined, fallback: string, t: Translator) {
  if (!level) {
    return fallback;
  }
  return resolveTranslation(t, `inspector.confidence.${level}`, fallback);
}

export function translateProviderName(provider: string | null | undefined, t: Translator) {
  if (!provider || provider === "local" || provider === "local-only") {
    return t("inspector.providerLabels.local");
  }
  if (provider === "musicbrainz") {
    return "MusicBrainz";
  }
  if (provider === "deezer") {
    return "Deezer";
  }
  if (provider === "artwork") {
    return t("inspector.providerLabels.artwork");
  }
  return provider;
}

export function translateMatchReason(reason: MatchReason, t: Translator) {
  const message = reason.message;
  if (message === "Deezer matched the artist and returned a complete track list.") {
    return t("inspector.matchMessages.deezerMatchedComplete");
  }
  if (message === "Deezer track count matched the local album exactly.") {
    return t("inspector.matchMessages.deezerTrackCountExact");
  }
  if (message === "MusicBrainz provided a more complete release when Deezer was not reliable enough.") {
    return t("inspector.matchMessages.musicbrainzMoreComplete");
  }
  if (message === "MusicBrainz supplied release-date information for year resolution.") {
    return t("inspector.matchMessages.musicbrainzYearResolution");
  }

  const artworkMatch = message.match(/^Artwork upgraded from (.+) to (.+)\.$/);
  if (artworkMatch) {
    return t("inspector.matchMessages.artworkUpgraded", {
      before: artworkMatch[1]!,
      after: artworkMatch[2]!,
    });
  }

  return translateProviderReason(message, t);
}

export function translateProviderReason(message: string, t: Translator) {
  const exactMap: Record<string, string> = {
    "Deezer could not find any release candidates.": "inspector.providerMessages.deezerNoCandidates",
    "Deezer candidates were rejected during release validation.": "inspector.providerMessages.deezerRejectedDuringValidation",
    "Deezer album details could not be loaded.": "inspector.providerMessages.deezerAlbumDetailsUnavailable",
    "Deezer returned incomplete metadata for this release.": "inspector.providerMessages.deezerInvalidPayload",
    "Deezer did not provide a complete release payload.": "inspector.providerMessages.deezerPartialPayload",
    "Deezer release rejected because track counts did not match.": "inspector.providerMessages.deezerTrackCountMismatch",
    "Deezer release failed Musorg's validation checks.": "inspector.providerMessages.deezerValidationRejected",
    "Deezer release details did not match the local album.": "inspector.providerMessages.deezerAlbumDetailsMismatch",
    "Deezer did not provide a reliable release.": "inspector.providerMessages.deezerUnknown",
  };

  const mappedKey = exactMap[message];
  if (mappedKey) {
    return t(mappedKey as never);
  }
  return message;
}

export function translateSuspiciousLabel(item: SuspiciousMetadataItem, t: Translator) {
  return resolveTranslation(t, `inspector.issueLabels.${item.id}`, item.label);
}

export function translateSuspiciousMessage(item: SuspiciousMetadataItem, t: Translator) {
  if (item.id === "conflicting-release-year") {
    const match = item.message.match(/^Deezer suggested (.+), but MusicBrainz suggested (.+)\.$/);
    if (match) {
      return t("inspector.suspiciousMessages.conflicting-release-year", {
        deezerYear: match[1]!,
        musicbrainzYear: match[2]!,
      });
    }
  }
  return resolveTranslation(t, `inspector.suspiciousMessages.${item.id}`, item.message);
}

export function translateLogSource(source: string, t: Translator) {
  const normalized = source.toLowerCase();
  const translated = t(`logs.sources.${normalized}` as never);
  return translated.startsWith("logs.sources.") ? source : translated;
}

export function translateLogMessage(log: LogEntry, t: Translator) {
  const message = log.message;

  const exactMap: Record<string, string> = {
    "Reading file tags...": "logs.messages.readingTags",
    "Music library cleanup completed": "logs.messages.cleanupCompleted",
  };
  if (exactMap[message]) {
    return t(exactMap[message] as never);
  }

  let match = message.match(/^Starting music library cleanup \((.+)\)$/);
  if (match) {
    return t("logs.messages.startingCleanup", { mode: match[1]! });
  }

  match = message.match(/^Scanning music files\.\.\. found (\d+) audio files$/);
  if (match) {
    return t("logs.messages.scanningFound", { count: Number(match[1]) });
  }

  match = message.match(/^Matching album metadata\.\.\. checking (\d+) albums online$/);
  if (match) {
    return t("logs.messages.matchingChecking", { count: Number(match[1]) });
  }

  match = message.match(/^Matching album metadata (\d+)\/(\d+): (.+) — (.+)$/);
  if (match) {
    return t("logs.messages.matchingAlbum", {
      index: Number(match[1]),
      total: Number(match[2]),
      artist: match[3]!,
      album: match[4]!,
    });
  }

  match = message.match(/^Deezer match found for (.+) — (.+) \((\d+) tracks\)$/);
  if (match) {
    return t("logs.messages.deezerMatchFound", {
      artist: match[1]!,
      album: match[2]!,
      tracks: Number(match[3]),
    });
  }

  match = message.match(/^Deezer rejected: track count mismatch \(local=(\d+), deezer=(\d+)\), falling back to MusicBrainz$/);
  if (match) {
    return t("logs.messages.deezerRejectedTrackCount", {
      local: Number(match[1]),
      deezer: Number(match[2]),
    });
  }

  match = message.match(/^Partial album payload for (.+) - (.+), falling back to MusicBrainz$/);
  if (match) {
    return t("logs.messages.deezerPartialPayload", {
      artist: match[1]!,
      album: match[2]!,
    });
  }

  match = message.match(/^MusicBrainz metadata matched for (.+) — (.+) \((.+)\)$/);
  if (match) {
    return t("logs.messages.musicbrainzMatched", {
      artist: match[1]!,
      album: match[2]!,
      date: match[3]!,
    });
  }

  match = message.match(/^Cleaned metadata for (\d+) tracks$/);
  if (match) {
    return t("logs.messages.cleanedTracks", { count: Number(match[1]) });
  }

  match = message.match(/^Organized album structure for (\d+) albums$/);
  if (match) {
    return t("logs.messages.organizedAlbums", { count: Number(match[1]) });
  }

  match = message.match(/^Organizing album (\d+)\/(\d+): (.+) — (.+)$/);
  if (match) {
    return t("logs.messages.organizingAlbum", {
      index: Number(match[1]),
      total: Number(match[2]),
      artist: match[3]!,
      album: match[4]!,
    });
  }

  match = message.match(/^Saved cleaned tags for (.+) — (.+)$/);
  if (match) {
    return t("logs.messages.savedTags", { artist: match[1]!, album: match[2]! });
  }

  match = message.match(/^Finished organizing (.+) — (.+)$/);
  if (match) {
    return t("logs.messages.finishedOrganizing", { artist: match[1]!, album: match[2]! });
  }

  match = message.match(/^Output ready for (.+) — (.+)$/);
  if (match) {
    return t("logs.messages.outputReady", { artist: match[1]!, album: match[2]! });
  }

  match = message.match(/^Album completed: (.+) — (.+)$/);
  if (match) {
    return t("logs.messages.albumCompleted", { artist: match[1]!, album: match[2]! });
  }

  match = message.match(/^Saved (\d+) cleaned tracks to output library$/);
  if (match) {
    return t("logs.messages.savedTracks", { count: Number(match[1]) });
  }

  return message;
}
