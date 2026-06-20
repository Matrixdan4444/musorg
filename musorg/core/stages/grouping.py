import os

from musorg.filesystem.naming import filesystem_path_key
from musorg.utils.debug import log


def _has_number_collisions(tracks) -> bool:
    """True if two tracks share the same (disc, track) number.

    Distinct editions of the same title (e.g. a regular and a Japanese
    "Mezzanine", each numbered 1..N) collide; a real multi-disc album spread
    across folders (disc 1 vs disc 2) does not.
    """
    seen = set()
    for track in tracks:
        disc = str(track.get("discnumber") or "1").strip()
        number = str(track.get("tracknumber") or "0").strip()
        pair = (disc, number)
        if pair in seen:
            return True
        seen.add(pair)
    return False


def _split_distinct_source_albums(tracks) -> list[list]:
    """Split a (artist, album) bucket into distinct source albums when needed.

    If tracks from different source folders have overlapping (disc, track)
    numbers, they are different editions of the same title and must NOT be merged
    into one output folder. Otherwise (single source, or non-overlapping discs)
    keep them together.
    """
    if not _has_number_collisions(tracks):
        return [tracks]

    by_source: dict[str, list] = {}
    source_order: list[str] = []
    for track in tracks:
        source = filesystem_path_key(os.path.dirname(str(track.get("path") or "")))
        if source not in by_source:
            by_source[source] = []
            source_order.append(source)
        by_source[source].append(track)

    if len(by_source) <= 1:
        return [tracks]
    return [by_source[source] for source in source_order]


def build_album_groups(tracks):
    buckets: dict[tuple, list] = {}
    bucket_order: list[tuple] = []

    for track in tracks:
        album_artist = track.get("albumartist")
        # STRICT: use ONLY albumartist
        if album_artist:
            album_artist = album_artist.strip().lower()
        else:
            album_artist = "unknown"

        album = track.get("album", "Unknown").strip().lower()
        key = (album_artist, album)

        if key not in buckets:
            buckets[key] = []
            bucket_order.append(key)
        buckets[key].append(track)

    albums = {}
    for key in bucket_order:
        groups = _split_distinct_source_albums(buckets[key])
        for index, group in enumerate(groups):
            # First (or only) edition keeps the natural key; further distinct
            # editions of the same title get a suffixed key so they stay separate.
            group_key = key if index == 0 else (*key, index)
            albums[group_key] = group

    return albums


def group_by_album(context):
    albums = build_album_groups(context.tracks)

    context.albums = albums

    log("Group", f"Organized album structure for {len(albums)} albums", "📚")

    return context
