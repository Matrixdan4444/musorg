import re
import threading

import requests
from mutagen import File
from mutagen.flac import FLAC, Picture

from musorg.filesystem.media import normalize_picture_data
from musorg.metadata.normalizer import numeric_tag_value, strip_feature_suffix
from musorg.metadata.parser import image_dimensions_from_bytes
from musorg.utils.debug import warning


_FOUR_DIGIT_YEAR_RE = re.compile(r"^\d{4}$")
_DISPLAY_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMMENT_TAG_KEYS = {
    "comment",
    "comments",
    "description",
}
_LABEL_TAG_KEYS = {"label", "organization", "publisher"}
_CATALOG_NUMBER_TAG_KEYS = {"catalognumber", "catalog_number"}
_COPYRIGHT_TAG_KEYS = {"copyright"}
_NUMERIC_TAG_KEYS = {
    "tracknumber",
    "track",
    "tracktotal",
    "totaltracks",
    "discnumber",
    "disc",
    "disctotal",
    "totaldiscs",
    "singleoriginaltracknumber",
}
_DATE_TAG_KEYS = {
    "date",
    "year",
    "originaldate",
    "originalyear",
    "releasedate",
    "releasetime",
    "release_date",
    "release_date_iso",
}
_REPLAYGAIN_TAG_KEYS = {
    "replaygain_track_gain",
    "replaygain_album_gain",
    "replaygain_track_peak",
    "replaygain_album_peak",
    "rg_track_gain",
    "rg_album_gain",
    "rg_track_peak",
    "rg_album_peak",
}
_TRACK_ARTIST_TAG_KEYS = {"artist"}
_ALBUM_TAG_KEYS = {"album"}
_TITLE_TAG_KEYS = {"title"}
_TRACK_NUMBER_TAG_KEYS = {"tracknumber", "track"}
_DISC_NUMBER_TAG_KEYS = {"discnumber", "disc"}
_DISC_TOTAL_TAG_KEYS = {"disctotal", "totaldiscs"}
_ALBUM_ARTIST_TAG_KEYS = {"albumartist"}
_GENRE_TAG_KEYS = {"genre"}
_RELEASE_TYPE_TAG_KEYS = {"releasetype"}
_COMPILATION_TAG_KEYS = {"compilation"}
_EXPLICIT_TAG_KEYS = {"explicit"}
_SINGLE_ORIGINAL_TRACKNUMBER_TAG_KEYS = {"singleoriginaltracknumber"}
_MUSICBRAINZ_RELEASE_TAG_KEYS = {
    "musicbrainz_albumid",
    "musicbrainz_releaseid",
    "musicbrainz release id",
}
_MUSICBRAINZ_TRACK_TAG_KEYS = {
    "musicbrainz_trackid",
    "musicbrainz_recordingid",
    "musicbrainz recording id",
}
_THREAD_LOCAL = threading.local()
_COVER_DOWNLOAD_CACHE: dict[str, tuple[bytes, str]] = {}


def default_metadata_preservation_settings() -> dict[str, dict[str, bool]]:
    return {
        "core": {
            "trackTitle": True,
            "trackArtist": True,
            "albumTitle": True,
            "albumArtist": True,
            "trackNumber": True,
            "discNumber": True,
            "discTotal": True,
        },
        "release": {
            "releaseDate": True,
            "genre": True,
            "releaseType": True,
            "explicit": True,
            "compilation": True,
        },
        "artwork": {
            "embedArtwork": True,
            "saveCoverJpg": False,
            "replaceLowQualityArtwork": True,
            "preserveHigherQualityArtwork": True,
        },
        "library": {
            "replayGain": True,
            "singleOriginalTrackNumber": True,
        },
        "advancedIds": {
            "musicBrainzReleaseId": True,
            "musicBrainzTrackId": True,
        },
    }


def normalize_metadata_preservation_settings(settings: dict | None) -> dict[str, dict[str, bool]]:
    merged = {
        section: dict(values)
        for section, values in default_metadata_preservation_settings().items()
    }
    if not isinstance(settings, dict):
        return merged

    for section, defaults in merged.items():
        payload = settings.get(section)
        if not isinstance(payload, dict):
            continue
        for key in defaults:
            if isinstance(payload.get(key), bool):
                defaults[key] = payload[key]

    return merged


def reset_cover_download_cache() -> None:
    _COVER_DOWNLOAD_CACHE.clear()


def cover_request_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "cover_request_session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": "musorg/0.1 (+https://example.com)"})
        _THREAD_LOCAL.cover_request_session = session
    return session


def read_existing_flac_pictures(file_path):
    if hasattr(file_path, "pictures"):
        try:
            return list(file_path.pictures)
        except Exception:
            return []

    try:
        audio = FLAC(file_path)
    except Exception:
        return []

    return list(audio.pictures)


def restore_flac_pictures(file_path, pictures, run_report=None):
    if not pictures:
        return

    try:
        audio = FLAC(file_path)
    except Exception as exc:
        warning("Tagging", f"Could not restore cover art on {file_path}: {exc}")
        return

    audio.clear_pictures()

    for picture in pictures:
        restored_picture = Picture()
        restored_picture.type = picture.type
        restored_picture.desc = picture.desc
        restored_picture.mime = picture.mime
        if run_report:
            with run_report.measure("cover_processing"):
                restored_picture.data, restored_picture.mime = normalize_picture_data(
                    picture.data,
                    picture.mime,
                )
        else:
            restored_picture.data, restored_picture.mime = normalize_picture_data(
                picture.data,
                picture.mime,
            )
        audio.add_picture(restored_picture)

    audio.save()


def clear_comment_tags(file_path):
    try:
        audio = File(file_path)
    except Exception as exc:
        warning("Tagging", f"Could not clear comment tags on {file_path}: {exc}")
        return

    if not audio or not getattr(audio, "tags", None):
        return

    tag_keys = list(audio.tags.keys())
    removed = False
    for key in tag_keys:
        if str(key).lower() in _COMMENT_TAG_KEYS:
            del audio.tags[key]
            removed = True

    if removed:
        audio.save()


def clear_comment_tags_on_audio(audio) -> None:
    if not getattr(audio, "tags", None):
        return

    for key in list(audio.tags.keys()):
        if str(key).lower() in _COMMENT_TAG_KEYS:
            del audio.tags[key]


def clear_tag_keys(audio, tag_keys: set[str]) -> None:
    if not getattr(audio, "tags", None):
        return

    for key in list(audio.tags.keys()):
        if str(key).lower() in tag_keys:
            del audio.tags[key]


def clear_numeric_tags(audio) -> None:
    clear_tag_keys(audio, _NUMERIC_TAG_KEYS)


def clear_date_tags(audio) -> None:
    clear_tag_keys(audio, _DATE_TAG_KEYS)


def write_cover_art(file_path, cover_url, run_report=None):
    if not cover_url:
        return

    try:
        audio = FLAC(file_path)
    except Exception as exc:
        warning("Tagging", f"Could not write cover art to {file_path}: {exc}")
        return

    picture = build_cover_picture(cover_url, run_report=run_report)
    if picture is None:
        return

    audio.clear_pictures()
    audio.add_picture(picture)
    audio.save()


def build_cover_picture(cover_url, run_report=None):
    download = download_cover_bytes(cover_url, run_report=run_report)
    if download is None:
        return None

    picture_data, mime_type = download
    picture = Picture()
    picture.type = 3
    picture.mime = mime_type or "image/jpeg"
    picture.desc = "Cover"
    picture.data = picture_data
    return picture


def download_cover_bytes(cover_url, run_report=None):
    if not cover_url:
        return None

    cached = _COVER_DOWNLOAD_CACHE.get(cover_url)
    if cached is not None:
        return cached

    try:
        if run_report:
            with run_report.measure("cover_download"):
                response = cover_request_session().get(cover_url, timeout=15)
                response.raise_for_status()
        else:
            response = cover_request_session().get(cover_url, timeout=15)
            response.raise_for_status()
    except requests.RequestException as e:
        warning("Organize", f"Could not download cover art: {e}")
        return None

    mime_type = response.headers.get("Content-Type") or "image/jpeg"
    if run_report:
        with run_report.measure("cover_processing"):
            normalized = normalize_picture_data(response.content, mime_type)
    else:
        normalized = normalize_picture_data(response.content, mime_type)

    _COVER_DOWNLOAD_CACHE[cover_url] = normalized
    return normalized


def _picture_pixel_area(picture) -> int:
    width = int(getattr(picture, "width", 0) or 0)
    height = int(getattr(picture, "height", 0) or 0)
    if width <= 0 or height <= 0:
        width, height = image_dimensions_from_bytes(getattr(picture, "data", b""))
    return width * height


def write_metadata_tags(file_path, track, run_report=None, metadata_preservation_settings=None):
    metadata_settings = normalize_metadata_preservation_settings(metadata_preservation_settings)
    audio = File(file_path)
    if not audio:
        return

    clear_comment_tags_on_audio(audio)

    clear_tag_keys(audio, _TRACK_ARTIST_TAG_KEYS)
    if metadata_settings["core"]["trackArtist"]:
        artist = track.get("artist")
        if artist and artist != "Unknown":
            audio["artist"] = [str(artist)]

    clear_tag_keys(audio, _ALBUM_TAG_KEYS)
    if metadata_settings["core"]["albumTitle"]:
        album = strip_feature_suffix(track.get("album"))
        if album and album != "Unknown":
            audio["album"] = [str(album)]

    clear_tag_keys(audio, _TITLE_TAG_KEYS)
    if metadata_settings["core"]["trackTitle"]:
        title = strip_feature_suffix(track.get("title"))
        if title and title != "Unknown":
            audio["title"] = [str(title)]

    clear_tag_keys(audio, _TRACK_NUMBER_TAG_KEYS)
    if metadata_settings["core"]["trackNumber"]:
        track_number = numeric_tag_value(track.get("tracknumber"))
        if track_number:
            audio["tracknumber"] = [str(track_number)]

    clear_tag_keys(audio, _DISC_NUMBER_TAG_KEYS)
    if metadata_settings["core"]["discNumber"]:
        disc_number = numeric_tag_value(track.get("discnumber"))
        if disc_number:
            audio["discnumber"] = [str(disc_number)]

    clear_tag_keys(audio, _DISC_TOTAL_TAG_KEYS)
    if metadata_settings["core"]["discTotal"]:
        disc_total = numeric_tag_value(track.get("disctotal"))
        if disc_total:
            audio["disctotal"] = [str(disc_total)]

    clear_tag_keys(audio, _ALBUM_ARTIST_TAG_KEYS)
    if metadata_settings["core"]["albumArtist"]:
        album_artist = track.get("albumartist")
        if album_artist and album_artist != "Unknown":
            audio["albumartist"] = [album_artist]

    release_date_iso = str(track.get("release_date_iso") or "").strip()
    date = str(track.get("date") or "").strip()

    clear_date_tags(audio)
    if metadata_settings["release"]["releaseDate"]:
        if _ISO_DATE_RE.match(release_date_iso):
            audio["DATE"] = [release_date_iso[:4]]
            audio["RELEASETIME"] = [release_date_iso]
        elif _FOUR_DIGIT_YEAR_RE.match(release_date_iso):
            audio["DATE"] = [release_date_iso]
        elif _FOUR_DIGIT_YEAR_RE.match(date):
            audio["DATE"] = [date]
        elif _DISPLAY_DATE_RE.match(date):
            audio["DATE"] = [date[-4:]]

    clear_tag_keys(audio, _GENRE_TAG_KEYS)
    if metadata_settings["release"]["genre"]:
        genre = track.get("genre")
        if genre:
            audio["genre"] = [genre]

    clear_comment_tags_on_audio(audio)
    comment = str(track.get("comment") or "").strip()
    if comment:
        audio["comment"] = [comment]

    clear_tag_keys(audio, _RELEASE_TYPE_TAG_KEYS)
    if metadata_settings["release"]["releaseType"]:
        release_type = track.get("releasetype")
        if release_type:
            audio["releasetype"] = [str(release_type)]

    clear_tag_keys(audio, _LABEL_TAG_KEYS)
    label = str(track.get("label") or "").strip()
    if label:
        audio["label"] = [label]

    clear_tag_keys(audio, _CATALOG_NUMBER_TAG_KEYS)
    catalog_number = str(track.get("catalognumber") or track.get("catalog_number") or "").strip()
    if catalog_number:
        audio["catalognumber"] = [catalog_number]

    clear_tag_keys(audio, _COPYRIGHT_TAG_KEYS)
    copyright_text = str(track.get("copyright") or "").strip()
    if copyright_text:
        audio["copyright"] = [copyright_text]

    clear_tag_keys(audio, _COMPILATION_TAG_KEYS)
    if metadata_settings["release"]["compilation"]:
        compilation = str(track.get("compilation") or "").strip().lower()
        if compilation in {"true", "false"}:
            audio["compilation"] = [compilation]

    clear_tag_keys(audio, _EXPLICIT_TAG_KEYS)
    if metadata_settings["release"]["explicit"]:
        explicit = str(track.get("explicit") or "").strip().lower()
        if explicit in {"true", "false"}:
            audio["explicit"] = [explicit]

    clear_tag_keys(audio, _SINGLE_ORIGINAL_TRACKNUMBER_TAG_KEYS)
    if metadata_settings["library"]["singleOriginalTrackNumber"]:
        single_original_tracknumber = numeric_tag_value(track.get("singleoriginaltracknumber"))
        if single_original_tracknumber:
            audio["singleoriginaltracknumber"] = [str(single_original_tracknumber)]

    clear_tag_keys(audio, _REPLAYGAIN_TAG_KEYS)
    if metadata_settings["library"]["replayGain"]:
        for tag_name in (
            "replaygain_track_gain",
            "replaygain_album_gain",
            "replaygain_track_peak",
            "replaygain_album_peak",
        ):
            value = str(track.get(tag_name) or "").strip()
            if value:
                audio[tag_name] = [value]

    clear_tag_keys(audio, _MUSICBRAINZ_RELEASE_TAG_KEYS)
    if metadata_settings["advancedIds"]["musicBrainzReleaseId"]:
        musicbrainz_release_id = str(track.get("musicbrainz_release_id") or "").strip()
        if musicbrainz_release_id:
            audio["musicbrainz_albumid"] = [musicbrainz_release_id]

    clear_tag_keys(audio, _MUSICBRAINZ_TRACK_TAG_KEYS)
    if metadata_settings["advancedIds"]["musicBrainzTrackId"]:
        musicbrainz_track_id = str(track.get("musicbrainz_track_id") or "").strip()
        if musicbrainz_track_id:
            audio["musicbrainz_trackid"] = [musicbrainz_track_id]

    cover_url = track.get("cover")
    can_update_pictures = callable(getattr(audio, "clear_pictures", None)) and callable(getattr(audio, "add_picture", None))
    if can_update_pictures:
        artwork_settings = metadata_settings["artwork"]
        if not artwork_settings["embedArtwork"]:
            audio.clear_pictures()
        elif cover_url:
            existing_pictures = read_existing_flac_pictures(audio)
            picture = build_cover_picture(cover_url, run_report=run_report)
            if picture is not None:
                existing_area = max((_picture_pixel_area(item) for item in existing_pictures), default=0)
                new_area = _picture_pixel_area(picture)
                has_existing_art = bool(existing_pictures)
                should_replace = not has_existing_art
                if has_existing_art:
                    should_replace = artwork_settings["replaceLowQualityArtwork"]
                    if artwork_settings["preserveHigherQualityArtwork"] and existing_area > new_area:
                        should_replace = False
                if should_replace:
                    audio.clear_pictures()
                    audio.add_picture(picture)

    audio.save()


def remove_cover_art(file_path):
    try:
        audio = File(file_path)
    except Exception as exc:
        warning("Tagging", f"Could not remove cover art from {file_path}: {exc}")
        return

    if not audio:
        return

    if callable(getattr(audio, "clear_pictures", None)):
        audio.clear_pictures()

    clear_tag_keys(audio, {"metadata_block_picture", "covr"})
    for key in list(getattr(audio, "tags", {}).keys() if getattr(audio, "tags", None) else []):
        if str(key).lower().startswith("apic"):
            del audio.tags[key]

    audio.save()


def write_cover_art_bytes(file_path, picture_data: bytes, mime_type: str = "image/jpeg", run_report=None):
    if not picture_data:
        return

    try:
        audio = FLAC(file_path)
    except Exception as exc:
        warning("Tagging", f"Could not write cover art bytes to {file_path}: {exc}")
        return

    if run_report:
        with run_report.measure("cover_processing"):
            normalized_bytes, normalized_mime = normalize_picture_data(picture_data, mime_type)
    else:
        normalized_bytes, normalized_mime = normalize_picture_data(picture_data, mime_type)

    picture = Picture()
    picture.type = 3
    picture.mime = normalized_mime or mime_type or "image/jpeg"
    picture.desc = "Cover"
    picture.data = normalized_bytes

    audio.clear_pictures()
    audio.add_picture(picture)
    audio.save()
