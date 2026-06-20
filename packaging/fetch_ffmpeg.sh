#!/usr/bin/env bash
#
# Downloads the static FFmpeg binary that the macOS .app bundles. The binary is
# NOT committed to git (it's ~45 MB and GPLv3); this script fetches and verifies
# it before packaging. Run it once before building the .app:
#
#     ./packaging/fetch_ffmpeg.sh
#
# Pinned by sha256. If upstream's "latest" build changes, the checksum check
# fails on purpose — re-verify the new build, then bump VERSION/EXPECT_SHA here.
#
set -euo pipefail

VERSION="8.1.1"                 # FFmpeg version (GPLv3, --enable-gpl, no nonfree)
EXPECT_SHA="ef4fe121377039053b0d7bed4a9aa46e7912918f5ba6424a1dd155f4eed625b0"
URL="https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"

DEST="$(cd "$(dirname "$0")" && pwd)/bin"
mkdir -p "$DEST"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "Downloading FFmpeg $VERSION (GPLv3, static arm64)…"
curl -fL "$URL" -o "$tmp/ffmpeg.zip"
unzip -o "$tmp/ffmpeg.zip" -d "$tmp" >/dev/null

got="$(shasum -a 256 "$tmp/ffmpeg" | awk '{print $1}')"
if [ "$got" != "$EXPECT_SHA" ]; then
  echo "ERROR: sha256 mismatch." >&2
  echo "  expected ($VERSION): $EXPECT_SHA" >&2
  echo "  got:                 $got" >&2
  echo "Upstream likely changed. Re-verify the build and update fetch_ffmpeg.sh." >&2
  exit 1
fi

chmod +x "$tmp/ffmpeg"
mv "$tmp/ffmpeg" "$DEST/ffmpeg"
echo "OK -> $DEST/ffmpeg"
