import { describe, expect, it } from "vitest";
import {
  buildOutputPreviewMockupModel,
  buildOutputPreviewTree,
  collapseDuplicateLeadingYear,
  defaultOutputFormatSettings,
  samplePreviewAlbum,
} from "@/lib/output-format";

describe("collapseDuplicateLeadingYear", () => {
  it("collapses a duplicated leading year", () => {
    expect(collapseDuplicateLeadingYear("2024 - 2024 - начало")).toBe("2024 - начало");
  });

  it("leaves a single leading year untouched", () => {
    expect(collapseDuplicateLeadingYear("2024 - начало")).toBe("2024 - начало");
  });

  it("does not touch an album that is just a year", () => {
    expect(collapseDuplicateLeadingYear("1984")).toBe("1984");
  });

  it("does not collapse two different leading years", () => {
    expect(collapseDuplicateLeadingYear("2024 - 1999 Remaster")).toBe("2024 - 1999 Remaster");
  });
});

describe("buildOutputPreviewMockupModel", () => {
  it("collects path segments and track filename examples from the preview tree", () => {
    const album = samplePreviewAlbum();
    const preview = buildOutputPreviewTree(album, defaultOutputFormatSettings());

    expect(buildOutputPreviewMockupModel(album, preview)).toMatchObject({
      pathSegments: ["Pink Floyd", "1973 - The Dark Side of the Moon"],
      sampleTrackFilenames: [
        "01. Speak to Me.flac",
        "02. Breathe (In the Air).flac",
        "03. On the Run.flac",
        "04. Time.flac",
      ],
      discFolders: [],
      hasArtwork: true,
      totalTracks: 10,
      discCount: 1,
    });
  });

  it("detects disc folders for keep-together multi-disc previews", () => {
    const album = {
      ...samplePreviewAlbum(),
      coverUrl: "/covers/down-underground.jpg",
      tracks: [
        { title: "Disc One Intro", artist: "The Liminanas", trackNumber: 1, discNumber: 1 },
        { title: "Disc Two Intro", artist: "The Liminanas", trackNumber: 1, discNumber: 2 },
      ],
    };
    const preview = buildOutputPreviewTree(album, defaultOutputFormatSettings());

    expect(buildOutputPreviewMockupModel(album, preview)).toMatchObject({
      discFolders: ["CD1", "CD2"],
      hasArtwork: true,
      discCount: 2,
    });
  });

  it("surfaces safe filenames from the generated preview tree", () => {
    const album = {
      ...samplePreviewAlbum(),
      title: "Down/Underground: Deluxe?",
      tracks: [
        { title: "Side/A: Intro?", artist: "The Liminanas", trackNumber: 1, discNumber: 1 },
      ],
    };
    const preview = buildOutputPreviewTree(album, defaultOutputFormatSettings(), "cross_platform_safe");

    expect(buildOutputPreviewMockupModel(album, preview)).toMatchObject({
      pathSegments: ["Pink Floyd", "1973 - Down_Underground_ Deluxe_"],
      sampleTrackFilenames: ["01. Side_A_ Intro_.flac"],
    });
  });

  it("summarizes warnings without crashing when there is no artwork", () => {
    const album = {
      ...samplePreviewAlbum(),
      coverUrl: "",
      tracks: [
        { title: "Disc One Intro", artist: "The Liminanas", trackNumber: 1, discNumber: 1 },
        { title: "Disc Two Intro", artist: "The Liminanas", trackNumber: 1, discNumber: 2 },
      ],
    };
    const preview = buildOutputPreviewTree(album, {
      ...defaultOutputFormatSettings(),
      discHandling: "flatten",
    });

    expect(buildOutputPreviewMockupModel(album, preview)).toMatchObject({
      hasArtwork: false,
      warningSummary: "Flattening can blur disc order",
      sampleTrackFilenames: ["01. Disc One Intro.flac", "01. Disc Two Intro.flac"],
    });
  });
});
