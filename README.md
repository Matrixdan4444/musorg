# musorg

Desktop app for organizing a music library. It scans your folders, matches each
album against online databases, cleans up the metadata, and lays the files out
into a consistent `Artist/Album` structure.

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

## Architecture

One supported desktop runtime:

- React frontend in `frontend/`
- FastAPI transport layer in `musorg/api/`
- shared backend-safe logic in `musorg/core/`
- pywebview desktop shell in `musorg/desktop_webview/`

All processing flows through a single pipeline: **scan → read metadata → group
by album → organize**. See [`docs/architecture.md`](docs/architecture.md) for
details.

## Installation

Requires Python 3.12+ and Node.js.

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
