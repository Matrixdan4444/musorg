import { act } from "react";
import ReactDOM from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { I18nProvider } from "@/i18n/provider";
import { ThemeProvider } from "@/theme/provider";
import type { LibrarySettingsPayload } from "@/types/music";

const { getLibrarySettingsMock, runtimeConfig } = vi.hoisted(() => ({
  getLibrarySettingsMock: vi.fn<() => Promise<LibrarySettingsPayload>>(),
  runtimeConfig: {
    mode: "browser",
    hostKind: "browser",
    apiBaseUrl: "http://127.0.0.1:8000",
    frontendOrigin: "http://127.0.0.1:5173",
    forceSetupWizard: false,
  },
}));

vi.mock("@/lib/runtime", () => ({
  getRuntimeConfig: () => runtimeConfig,
}));

vi.mock("@/lib/api/music", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/music")>("@/lib/api/music");
  return {
    ...actual,
    getLibrarySettings: getLibrarySettingsMock,
  };
});

vi.mock("@/pages/ImportAlbumsPage", () => ({
  ImportAlbumsPage: () => <div>import-page</div>,
}));

vi.mock("@/pages/BatchEditingPage", () => ({
  BatchEditingPage: () => <div>batch-page</div>,
}));

vi.mock("@/pages/SettingsPage", () => ({
  SettingsPage: () => <div>settings-page</div>,
}));

function baseSettings(overrides: Partial<LibrarySettingsPayload> = {}): LibrarySettingsPayload {
  return {
    libraryRoot: "",
    outputRoot: "",
    developerMode: false,
    language: "en",
    themeMode: "dark",
    accentColor: "violet",
    duplicateHandling: "keep_everything",
    filenameCompatibility: "preserve_original",
    outputFormat: {
      albumFolderPreset: "artist_year_album",
      discHandling: "keep_together",
      fileNaming: "track_title",
      separatorStyle: "dot",
      customAlbumPattern: ["artist", "folder_break", "year", "album"],
      customAdvancedTemplate: null,
    },
    metadataPreservation: {
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
    },
    isConfigured: false,
    isAvailable: false,
    source: "none",
    pickerAvailable: true,
    onboardingCompleted: false,
    onboardingDismissed: false,
    message: null,
    error: null,
    ...overrides,
  };
}

describe("App onboarding flow", () => {
  let container: HTMLDivElement;
  let root: ReactDOM.Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = ReactDOM.createRoot(container);
    getLibrarySettingsMock.mockReset();
    runtimeConfig.forceSetupWizard = false;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", library_path: "" }),
    })));
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
  });

  it("shows the first-run helper when onboarding is still pending", async () => {
    getLibrarySettingsMock.mockResolvedValue(baseSettings());

    await act(async () => {
      root.render(
        <ThemeProvider>
          <I18nProvider>
            <App />
          </I18nProvider>
        </ThemeProvider>,
      );
    });

    expect(container.textContent).toContain("Skip");
    expect(container.textContent).not.toContain("import-page");
  });

  it("opens the import page when onboarding was already completed", async () => {
    getLibrarySettingsMock.mockResolvedValue(baseSettings({
      onboardingCompleted: true,
    }));

    await act(async () => {
      root.render(
        <ThemeProvider>
          <I18nProvider>
            <App />
          </I18nProvider>
        </ThemeProvider>,
      );
    });

    expect(container.textContent).toContain("import-page");
  });

  it("forces the setup helper open when the runtime asks for it", async () => {
    runtimeConfig.forceSetupWizard = true;
    getLibrarySettingsMock.mockResolvedValue(baseSettings({
      onboardingCompleted: true,
    }));

    await act(async () => {
      root.render(
        <ThemeProvider>
          <I18nProvider>
            <App />
          </I18nProvider>
        </ThemeProvider>,
      );
    });

    expect(container.textContent).toContain("Skip");
    expect(container.textContent).not.toContain("import-page");
  });
});
