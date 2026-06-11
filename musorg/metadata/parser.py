from __future__ import annotations

import io
import struct

from mutagen import File, MutagenError

from musorg.utils.debug import warning


def first_tag(audio, *keys, default=""):
    for key in keys:
        value = audio.get(key, [None])[0]
        if value not in (None, ""):
            return value
    return default


def first_tag_from_sources(*sources, keys, default=""):
    for source in sources:
        if not source:
            continue
        value = first_tag(source, *keys, default="")
        if value not in (None, ""):
            return value
    return default


def has_tag(audio, key):
    value = audio.get(key, [None])[0]
    return value not in (None, "")


def has_cover_art(audio):
    pictures = getattr(audio, "pictures", None)
    if pictures:
        return True

    tags = getattr(audio, "tags", None)
    if not tags:
        return False

    for key in tags.keys():
        lowered_key = str(key).lower()
        if lowered_key.startswith("apic") or lowered_key in {"covr", "metadata_block_picture"}:
            if tags.get(key):
                return True

    return False


def embedded_cover_dimensions(audio) -> tuple[int, int]:
    pictures = getattr(audio, "pictures", None)
    if pictures:
        for picture in pictures:
            width = int(getattr(picture, "width", 0) or 0)
            height = int(getattr(picture, "height", 0) or 0)
            if width > 0 and height > 0:
                return width, height

            data = getattr(picture, "data", None)
            if data:
                dimensions = image_dimensions_from_bytes(data)
                if dimensions != (0, 0):
                    return dimensions

    tags = getattr(audio, "tags", None)
    if not tags:
        return 0, 0

    for key in tags.keys():
        lowered_key = str(key).lower()
        if not (lowered_key.startswith("apic") or lowered_key in {"covr", "metadata_block_picture"}):
            continue

        frames = tags.get(key)
        if not isinstance(frames, list):
            frames = [frames]

        for frame in frames:
            data = getattr(frame, "data", None)
            if isinstance(frame, (bytes, bytearray)):
                data = bytes(frame)
            if not data:
                continue
            dimensions = image_dimensions_from_bytes(data)
            if dimensions != (0, 0):
                return dimensions

    return 0, 0


def image_dimensions_from_bytes(data: bytes) -> tuple[int, int]:
    if not data:
        return 0, 0

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        try:
            width, height = struct.unpack(">II", data[16:24])
            return int(width), int(height)
        except struct.error:
            return 0, 0

    if data[:3] == b"GIF" and len(data) >= 10:
        try:
            width, height = struct.unpack("<HH", data[6:10])
            return int(width), int(height)
        except struct.error:
            return 0, 0

    if data.startswith(b"\xff\xd8"):
        return jpeg_dimensions_from_bytes(data)

    return 0, 0


def jpeg_dimensions_from_bytes(data: bytes) -> tuple[int, int]:
    stream = io.BytesIO(data)
    stream.read(2)

    while True:
        marker_prefix = stream.read(1)
        if marker_prefix != b"\xff":
            return 0, 0

        marker_type = stream.read(1)
        while marker_type == b"\xff":
            marker_type = stream.read(1)
        if not marker_type:
            return 0, 0

        marker = marker_type[0]
        if marker in {0xD8, 0xD9}:
            continue

        segment_length_bytes = stream.read(2)
        if len(segment_length_bytes) != 2:
            return 0, 0

        segment_length = struct.unpack(">H", segment_length_bytes)[0]
        if segment_length < 2:
            return 0, 0

        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            segment = stream.read(segment_length - 2)
            if len(segment) < 5:
                return 0, 0
            height, width = struct.unpack(">HH", segment[1:5])
            return int(width), int(height)

        stream.seek(segment_length - 2, io.SEEK_CUR)


def read_tags(file_path):
    try:
        audio = File(file_path, easy=True)
        full_audio = File(file_path)
    except (MutagenError, OSError) as exc:
        warning("Metadata", f"Skipping unreadable audio file {file_path}: {exc}")
        return None

    if not audio:
        return None

    full_audio = full_audio or audio
    duration_seconds = getattr(getattr(full_audio, "info", None), "length", None)
    bitrate = getattr(getattr(full_audio, "info", None), "bitrate", None)
    sample_rate = getattr(getattr(full_audio, "info", None), "sample_rate", None)
    bits_per_sample = getattr(getattr(full_audio, "info", None), "bits_per_sample", None)
    channels = getattr(getattr(full_audio, "info", None), "channels", None)
    cover_width, cover_height = embedded_cover_dimensions(full_audio)
    replaygain_keys = {
        "replaygain_track_gain",
        "replaygain_album_gain",
        "replaygain_track_peak",
        "replaygain_album_peak",
        "rg_track_gain",
        "rg_album_gain",
        "rg_track_peak",
        "rg_album_peak",
    }
    easy_keys = {str(key).lower() for key in getattr(audio, "keys", lambda: [])()}
    full_tags = getattr(full_audio, "tags", None)
    full_keys = {str(key).lower() for key in full_tags.keys()} if full_tags else set()
    has_replaygain = bool(replaygain_keys & (easy_keys | full_keys))

    albumartist = audio.get("albumartist", [""])[0]
    track_artist = audio.get("artist", [""])[0]
    resolved_artist = albumartist or track_artist or "Unknown artist"

    return {
        "path": file_path,
        "artist": resolved_artist,
        "trackartist": track_artist or resolved_artist,
        "albumartist": albumartist or "Unknown artist",
        "album": audio.get("album", ["Unknown"])[0],
        "title": audio.get("title", ["Unknown"])[0],
        "genre": audio.get("genre", [""])[0],
        "label": first_tag_from_sources(audio, full_audio, keys=("label", "organization", "publisher")),
        "catalognumber": first_tag_from_sources(audio, full_audio, keys=("catalognumber", "catalog_number", "catalognumber")),
        "copyright": first_tag_from_sources(audio, full_audio, keys=("copyright",)),
        "comment": first_tag_from_sources(audio, full_audio, keys=("comment", "comments", "description")),
        "tracknumber": audio.get("tracknumber", ["0"])[0],
        "discnumber": audio.get("discnumber", ["0"])[0],
        "disctotal": first_tag_from_sources(audio, full_audio, keys=("disctotal", "totaldiscs"), default="0"),
        "date": first_tag(audio, "date", "releasedate", "release_date", "originaldate", default="0000"),
        "releasetime": first_tag(audio, "releasetime"),
        "releasetype": audio.get("releasetype", [""])[0],
        "release_date_iso": first_tag(audio, "release_date_iso", "releasedate", "release_date", "originaldate"),
        "musicbrainz_release_id": first_tag_from_sources(
            audio,
            full_audio,
            keys=(
                "musicbrainz_albumid",
                "musicbrainz_releaseid",
                "musicbrainz release id",
            ),
        ),
        "musicbrainz_track_id": first_tag_from_sources(
            audio,
            full_audio,
            keys=(
                "musicbrainz_trackid",
                "musicbrainz_recordingid",
                "musicbrainz recording id",
            ),
        ),
        "replaygain_track_gain": first_tag_from_sources(audio, full_audio, keys=("replaygain_track_gain", "rg_track_gain")),
        "replaygain_album_gain": first_tag_from_sources(audio, full_audio, keys=("replaygain_album_gain", "rg_album_gain")),
        "replaygain_track_peak": first_tag_from_sources(audio, full_audio, keys=("replaygain_track_peak", "rg_track_peak")),
        "replaygain_album_peak": first_tag_from_sources(audio, full_audio, keys=("replaygain_album_peak", "rg_album_peak")),
        "compilation": first_tag_from_sources(audio, full_audio, keys=("compilation",)),
        "explicit": first_tag_from_sources(audio, full_audio, keys=("explicit",)),
        "duration_seconds": float(duration_seconds) if duration_seconds is not None else None,
        "bitrate": int(bitrate) if bitrate is not None else None,
        "sample_rate": int(sample_rate) if sample_rate is not None else None,
        "bit_depth": int(bits_per_sample) if bits_per_sample is not None else None,
        "channels": int(channels) if channels is not None else None,
        "format": file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "",
        "has_replaygain": has_replaygain,
        "singleoriginaltracknumber": audio.get("singleoriginaltracknumber", ["0"])[0],
        "has_date_tag": has_tag(audio, "date"),
        "has_releasetime_tag": has_tag(audio, "releasetime"),
        "has_tracknumber_tag": has_tag(audio, "tracknumber"),
        "has_cover_art": has_cover_art(full_audio),
        "cover_width": cover_width,
        "cover_height": cover_height,
    }
