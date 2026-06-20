import re
from dataclasses import asdict, dataclass

from rapidfuzz import fuzz

from musorg.metadata.normalizer import (
    VERSION_WORDS,
    normalize_lookup_text as _normalize_lookup_text,
    normalize_lookup_text_for_matching,
    strip_edition_suffixes,
    strip_producer_suffix,
    strip_version_suffixes,
)


FailureReason = str

GENERIC_BRACKET_HINT_WORDS = {
    "album",
    "cd",
    "disc",
    "digital",
    "ep",
    "lp",
    "release",
    "single",
}
SOUNDTRACK_BRACKET_HINT_WORDS = {
    "ost",
    "score",
    "soundtrack",
}
ACCEPTED_RELEASE_TYPES = {"album", "single", "ep", "compilation"}
_ARTIST_CREDIT_SPLIT_RE = re.compile(r"\s*(?:,|&|/|\\| feat\. | ft\. )\s*", re.IGNORECASE)
_SOUNDTRACK_TRAILING_SEPARATOR_RE = re.compile(r"\s*(?:-|:|–|—)\s*$")
_CYRILLIC_TO_LATIN = {
    "а": ("a",),
    "б": ("b",),
    "в": ("v",),
    "г": ("g",),
    "д": ("d",),
    "е": ("e", "ye"),
    "ё": ("yo", "e"),
    "ж": ("zh",),
    "з": ("z",),
    "и": ("i", "y"),
    "й": ("y", "i"),
    "к": ("k", "c"),
    "л": ("l",),
    "м": ("m",),
    "н": ("n",),
    "о": ("o",),
    "п": ("p",),
    "р": ("r",),
    "с": ("s",),
    "т": ("t",),
    "у": ("u",),
    "ф": ("f",),
    "х": ("kh", "h"),
    "ц": ("ts", "c"),
    "ч": ("ch",),
    "ш": ("sh",),
    "щ": ("shch", "sch"),
    "ъ": ("",),
    "ы": ("y", "i"),
    "ь": ("",),
    "э": ("e",),
    "ю": ("yu", "u"),
    "я": ("ya", "ia"),
}
_RU_TRANSLIT_TOKENS = (
    ("shch", "щ"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("a", "а"),
    ("b", "б"),
    ("v", "в"),
    ("g", "г"),
    ("d", "д"),
    ("e", "е"),
    ("z", "з"),
    ("i", "и"),
    ("j", "й"),
    ("y", "ы"),
    ("k", "к"),
    ("l", "л"),
    ("m", "м"),
    ("n", "н"),
    ("o", "о"),
    ("p", "п"),
    ("r", "р"),
    ("s", "с"),
    ("t", "т"),
    ("u", "у"),
    ("f", "ф"),
    ("h", "х"),
    ("c", "к"),
)


@dataclass(frozen=True)
class LookupInput:
    artist: str
    album: str
    expected_track_count: int | None = None
    expected_titles: tuple[str, ...] = ()
    preferred_release_type: str = ""


@dataclass(frozen=True)
class QueryPlan:
    phase: str
    query: str
    entity: str
    strength: str


@dataclass(frozen=True)
class CandidateEvidence:
    is_release: bool
    exact_track_count: bool
    strict_title_match: bool
    release_type_match: bool
    title_match: bool
    artist_match: bool
    artist_score: float
    title_score: float
    track_title_sequence_score: float
    track_delta: int
    version_penalty: int
    completeness_score: int

    def deezer_rank(self) -> tuple:
        return (
            self.is_release,
            self.exact_track_count,
            self.strict_title_match,
            self.release_type_match,
            self.title_match,
            self.artist_match,
            self.artist_score,
            self.track_title_sequence_score,
            -self.track_delta,
            -self.version_penalty,
            self.completeness_score,
        )

    def musicbrainz_rank(self) -> tuple:
        return (
            self.strict_title_match,
            self.title_match,
            self.exact_track_count,
            self.release_type_match,
            self.artist_match,
            self.track_title_sequence_score,
            self.completeness_score,
            self.title_score,
            self.artist_score,
            -self.track_delta,
            -self.version_penalty,
        )


@dataclass(frozen=True)
class ResolutionResult:
    provider: str
    success: bool
    metadata: dict | None
    reason: FailureReason | None
    terminal: bool
    confidence: str | None = None
    evidence: dict | None = None

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "success": self.success,
            "metadata": self.metadata,
            "reason": self.reason,
            "terminal": self.terminal,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def normalize_lookup_text(value: str | None) -> str:
    return _normalize_lookup_text(value)


def contains_ascii_letter(value: str | None) -> bool:
    if not value:
        return False
    return any(char.isalpha() and char.isascii() for char in value)


def contains_non_ascii_letter(value: str | None) -> bool:
    if not value:
        return False
    return any(char.isalpha() and not char.isascii() for char in value)


def latin_transliteration_variants(value: str, limit: int = 32) -> list[str]:
    variants = [""]
    converted = False

    for char in (value or "").lower():
        replacements = _CYRILLIC_TO_LATIN.get(char)
        if replacements is None:
            replacements = (char if char.isalnum() else " ",)
        else:
            converted = True

        variants = [
            prefix + replacement
            for prefix in variants
            for replacement in replacements
        ][:limit]

    if not converted:
        return []

    normalized_variants = []
    seen = set()
    for variant in variants:
        normalized = normalize_lookup_text(variant)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_variants.append(normalized)

    return normalized_variants


def russian_transliteration_variant(value: str) -> str | None:
    if not value or not any(char.isascii() and char.isalpha() for char in value):
        return None

    result = []
    index = 0
    converted = False
    bracket_depth = 0

    while index < len(value):
        char = value[index]
        lower_tail = value[index:].lower()

        if char in "([":
            bracket_depth += 1
            result.append(char)
            index += 1
            continue

        if char in ")]" and bracket_depth:
            bracket_depth -= 1
            result.append(char)
            index += 1
            continue

        if bracket_depth:
            result.append(char)
            index += 1
            continue

        if char == "'":
            result.append("ь")
            converted = True
            index += 1
            continue

        matched = False
        for latin, cyrillic in _RU_TRANSLIT_TOKENS:
            if lower_tail.startswith(latin):
                result.append(cyrillic.upper() if char.isupper() else cyrillic)
                converted = True
                index += len(latin)
                matched = True
                break

        if matched:
            continue

        result.append(char)
        index += 1

    transliterated = "".join(result)
    return transliterated if converted and transliterated != value else None


def soundtrack_suffix_text(value: str | None) -> str:
    normalized = normalize_lookup_text(value)
    if not normalized:
        return ""

    words = set(normalized.split())
    if "soundtrack" in words or "ost" in words:
        return normalized
    if "score" in words and "picture" in words:
        return normalized
    if {"motion", "picture"} <= words and ("original" in words or "music" in words):
        return normalized
    if normalized in {"original score", "original soundtrack", "motion picture soundtrack"}:
        return normalized

    return ""


def strip_soundtrack_suffix(value: str) -> str:
    if not value:
        return ""

    stripped = value.strip()
    if not stripped:
        return ""

    changed = True
    while changed and stripped:
        changed = False
        for match in reversed(list(re.finditer(r"\([^)]*\)|\[[^]]*]", stripped))):
            if match.end() != len(stripped):
                continue
            suffix_text = soundtrack_suffix_text(match.group(0))
            if not suffix_text:
                continue
            stripped = stripped[:match.start()].rstrip()
            stripped = _SOUNDTRACK_TRAILING_SEPARATOR_RE.sub("", stripped).rstrip()
            changed = True
            break

    normalized_full = soundtrack_suffix_text(stripped)
    if normalized_full:
        return ""

    separator_match = re.search(r"\s(?:-|:|–|—)\s([^:—–-]+)$", stripped)
    if separator_match and soundtrack_suffix_text(separator_match.group(1)):
        stripped = stripped[:separator_match.start()].rstrip()

    return stripped.strip()


def normalize_album_title(value: str) -> str:
    if not value:
        return ""

    title = strip_soundtrack_suffix(strip_producer_suffix(value) or value)
    if title == "Unknown":
        title = value
    for part in re.findall(r"\([^)]*\)|\[[^]]*]", value):
        normalized_part = normalize_lookup_text(part)
        part_words = set(normalized_part.split())
        if any(word in normalized_part for word in VERSION_WORDS) or GENERIC_BRACKET_HINT_WORDS & part_words:
            title = title.replace(part, " ")

    words = [
        word for word in normalize_lookup_text(title).split()
        if word not in VERSION_WORDS
    ]
    if words[:1] in (["the"], ["a"], ["an"]):
        words = words[1:]

    return " ".join(words)


def album_title_variants(value: str | None) -> set[str]:
    if not value:
        return set()

    variants = set()
    stripped_value = strip_version_suffixes(strip_soundtrack_suffix(strip_producer_suffix(value) or value) or value)

    def add_variants(candidate: str | None) -> None:
        normalized = normalize_album_title(candidate or "")
        if normalized:
            variants.add(normalized)

        bracket_match = re.match(r"^(.*?)\s*[\(\[][^)\]]+[\)\]]\s*$", candidate or "")
        if bracket_match:
            head = normalize_album_title(bracket_match.group(1))
            if head:
                variants.add(head)

            content_match = re.search(r"[\(\[]([^)\]]+)[\)\]]\s*$", candidate or "")
            if content_match:
                head_text = bracket_match.group(1)
                content_text = content_match.group(1)
                # Treat trailing bracket text as a same-work alias only when it looks
                # like a script/locale gloss rather than a same-language subtitle.
                if (
                    (
                        contains_non_ascii_letter(head_text)
                        and contains_ascii_letter(content_text)
                    )
                    or (
                        contains_ascii_letter(head_text)
                        and contains_non_ascii_letter(content_text)
                    )
                ):
                    content = normalize_album_title(content_text)
                    if content:
                        variants.add(content)

        for separator in (":", " - ", " – ", " — "):
            if separator not in (candidate or ""):
                continue
            head = normalize_album_title((candidate or "").split(separator, 1)[0])
            if head:
                variants.add(head)

    add_variants(value)
    add_variants(stripped_value)

    transliterated = russian_transliteration_variant(value)
    transliterated_stripped = russian_transliteration_variant(stripped_value)
    add_variants(transliterated or "")
    add_variants(transliterated_stripped or "")

    return variants


def album_titles_match(left: str | None, right: str | None) -> bool:
    left_variants = album_title_variants(left)
    right_variants = album_title_variants(right)
    return bool(left_variants and right_variants and left_variants & right_variants)


def strict_album_title_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return normalize_lookup_text(left) == normalize_lookup_text(right)


def album_query_variants(album: str) -> list[str]:
    variants = []
    seen = set()

    for candidate in (album, *album_title_variants(album)):
        cleaned = " ".join((candidate or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        variants.append(cleaned)

    return variants


def title_variants(value: str) -> set[str]:
    cleaned_value = strip_version_suffixes(value)
    normalized = normalize_lookup_text(cleaned_value)
    if not normalized:
        return set()

    variants = {normalized}
    for candidate in (value, cleaned_value):
        for separator in (":", " - ", " – ", " — "):
            if separator in candidate:
                head = normalize_lookup_text(candidate.split(separator, 1)[0])
                if head:
                    variants.add(head)

    for candidate in album_title_variants(value):
        variants.add(candidate)

    return variants


def normalized_title_for_matching(value: str | None) -> str:
    cleaned = strip_version_suffixes(value or "")
    normalized = normalize_lookup_text(cleaned)
    if normalized:
        return normalized
    return normalize_lookup_text(value or "")


def split_credit_names(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in _ARTIST_CREDIT_SPLIT_RE.split(value) if part.strip()]


def artist_tokens(value: str) -> set[str]:
    return {token for token in normalize_lookup_text(value).split() if token}


def artist_match_variants(value: str) -> set[str]:
    normalized = normalize_lookup_text(value)
    variants = {normalized} if normalized else set()
    variants.update(latin_transliteration_variants(value))
    matching_normalized = normalize_lookup_text_for_matching(value)
    if matching_normalized:
        variants.add(matching_normalized)
    variants.update(
        normalize_lookup_text_for_matching(variant)
        for variant in list(variants)
        if variant
    )
    variants.discard("")
    return variants


def artist_match(candidate_artist: str, artist: str) -> tuple[bool, float]:
    candidate_variants = artist_match_variants(candidate_artist)
    artist_variants = artist_match_variants(artist)
    score = max(
        (
            fuzz.ratio(candidate_variant, artist_variant)
            for candidate_variant in candidate_variants
            for artist_variant in artist_variants
        ),
        default=0,
    )

    if not candidate_variants or not artist_variants:
        return False, score

    exact = bool(candidate_variants & artist_variants)
    token_subset = False

    for candidate_variant in candidate_variants:
        candidate_tokens = artist_tokens(candidate_variant)
        if len(candidate_tokens) < 2:
            continue

        for artist_variant in artist_variants:
            artist_tokens_set = artist_tokens(artist_variant)
            if (
                len(artist_tokens_set) >= 2
                and (
                    candidate_tokens.issubset(artist_tokens_set)
                    or artist_tokens_set.issubset(candidate_tokens)
                )
            ):
                token_subset = True
                break

        if token_subset:
            break

    return exact or token_subset or score >= 85, score


def any_artist_matches(candidate_artists: list[str], artist: str) -> tuple[bool, float]:
    matches = [artist_match(candidate_artist, artist) for candidate_artist in candidate_artists]
    if not matches:
        return False, 0

    matched = any(match for match, _score in matches)
    score = max(score for _match, score in matches)
    return matched, score


def version_penalty(value: str) -> int:
    normalized = normalize_lookup_text(value)
    return sum(1 for word in VERSION_WORDS if word in normalized)


def artist_query_variants(artist: str, include_transliteration: bool = True) -> list[str]:
    cleaned_artist = " ".join((artist or "").split()).strip()
    if not cleaned_artist:
        return []
    if not include_transliteration:
        return [cleaned_artist]

    variants = []
    seen = set()
    candidates = [
        cleaned_artist,
        normalize_lookup_text(cleaned_artist),
        cleaned_artist.replace("-", " "),
    ]
    candidates.extend(latin_transliteration_variants(cleaned_artist))

    for candidate in candidates:
        cleaned = " ".join((candidate or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        variants.append(cleaned)

    return variants


def deezer_album_query_artist_variants(artist: str, include_transliteration: bool = True) -> list[str]:
    variants = []
    seen = set()

    def add_candidate(value: str | None) -> None:
        cleaned = " ".join((value or "").split()).strip()
        if not cleaned:
            return
        key = normalize_lookup_text(cleaned)
        if not key or key in seen:
            return
        seen.add(key)
        variants.append(cleaned)

    for candidate in artist_query_variants(artist, include_transliteration=include_transliteration):
        add_candidate(candidate)

    split_names = split_credit_names(artist)
    if len(split_names) > 1 and include_transliteration:
        transliterated_split_names = []
        for name in split_names:
            add_candidate(name)
            canonical = normalize_lookup_text(name)
            add_candidate(canonical if canonical != normalize_lookup_text(artist) else None)
            transliterated = russian_transliteration_variant(name)
            if transliterated:
                add_candidate(transliterated)
            transliterated_split_names.append(transliterated or name)

        if any(transliterated != original for transliterated, original in zip(transliterated_split_names, split_names)):
            add_candidate(" & ".join(transliterated_split_names))

    return variants


def build_deezer_album_query_plan(
    artist: str,
    album: str,
    *,
    artist_query_mode: str = "expanded",
    include_album_only_queries: bool = True,
) -> list[QueryPlan]:
    plans: list[QueryPlan] = []
    seen = set()
    include_transliteration = artist_query_mode != "exact"
    album_variants = [album] if artist_query_mode == "exact" else list(album_query_variants(album))
    artist_variants = (
        artist_query_variants(artist, include_transliteration=False)
        if artist_query_mode == "exact"
        else deezer_album_query_artist_variants(artist, include_transliteration=include_transliteration)
    )

    for album_variant in album_variants:
        cleaned_album_variant = " ".join((album_variant or "").split()).strip()
        if not cleaned_album_variant:
            continue
        for artist_variant in artist_variants:
            query_templates = [
                f'artist:"{artist_variant}" album:"{cleaned_album_variant}"',
                f'artist:"{artist_variant}" "{cleaned_album_variant}"',
            ]
            if artist_query_mode != "exact":
                query_templates.append(f'"{artist_variant}" "{cleaned_album_variant}"')
            query_templates.append(f"{artist_variant} {cleaned_album_variant}")
            for index, query in enumerate(query_templates):
                if query in seen:
                    continue
                seen.add(query)
                plans.append(
                    QueryPlan(
                        phase="strong" if index < 2 else ("medium" if index == 2 else "broad"),
                        query=query,
                        entity="album",
                        strength="exact" if index == 0 else ("quoted" if index < 3 else "loose"),
                    )
                )
        if include_album_only_queries and cleaned_album_variant not in seen:
            seen.add(cleaned_album_variant)
            plans.append(QueryPlan(phase="broad", query=cleaned_album_variant, entity="album", strength="album-only"))

    return plans


def build_deezer_track_query_plan(
    artist: str,
    titles: list[str],
    *,
    artist_query_mode: str = "expanded",
) -> list[QueryPlan]:
    plans: list[QueryPlan] = []
    seen_queries = set()
    include_transliteration = artist_query_mode != "exact"

    for title in titles:
        cleaned_title = " ".join((title or "").split()).strip()
        if not cleaned_title:
            continue
        for artist_variant in artist_query_variants(artist, include_transliteration=include_transliteration):
            query_templates = [
                f'artist:"{artist_variant}" track:"{cleaned_title}"',
                f'artist:"{artist_variant}" "{cleaned_title}"',
            ]
            if artist_query_mode != "exact":
                query_templates.append(f'"{artist_variant}" "{cleaned_title}"')
            query_templates.append(f"{artist_variant} {cleaned_title}")
            for index, query in enumerate(query_templates):
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                plans.append(
                    QueryPlan(
                        phase="strong" if index < 2 else ("medium" if index == 2 else "broad"),
                        query=query,
                        entity="track",
                        strength="exact" if index == 0 else ("quoted" if index < 3 else "loose"),
                    )
                )
        if cleaned_title not in seen_queries:
            seen_queries.add(cleaned_title)
            plans.append(QueryPlan(phase="broad", query=cleaned_title, entity="track", strength="title-only"))

    return plans


def normalized_track_title_for_matching(value: str | None) -> str:
    """Track-title normalizer that preserves remix/live/acoustic markers, so a
    remix is not scored as identical to the original recording."""
    cleaned = strip_edition_suffixes(value or "")
    normalized = _normalize_lookup_text(cleaned)
    if normalized:
        return normalized
    return _normalize_lookup_text(value or "")


def normalized_title_sequence(titles: list[str] | tuple[str, ...] | None) -> list[str]:
    if not titles:
        return []

    return [
        normalized_track_title_for_matching(title)
        for title in titles
        if normalized_track_title_for_matching(title)
    ]


def track_title_sequence_score_from_titles(expected_titles: list[str] | tuple[str, ...], actual_titles: list[str] | tuple[str, ...]) -> float:
    expected = normalized_title_sequence(expected_titles)
    actual = normalized_title_sequence(actual_titles)

    if not expected or len(expected) != len(actual):
        return 0

    scores = [
        fuzz.ratio(expected_title, actual_title)
        for expected_title, actual_title in zip(expected, actual)
    ]
    return sum(scores) / len(scores)


def build_candidate_evidence(
    *,
    candidate_artists: list[str],
    requested_artist: str,
    candidate_title: str,
    requested_album: str,
    record_type: str | None = None,
    candidate_track_count: int | None = None,
    expected_track_count: int | None = None,
    preferred_release_type: str | None = None,
    track_title_sequence_score: float = 0.0,
    completeness_score: int = 0,
) -> CandidateEvidence:
    record_type_normalized = (record_type or "").lower()
    is_release = not record_type_normalized or record_type_normalized in ACCEPTED_RELEASE_TYPES
    title_match = album_titles_match(candidate_title, requested_album)
    strict_title_match = strict_album_title_match(candidate_title, requested_album)
    artist_matches, artist_score = any_artist_matches(candidate_artists, requested_artist)
    title_score = fuzz.ratio(
        normalized_title_for_matching(candidate_title),
        normalized_title_for_matching(requested_album),
    )
    type_match = bool(preferred_release_type and record_type_normalized == preferred_release_type)
    exact_track_count = bool(expected_track_count and candidate_track_count == expected_track_count)
    track_delta = abs((candidate_track_count or 0) - expected_track_count) if expected_track_count else 0

    if expected_track_count and expected_track_count > 1 and candidate_track_count == 1:
        is_release = False

    return CandidateEvidence(
        is_release=is_release,
        exact_track_count=exact_track_count,
        strict_title_match=strict_title_match,
        release_type_match=type_match,
        title_match=title_match,
        artist_match=artist_matches,
        artist_score=artist_score,
        title_score=title_score,
        track_title_sequence_score=track_title_sequence_score,
        track_delta=track_delta,
        version_penalty=version_penalty(candidate_title),
        completeness_score=completeness_score,
    )


def resolution_success(provider: str, metadata: dict, *, confidence: str | None = None, evidence: CandidateEvidence | dict | None = None) -> dict:
    if isinstance(evidence, CandidateEvidence):
        evidence = asdict(evidence)
    return ResolutionResult(
        provider=provider,
        success=True,
        metadata=metadata,
        reason=None,
        terminal=False,
        confidence=confidence,
        evidence=evidence,
    ).as_dict()


def resolution_failure(provider: str, reason: FailureReason, *, terminal: bool = True, confidence: str | None = None, evidence: CandidateEvidence | dict | None = None) -> dict:
    if isinstance(evidence, CandidateEvidence):
        evidence = asdict(evidence)
    return ResolutionResult(
        provider=provider,
        success=False,
        metadata=None,
        reason=reason,
        terminal=terminal,
        confidence=confidence,
        evidence=evidence,
    ).as_dict()


def metadata_completeness_score(metadata: dict | None) -> int:
    if not metadata:
        return 0

    score = 0
    if metadata.get("albumartist"):
        score += 1
    if metadata.get("releasetype") or metadata.get("record_type"):
        score += 1
    if metadata.get("date_iso"):
        score += 1
    if metadata.get("cover"):
        score += 1
    tracks = metadata.get("tracks") or []
    if isinstance(tracks, list) and tracks:
        score += 1
    return score


def provider_metadata_evidence(provider: str, metadata: dict | None, lookup: LookupInput) -> CandidateEvidence | None:
    if not metadata:
        return None

    tracks = metadata.get("tracks") or []
    track_titles = []
    if isinstance(tracks, list):
        track_titles = [str(track.get("title") or "") for track in tracks if isinstance(track, dict)]

    candidate_artists = [
        str(metadata.get("albumartist") or ""),
        str(metadata.get("artist") or ""),
    ]
    candidate_artists = [artist for artist in candidate_artists if artist]
    if not candidate_artists:
        candidate_artists = [lookup.artist]

    candidate_track_count = len(tracks) if isinstance(tracks, list) and tracks else metadata.get("expected_track_count")
    sequence_score = 100.0 if not lookup.expected_titles else track_title_sequence_score_from_titles(lookup.expected_titles, track_titles)
    evidence = build_candidate_evidence(
        candidate_artists=candidate_artists,
        requested_artist=lookup.artist,
        candidate_title=str(metadata.get("album") or metadata.get("title") or lookup.album),
        requested_album=lookup.album,
        record_type=str(metadata.get("releasetype") or metadata.get("record_type") or ""),
        candidate_track_count=candidate_track_count,
        expected_track_count=lookup.expected_track_count,
        preferred_release_type=lookup.preferred_release_type,
        track_title_sequence_score=sequence_score,
        completeness_score=metadata_completeness_score(metadata),
    )
    return evidence


def evidence_confidence(evidence: CandidateEvidence | None) -> str | None:
    if evidence is None:
        return None
    if evidence.exact_track_count and evidence.strict_title_match and evidence.artist_match and evidence.track_title_sequence_score >= 90:
        return "high"
    if evidence.exact_track_count and evidence.title_match and evidence.artist_match and evidence.track_title_sequence_score < 60:
        return "low"
    if evidence.exact_track_count and evidence.title_match and evidence.artist_match:
        return "high"
    if evidence.title_match and evidence.artist_match:
        return "medium"
    return "low"


def locale_track_sequence_title_rescue(
    evidence: CandidateEvidence | None,
    *,
    min_sequence_score: float = 95.0,
    min_artist_score: float = 60.0,
) -> bool:
    if evidence is None:
        return False
    return (
        evidence.is_release
        and not evidence.title_match
        and evidence.exact_track_count
        and evidence.track_title_sequence_score >= min_sequence_score
        and (evidence.artist_match or evidence.artist_score >= min_artist_score)
    )


def select_preferred_metadata_provider(
    deezer_metadata: dict | None,
    musicbrainz_metadata: dict | None,
    lookup: LookupInput,
) -> str | None:
    deezer_evidence = provider_metadata_evidence("deezer", deezer_metadata, lookup)
    musicbrainz_evidence = provider_metadata_evidence("musicbrainz", musicbrainz_metadata, lookup)

    if deezer_evidence and not musicbrainz_evidence:
        return "deezer"
    if musicbrainz_evidence and not deezer_evidence:
        return "musicbrainz"
    if not deezer_evidence and not musicbrainz_evidence:
        return None

    deezer_rank = deezer_evidence.deezer_rank()
    musicbrainz_rank = musicbrainz_evidence.musicbrainz_rank()
    if musicbrainz_rank > deezer_rank:
        return "musicbrainz"
    return "deezer"


def lookup_input_signature(lookup: LookupInput) -> tuple[str, str, int | None, tuple[str, ...], str]:
    return (
        normalize_lookup_text(lookup.artist),
        normalize_album_title(lookup.album),
        lookup.expected_track_count,
        tuple(str(title) for title in lookup.expected_titles if title),
        lookup.preferred_release_type.lower(),
    )
