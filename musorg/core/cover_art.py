from __future__ import annotations

from pathlib import Path

from mutagen.flac import FLAC


_FOLDER_COVER_NAMES = ("cover.jpg", "folder.jpg", "front.jpg")


def load_album_cover_bytes(folder_path: str) -> bytes | None:
    folder = Path(folder_path).expanduser()
    if not folder.exists() or not folder.is_dir():
        return None

    embedded = _load_embedded_cover_bytes(folder)
    if embedded:
        return embedded
    return _load_folder_cover_bytes(folder)


def _load_embedded_cover_bytes(folder: Path) -> bytes | None:
    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() != ".flac":
            continue
        try:
            audio = FLAC(file_path)
        except Exception:
            continue
        pictures = getattr(audio, "pictures", None) or []
        if pictures:
            return pictures[0].data
    return None


def _load_folder_cover_bytes(folder: Path) -> bytes | None:
    candidates = {path.name.lower(): path for path in folder.iterdir() if path.is_file()}
    for file_name in _FOLDER_COVER_NAMES:
        image_path = candidates.get(file_name)
        if not image_path:
            continue
        try:
            return image_path.read_bytes()
        except OSError:
            continue
    return None
