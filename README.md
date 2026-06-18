# musorg

[![CI](https://github.com/Matrixdan4444/musorg/actions/workflows/ci.yml/badge.svg)](https://github.com/Matrixdan4444/musorg/actions/workflows/ci.yml)

Desktop app for organizing a music library. It scans your folders, matches each
album against online databases, cleans up the metadata, and lays the files out
into a consistent `Artist/Album` structure.

![Musorg](docs/ui-reference/current_ui_reference.png)

## Features

- **Automatic metadata matching** — looks each album up on Deezer first, then
  falls back to MusicBrainz when Deezer has no confident match.
- **Metadata cleanup** — normalizes artist/album/track fields and fills in
  missing release dates from the matched release.
- **Library organization** — moves tracks into a tidy `Artist/Album` layout and
  fetches cover art.
- **Batch editing** — edit metadata across many tracks at once.
- **Library health checks** — flags albums with missing covers, unknown artists,
  missing track numbers, or inconsistent album artists.

## Download (macOS)

Download the latest `Musorg-*.dmg` from the
[Releases](https://github.com/Matrixdan4444/musorg/releases) page, open it, and
drag **Musorg** into **Applications**.

The app is **not signed with an Apple Developer ID**, so on first launch macOS
Gatekeeper will block it — warning that it's from an "unidentified developer"
or, on recent macOS, that the app "is damaged and can't be opened." This is
expected for an open-source app distributed without a paid Apple certificate.
To run it the first time, do **one** of the following:

- **Right-click** (or Control-click) `Musorg.app` in Applications, choose
  **Open**, then **Open** in the dialog. macOS remembers the choice afterwards.

- Or remove the quarantine flag from Terminal, then open the app normally:

  ```bash
  xattr -dr com.apple.quarantine /Applications/Musorg.app
  ```

> Transcoding non-FLAC source files needs [`ffmpeg`](https://ffmpeg.org) on your
> `PATH` (`brew install ffmpeg`). FLAC-only libraries don't need it; cover-art
> resizing uses `sips`, which is built into macOS.

## Architecture

One supported desktop runtime:

- React frontend in `frontend/`
- FastAPI transport layer in `musorg/api/`
- shared backend-safe logic in `musorg/core/`
- pywebview desktop shell in `musorg/desktop_webview/`

All processing flows through a single pipeline: **scan → read metadata → group
by album → organize**. See [`docs/architecture.md`](docs/architecture.md) for
details.

## Build from source

For development, or to run without the prebuilt `.dmg`. Requires Python 3.12+
and Node.js.

**Backend:**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-desktop.txt
```

**Frontend** (the desktop shell serves the built assets, so this step is
required before running):

```bash
cd frontend
npm install
npm run build
```

## Run

```bash
python -m musorg.desktop_webview
```

## Development

Install dev dependencies and run the test suite:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## License

[MIT](LICENSE)
