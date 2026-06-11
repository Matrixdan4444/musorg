import re
import unicodedata
from datetime import datetime


_NUMBER_WORD_VALUES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_NUMBER_SCALE_WORDS = {
    "hundred": 100,
    "thousand": 1000,
}
_NUMBER_CONNECTOR_WORDS = {"and"}
_ARTIST_SEPARATOR_RE = re.compile(r"\s*(?:,|/|\\|\s+-\s+)\s*")
VERSION_WORDS = (
    "acoustic",
    "anniversary",
    "cover",
    "clean",
    "deluxe",
    "edition",
    "ep",
    "edited",
    "expanded",
    "explicit",
    "exclusive",
    "live",
    "mix",
    "mono",
    "outtake",
    "remaster",
    "remastered",
    "censored",
    "stereo",
    "super deluxe",
    "version",
)
_REMASTERED_SUFFIX_RE = re.compile(r"\s*[\(\[][^)\]]*\bremaster(?:ed)?\b[^)\]]*[\)\]]\s*", re.IGNORECASE)
_FEATURE_SUFFIX_RE = re.compile(r"\s*[\(\[][^)\]]*\b(?:feat|ft)\.?(?:\s+[^)\]]*)?[\)\]]\s*", re.IGNORECASE)
_PRODUCER_SUFFIX_RE = re.compile(r"\s*[\(\[][^)\]]*\bprod\.?(?:\s+by)?\s+[^)\]]*[\)\]]\s*", re.IGNORECASE)
_BRACKETED_PART_RE = re.compile(r"\(([^)]*)\)|\[([^]]*)\]")
_FULL_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DISPLAY_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
ARTIST_ALIAS_OVERRIDES = {
    "affinage": "Аффинаж",
    "ирина қайратовна": "Ирина Кайратовна",
}


def clean_string(value: str) -> str:
    if not value:
        return "Unknown"

    return value.strip()


def normalize_lookup_text(value: str | None) -> str:
    if not value:
        return ""

    decomposed = unicodedata.normalize("NFKD", value)
    chars = []
    for char in decomposed.lower():
        if unicodedata.combining(char):
            continue
        chars.append(char if char.isalnum() else " ")

    return " ".join("".join(chars).split())


def _parse_number_word_tokens(tokens: list[str], start: int) -> tuple[str | None, int]:
    total = 0
    current = 0
    consumed = 0
    index = start
    saw_number = False

    while index < len(tokens):
        token = tokens[index]
        if token in _NUMBER_CONNECTOR_WORDS:
            if not saw_number:
                break
            index += 1
            consumed += 1
            continue

        if token in _NUMBER_WORD_VALUES:
            saw_number = True
            current += _NUMBER_WORD_VALUES[token]
            index += 1
            consumed += 1
            continue

        scale = _NUMBER_SCALE_WORDS.get(token)
        if scale is None:
            break

        if not saw_number:
            current = 1
            saw_number = True

        current *= scale
        if scale >= 1000:
            total += current
            current = 0

        index += 1
        consumed += 1

    if not saw_number:
        return None, 0

    return str(total + current), consumed


def normalize_lookup_text_for_matching(value: str | None) -> str:
    normalized = normalize_lookup_text(value)
    if not normalized:
        return ""

    tokens = normalized.split()
    canonical_tokens = []
    index = 0

    while index < len(tokens):
        token = tokens[index]

        if token.isdigit():
            canonical_tokens.append(str(int(token)))
            index += 1
            continue

        parsed_number, consumed = _parse_number_word_tokens(tokens, index)
        if parsed_number is not None and consumed:
            canonical_tokens.append(parsed_number)
            index += consumed
            continue

        canonical_tokens.append(token)
        index += 1

    return " ".join(canonical_tokens)


def canonical_artist_name(value: str | None) -> str | None:
    if not value or value == "Unknown":
        return None

    normalized = normalize_lookup_text(value)
    return ARTIST_ALIAS_OVERRIDES.get(normalized, value)


def normalize_artist_aliases(value: str | None) -> str | None:
    if not value or value == "Unknown":
        return value

    result = value
    for alias, canonical in ARTIST_ALIAS_OVERRIDES.items():
        result = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", canonical, result, flags=re.IGNORECASE)
    return result


def display_date(value: str) -> str:
    if not value:
        return "0000"

    cleaned = value.strip()
    if _FULL_ISO_DATE_RE.match(cleaned):
        try:
            return datetime.strptime(cleaned, "%Y-%m-%d").strftime("%d-%m-%Y")
        except ValueError:
            return cleaned

    return cleaned


def normalized_release_dates(
    date_value: str | None,
    release_date_iso_value: str | None = None,
) -> tuple[str, str]:
    cleaned_date = (date_value or "").strip()
    cleaned_release_date_iso = (release_date_iso_value or "").strip()

    if _FULL_ISO_DATE_RE.match(cleaned_release_date_iso):
        if _DISPLAY_DATE_RE.match(cleaned_date):
            return cleaned_date, cleaned_release_date_iso
        return display_date(cleaned_release_date_iso), cleaned_release_date_iso

    if _FULL_ISO_DATE_RE.match(cleaned_date):
        return display_date(cleaned_date), cleaned_date

    if _DISPLAY_DATE_RE.match(cleaned_date):
        return cleaned_date, ""

    if not cleaned_date:
        return "0000", ""

    return cleaned_date, cleaned_release_date_iso


def strip_version_suffixes(value: str) -> str:
    if not value:
        return "Unknown"

    cleaned = clean_string(value)

    def replace_if_version(match: re.Match[str]) -> str:
        part = match.group(0)
        lowered = part.lower()
        if any(word in lowered for word in VERSION_WORDS):
            return " "
        return part

    cleaned = re.sub(r"\([^)]*\)|\[[^]]*\]", replace_if_version, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip() or "Unknown"


def release_type_hint_from_album(value: str | None) -> str:
    if not value:
        return ""

    release_type_map = {
        "album": "album",
        "ep": "ep",
        "lp": "album",
        "single": "single",
    }

    for match in _BRACKETED_PART_RE.finditer(value):
        part = next((group for group in match.groups() if group), "")
        normalized = normalize_lookup_text(part)
        if normalized in release_type_map:
            return release_type_map[normalized]

    return ""


def strip_remastered_suffix(value: str) -> str:
    if not value:
        return "Unknown"

    cleaned = clean_string(value)
    cleaned = _REMASTERED_SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip() or "Unknown"


def strip_feature_suffix(value: str) -> str:
    if not value:
        return "Unknown"

    cleaned = clean_string(value)
    removed_feature = bool(_FEATURE_SUFFIX_RE.search(cleaned))
    cleaned = _FEATURE_SUFFIX_RE.sub(" ", cleaned)
    if removed_feature:
        cleaned = cleaned.rstrip(". ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip() or "Unknown"


def strip_producer_suffix(value: str) -> str:
    if not value:
        return "Unknown"

    cleaned = clean_string(value)
    cleaned = _PRODUCER_SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip() or "Unknown"


def primary_artist(value: str) -> str:
    if not value:
        return "Unknown"

    first_artist = _ARTIST_SEPARATOR_RE.split(value.strip(), maxsplit=1)[0]
    cleaned = clean_string(first_artist)

    return _ARTIST_SEPARATOR_RE.split(cleaned, maxsplit=1)[0].strip() or "Unknown"


def numeric_tag_value(value, fallback: int = 0) -> int:
    if value is None:
        return fallback

    raw_value = str(value).strip()
    if not raw_value:
        return fallback

    raw_value = re.split(r"[/\\]", raw_value, maxsplit=1)[0].strip()

    try:
        return int(raw_value)
    except ValueError:
        return fallback


def normalize_track(track: dict) -> dict:
    raw_album = track.get("album", "Unknown")

    # artist
    track["artist"] = clean_string(track.get("artist", "Unknown"))

    # album artist
    track["albumartist"] = clean_string(track.get("albumartist", "Unknown"))

    # album
    track["album"] = strip_feature_suffix(
        strip_version_suffixes(raw_album)
    )

    # title
    track["title"] = strip_producer_suffix(
        strip_feature_suffix(
            strip_remastered_suffix(track.get("title", "Unknown"))
        )
    )

    # preserve full date when available and keep display/ISO forms in sync
    date, release_date_iso = normalized_release_dates(
        track.get("date", "0000"),
        track.get("release_date_iso", ""),
    )
    track["date"] = date

    # track/disc numbers may arrive as "1/10" or malformed backslash variants like "1\10".
    track["tracknumber"] = numeric_tag_value(track.get("tracknumber"))
    track["discnumber"] = numeric_tag_value(track.get("discnumber"))

    release_type = track.get("releasetype", "")
    track["releasetype"] = clean_string(release_type) if release_type else ""

    track["release_date_iso"] = release_date_iso

    track["singleoriginaltracknumber"] = numeric_tag_value(
        track.get("singleoriginaltracknumber"),
        fallback=track["tracknumber"] or 0,
    )

    return track
