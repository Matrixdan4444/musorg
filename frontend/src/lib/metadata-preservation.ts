import type { MetadataPreservationSettings } from "@/types/music";

export function defaultMetadataPreservationSettings(): MetadataPreservationSettings {
  return {
    core: {
      trackTitle: true,
      trackArtist: true,
      albumTitle: true,
      albumArtist: true,
      trackNumber: true,
      discNumber: true,
      discTotal: true,
    },
    release: {
      releaseDate: true,
      genre: true,
      releaseType: true,
      explicit: true,
      compilation: true,
    },
    artwork: {
      embedArtwork: true,
      saveCoverJpg: false,
      replaceLowQualityArtwork: true,
      preserveHigherQualityArtwork: true,
    },
    library: {
      replayGain: true,
      singleOriginalTrackNumber: true,
    },
    advancedIds: {
      musicBrainzReleaseId: true,
      musicBrainzTrackId: true,
    },
  };
}

export function artworkQualityControlsEnabled(settings: MetadataPreservationSettings): boolean {
  return settings.artwork.embedArtwork || settings.artwork.saveCoverJpg;
}
