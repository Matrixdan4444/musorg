"""Parsing and detection for CUE-sheet "image + cue" albums.

A CUE sheet describes an album whose audio is a single large "image" file
(album.flac / album.ape / album.wv ...) plus per-track titles and start
timestamps. This module turns such a folder into a list of per-track specs so
the rest of the pipeline can treat it like a normal multi-track album and the
organize step can slice the image into individual FLAC files.

Scope (v1): a single external ``.cue`` referencing exactly one image FILE.
Multi-file cue sheets (already split per track) are ignored so those files flow
through the normal per-file path.
"""
from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError

from musorg.utils.debug import warning

# Lossless container extensions that can act as a CUE "image".
IMAGE_EXTENSIONS = (".flac", ".ape", ".wv", ".wav", ".tta", ".wavpack")

FRAMES_PER_SECOND = 75


@dataclass
class CueTrack:
    number: int
    title: str = ""
    performer: str = ""
    start_seconds: float = 0.0


@dataclass
class CueSheet:
    performer: str = ""
    title: str = ""
    date: str = ""
    genre: str = ""
    comment: str = ""
    file_names: list[str] = field(default_factory=list)
    tracks: list[CueTrack] = field(default_factory=list)

    @property
    def is_single_image(self) -> bool:
        return len(self.file_names) == 1 and len(self.tracks) >= 1


def cue_index_to_seconds(value: str) -> float:
    """Convert an ``MM:SS:FF`` CUE timestamp (FF = frames, 75/sec) to seconds."""
    parts = str(value).strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid CUE index {value!r}")
    minutes, seconds, frames = (int(p) for p in parts)
    return minutes * 60 + seconds + frames / FRAMES_PER_SECOND


def _decode_cue_bytes(data: bytes) -> str:
    """CUE files come in assorted encodings (UTF-8/BOM, legacy cp1251, …)."""
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _tokenize(line: str) -> list[str]:
    try:
        return shlex.split(line)
    except ValueError:
        return line.split()


def parse_cue_text(text: str) -> CueSheet:
    sheet = CueSheet()
    current: CueTrack | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tokens = _tokenize(line)
        if not tokens:
            continue
        keyword = tokens[0].upper()

        if keyword == "FILE" and len(tokens) >= 2:
            sheet.file_names.append(tokens[1])
        elif keyword == "TRACK" and len(tokens) >= 2:
            try:
                number = int(tokens[1])
            except ValueError:
                number = len(sheet.tracks) + 1
            current = CueTrack(number=number)
            sheet.tracks.append(current)
        elif keyword == "TITLE" and len(tokens) >= 2:
            if current is not None:
                current.title = tokens[1]
            else:
                sheet.title = tokens[1]
        elif keyword == "PERFORMER" and len(tokens) >= 2:
            if current is not None:
                current.performer = tokens[1]
            else:
                sheet.performer = tokens[1]
        elif keyword == "INDEX" and len(tokens) >= 3 and current is not None:
            # INDEX 01 is the track start; INDEX 00 is the pregap. Prefer 01,
            # but accept 00 if 01 never appears.
            index_number = tokens[1]
            try:
                start = cue_index_to_seconds(tokens[2])
            except ValueError:
                continue
            if index_number == "01" or current.start_seconds == 0.0:
                current.start_seconds = start
        elif keyword == "REM" and len(tokens) >= 3:
            field_name = tokens[1].upper()
            value = " ".join(tokens[2:]).strip('"')
            if field_name == "DATE":
                sheet.date = value
            elif field_name == "GENRE":
                sheet.genre = value
            elif field_name == "COMMENT":
                sheet.comment = value

    return sheet


def _read_cue_file(cue_path: Path) -> CueSheet | None:
    try:
        data = cue_path.read_bytes()
    except OSError as exc:
        warning("Cue", f"Could not read cue sheet {cue_path}: {exc}")
        return None
    return parse_cue_text(_decode_cue_bytes(data))


def _resolve_image_path(folder: Path, sheet: CueSheet) -> Path | None:
    """Find the actual image file the cue refers to.

    EAC/XLD rips frequently name the FILE with a different extension than the
    real file (e.g. ``.wav`` in the cue but a ``.flac`` on disk), so fall back to
    the same basename with any known image extension, then to the single image
    file in the folder.
    """
    file_name = sheet.file_names[0]
    direct = folder / file_name
    if direct.is_file():
        return direct

    stem = Path(file_name).stem
    for ext in IMAGE_EXTENSIONS:
        candidate = folder / f"{stem}{ext}"
        if candidate.is_file():
            return candidate

    images = [
        entry
        for entry in folder.iterdir()
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if len(images) == 1:
        return images[0]
    return None


def detect_image_cue(folder: str | os.PathLike) -> tuple[str, CueSheet] | None:
    """Detect a single-image + cue album in ``folder``.

    Returns ``(image_path, CueSheet)`` or ``None`` when there is no usable
    single-image cue (no cue, multi-file cue, or the image is missing).
    """
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return None
    try:
        cue_files = sorted(
            entry for entry in folder_path.iterdir()
            if entry.is_file() and entry.suffix.lower() == ".cue"
        )
    except OSError:
        return None

    for cue_path in cue_files:
        sheet = _read_cue_file(cue_path)
        if sheet is None or not sheet.is_single_image:
            continue
        image_path = _resolve_image_path(folder_path, sheet)
        if image_path is not None:
            return str(image_path), sheet
    return None


def image_duration_seconds(image_path: str | os.PathLike) -> float | None:
    try:
        audio = MutagenFile(str(image_path))
    except (MutagenError, OSError):
        return None
    length = getattr(getattr(audio, "info", None), "length", None)
    return float(length) if length is not None else None


def cue_track_tag_dicts(
    image_path: str | os.PathLike,
    sheet: CueSheet,
    base_tags: dict | None = None,
    image_duration: float | None = None,
) -> list[dict]:
    """Build one ``read_tags``-shaped dict per cue track.

    Album-level fields come from the cue sheet (authoritative for image+cue
    rips), falling back to the image's own tags (``base_tags``). Per-track
    title/artist/number come from the cue. Each dict carries ``_cue_*`` slice
    markers used by the organize stage to extract the segment with ffmpeg.
    Callers read ``base_tags`` themselves so this module stays parser-free.
    """
    image_path = str(image_path)
    base = dict(base_tags) if base_tags else {"path": image_path}
    if image_duration is None:
        image_duration = image_duration_seconds(image_path)
    specs = cue_track_specs(image_path, sheet, image_duration)
    image_format = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else ""

    dicts: list[dict] = []
    for spec in specs:
        tags = dict(base)
        start = spec["start"]
        end = spec["end"]
        performer = spec["performer"] or sheet.performer
        tags["path"] = image_path
        tags["title"] = spec["title"] or tags.get("title") or "Unknown"
        if performer:
            tags["artist"] = performer
            tags["trackartist"] = performer
        if sheet.performer:
            tags["albumartist"] = sheet.performer
        if sheet.title:
            tags["album"] = sheet.title
        if sheet.genre:
            tags["genre"] = sheet.genre
        if sheet.date:
            tags["date"] = sheet.date
        tags["tracknumber"] = str(spec["number"])
        tags["discnumber"] = "1"
        tags["has_tracknumber_tag"] = True
        tags["duration_seconds"] = (end - start) if end is not None else None
        tags["format"] = image_format
        tags["_cue_image_path"] = image_path
        tags["_cue_start_seconds"] = start
        tags["_cue_end_seconds"] = end
        dicts.append(tags)
    return dicts


def cue_track_specs(
    image_path: str | os.PathLike,
    sheet: CueSheet,
    image_duration: float | None = None,
) -> list[dict]:
    """Per-track slice specs: number, title, performer, start, end (seconds).

    ``end`` is the next track's start; the last track ends at the image
    duration (or ``None`` if unknown, meaning "to end of file").
    """
    if image_duration is None:
        image_duration = image_duration_seconds(image_path)

    ordered = sorted(sheet.tracks, key=lambda track: track.start_seconds)
    specs: list[dict] = []
    for position, track in enumerate(ordered):
        if position + 1 < len(ordered):
            end: float | None = ordered[position + 1].start_seconds
        else:
            end = image_duration
        specs.append(
            {
                "number": track.number or (position + 1),
                "title": track.title,
                "performer": track.performer or sheet.performer,
                "start": track.start_seconds,
                "end": end,
            }
        )
    return specs
