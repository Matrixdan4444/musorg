from __future__ import annotations


_PLACEHOLDER_ARTISTS = {"", "unknown", "unknown artist"}


def known_artist(value: object) -> str | None:
    text = str(value or "").strip()
    if text.lower() in _PLACEHOLDER_ARTISTS:
        return None
    return text


def first_known_artist(*values: object, fallback: str | None = None) -> str | None:
    for value in values:
        artist = known_artist(value)
        if artist:
            return artist
    return fallback
