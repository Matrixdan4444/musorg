from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
import math
import re

from rapidfuzz import fuzz

from musorg.core.library_preview import load_album_detail, scan_album_previews
from musorg.filesystem.scanner import SUPPORTED_FORMATS
from musorg.metadata.normalizer import normalize_lookup_text
from musorg.metadata.parser import read_tags

_LOSSLESS_FORMATS = {"flac", "wav", "aiff", "aif"}
_VARIANT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("japanese_edition", ("japanese edition", "japan edition", "japanese", "japan")),
    ("anniversary", ("anniversary",)),
    ("deluxe", ("deluxe", "super deluxe")),
    ("expanded", ("expanded", "bonus tracks", "bonus disc")),
    ("remaster", ("remaster", "remastered")),
    ("compilation", ("greatest hits", "best of", "anthology", "collection", "compilation")),
    ("live", ("live", "concert")),
    ("bootleg", ("bootleg", "unofficial")),
    ("vinyl_rip", ("vinyl rip", "lp rip", "needledrop")),
    ("web_release", ("web release", "web")),
    ("cd_rip", ("cd rip",)),
]
_VARIANT_STRIP_PATTERNS = (
    r"\bdeluxe\b",
    r"\bsuper deluxe\b",
    r"\bexpanded\b",
    r"\banniversary\b",
    r"\bbonus tracks?\b",
    r"\bbonus disc\b",
    r"\bremaster(?:ed)?\b",
    r"\blive\b",
    r"\bbootleg\b",
    r"\bunofficial\b",
    r"\bjapanese edition\b",
    r"\bjapan(?:ese)?\b",
    r"\bvinyl rip\b",
    r"\blp rip\b",
    r"\bneedledrop\b",
    r"\bweb release\b",
    r"\bcd rip\b",
)
_YEAR_PREFIX_RE = re.compile(r"^\d{4}\s*-\s*")
_BRACKET_RE = re.compile(r"[\(\[]([^\)\]]+)[\)\]]")


@dataclass(frozen=True)
class ReleaseAction:
    id: str
    label: str
    reason: str
    tone: str


@dataclass(frozen=True)
class ReleaseFacts:
    folder_path: str
    artist: str
    album_title: str
    year: str
    track_count: int
    issues: tuple[str, ...]
    metadata_intelligence: dict | None
    normalized_artist: str
    normalized_title: str
    base_title: str
    variant_type: str
    musicbrainz_release_ids: tuple[str, ...]
    normalized_track_titles: tuple[str, ...]
    durations: tuple[float, ...]
    total_duration: float
    avg_bitrate: int | None
    max_sample_rate: int | None
    max_bit_depth: int | None
    has_replaygain: bool
    artwork_pixels: int
    lossless: bool
    format_summary: str
    metadata_completeness: int
    provider_confidence: int
    quality_score: int
    fake_flac_status: str


@dataclass(frozen=True)
class ReleaseEdge:
    left: str
    right: str
    strength: str
    confidence: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseIntelligenceRegistry:
    summaries_by_path: dict[str, dict]
    related_payload_by_path: dict[str, dict]


def build_release_intelligence_registry(
    root_path: str,
    *,
    metadata_intelligence_by_path: dict[str, dict] | None = None,
) -> ReleaseIntelligenceRegistry:
    metadata_intelligence_by_path = metadata_intelligence_by_path or {}
    normalized_root = str(Path(root_path).expanduser().resolve())
    previews = scan_album_previews(normalized_root)
    facts_by_path = {
        facts.folder_path: facts
        for preview in previews
        for facts in [_build_release_facts(normalized_root, preview.folder_path, metadata_intelligence_by_path)]
        if facts is not None
    }
    if not facts_by_path:
        return ReleaseIntelligenceRegistry(summaries_by_path={}, related_payload_by_path={})

    strong_edges: list[ReleaseEdge] = []
    possible_edges: list[ReleaseEdge] = []
    paths = list(facts_by_path.keys())
    for index, left_path in enumerate(paths):
        for right_path in paths[index + 1:]:
            edge = _relationship_edge(facts_by_path[left_path], facts_by_path[right_path])
            if edge is None:
                continue
            if edge.strength in {"exact_duplicate", "near_duplicate", "related_release"}:
                strong_edges.append(edge)
            elif edge.strength == "possible_related_release":
                possible_edges.append(edge)

    family_members = _build_families(paths, strong_edges, facts_by_path)
    summaries_by_path: dict[str, dict] = {}
    related_payload_by_path: dict[str, dict] = {}
    possible_by_path = _edges_by_path(possible_edges)
    strong_by_path = _edges_by_path(strong_edges)

    for family_paths in family_members:
        family_facts = [facts_by_path[path] for path in family_paths]
        family_id = _family_id_for(family_facts)
        ranked_paths = _rank_family_paths(family_facts)
        for rank, path in enumerate(ranked_paths, start=1):
            facts = facts_by_path[path]
            strongest = max(strong_by_path.get(path, []), key=lambda item: item.confidence, default=None)
            possible = sorted(possible_by_path.get(path, []), key=lambda item: item.confidence, reverse=True)
            best_path = ranked_paths[0]
            best_facts = facts_by_path[best_path]
            status = _relationship_status(
                path=path,
                ranked_paths=ranked_paths,
                strongest=strongest,
                possible=possible,
                fake_flac_status=facts.fake_flac_status,
            )
            actions = _release_actions(
                facts,
                best_facts,
                status=status,
                ranked_paths=ranked_paths,
                strongest=strongest,
            )
            related_items = [
                _related_release_item(
                    member_facts=facts_by_path[member_path],
                    family_id=family_id,
                    rank=ranked_paths.index(member_path) + 1,
                    current=(member_path == path),
                    best_path=best_path,
                    strongest=strong_by_path.get(member_path, []),
                    status_override=_relationship_status(
                        path=member_path,
                        ranked_paths=ranked_paths,
                        strongest=max(strong_by_path.get(member_path, []), key=lambda item: item.confidence, default=None),
                        possible=possible_by_path.get(member_path, []),
                        fake_flac_status=facts_by_path[member_path].fake_flac_status,
                    ),
                )
                for member_path in ranked_paths
            ]
            possible_items = [
                _possible_related_item(path, edge, facts_by_path)
                for edge in possible
            ]
            summary = {
                "releaseFamilyId": family_id,
                "releaseVariantId": _variant_id_for(facts, family_id),
                "releaseVariantType": facts.variant_type,
                "relationshipStatus": status,
                "qualityScore": facts.quality_score,
                "qualityRank": rank,
                "duplicateConfidence": strongest.confidence if strongest else 0,
                "relatedReleaseCount": max(0, len(ranked_paths) - 1),
                "bestVersion": path == best_path and len(ranked_paths) > 1,
                "fakeFlacStatus": facts.fake_flac_status,
                "formatSummary": facts.format_summary,
                "reasons": _summary_reasons(facts, strongest, possible),
                "releaseActions": [
                    {
                        "id": action.id,
                        "label": action.label,
                        "reason": action.reason,
                        "tone": action.tone,
                    }
                    for action in actions
                ],
            }
            summaries_by_path[path] = summary
            related_payload_by_path[path] = {
                "albumId": "",
                "releaseFamilyId": family_id,
                "current": _related_release_item(
                    member_facts=facts,
                    family_id=family_id,
                    rank=rank,
                    current=True,
                    best_path=best_path,
                    strongest=strong_by_path.get(path, []),
                    status_override=status,
                ),
                "family": related_items,
                "possibleMatches": possible_items,
            }

    return ReleaseIntelligenceRegistry(
        summaries_by_path=summaries_by_path,
        related_payload_by_path=related_payload_by_path,
    )


def _build_release_facts(
    root_path: str,
    folder_path: str,
    metadata_intelligence_by_path: dict[str, dict],
) -> ReleaseFacts | None:
    normalized_folder = str(Path(folder_path).expanduser().resolve())
    detail = load_album_detail(normalized_folder, root_path)
    audio_files = _album_audio_files(normalized_folder)
    if not audio_files:
        return None
    tags = [read_tags(str(path)) for path in audio_files]
    tags = [item for item in tags if item]
    if not tags:
        return None
    normalized_artist = normalize_lookup_text(detail.album_artist or detail.artist_name)
    normalized_title = _normalized_display_title(detail.album_title)
    base_title = _base_release_title(detail.album_title)
    durations = tuple(float(item.get("duration_seconds") or 0.0) for item in tags if item.get("duration_seconds"))
    total_duration = round(sum(durations), 3)
    bitrates = [int(item.get("bitrate") or 0) for item in tags if item.get("bitrate")]
    sample_rates = [int(item.get("sample_rate") or 0) for item in tags if item.get("sample_rate")]
    bit_depths = [int(item.get("bit_depth") or 0) for item in tags if item.get("bit_depth")]
    formats = [str(item.get("format") or "").lower() for item in tags if item.get("format")]
    format_counter = Counter(formats)
    artwork_pixels = max((int(item.get("cover_width") or 0) * int(item.get("cover_height") or 0) for item in tags), default=0)
    replaygain_hits = sum(1 for item in tags if item.get("has_replaygain"))
    metadata_completeness = _metadata_completeness(detail, tags)
    metadata_intelligence = metadata_intelligence_by_path.get(normalized_folder)
    provider_confidence = _provider_confidence_score(metadata_intelligence)
    lossless = bool(formats) and all(format_name in _LOSSLESS_FORMATS for format_name in formats)
    quality_score = _quality_score(
        lossless=lossless,
        avg_bitrate=round(sum(bitrates) / len(bitrates)) if bitrates else None,
        max_sample_rate=max(sample_rates) if sample_rates else None,
        max_bit_depth=max(bit_depths) if bit_depths else None,
        artwork_pixels=artwork_pixels,
        metadata_completeness=metadata_completeness,
        provider_confidence=provider_confidence,
        replaygain_ratio=replaygain_hits / len(tags) if tags else 0.0,
        track_count=len(tags),
        issue_count=len(detail.issues),
    )
    mb_release_ids = tuple(sorted({
        normalize_lookup_text(str(item.get("musicbrainz_release_id") or ""))
        for item in tags
        if str(item.get("musicbrainz_release_id") or "").strip()
    }))
    return ReleaseFacts(
        folder_path=normalized_folder,
        artist=detail.artist_name,
        album_title=detail.album_title,
        year=detail.release_year,
        track_count=len(tags),
        issues=detail.issues,
        metadata_intelligence=metadata_intelligence,
        normalized_artist=normalized_artist,
        normalized_title=normalized_title,
        base_title=base_title,
        variant_type=_variant_type(detail.album_title),
        musicbrainz_release_ids=mb_release_ids,
        normalized_track_titles=tuple(_normalized_track_title(str(item.get("title") or "")) for item in tags),
        durations=tuple(round(float(item.get("duration_seconds") or 0.0), 3) for item in tags),
        total_duration=total_duration,
        avg_bitrate=round(sum(bitrates) / len(bitrates)) if bitrates else None,
        max_sample_rate=max(sample_rates) if sample_rates else None,
        max_bit_depth=max(bit_depths) if bit_depths else None,
        has_replaygain=replaygain_hits > 0,
        artwork_pixels=artwork_pixels,
        lossless=lossless,
        format_summary=_format_summary(format_counter, lossless, bitrates),
        metadata_completeness=metadata_completeness,
        provider_confidence=provider_confidence,
        quality_score=quality_score,
        fake_flac_status="none",
    )


def _album_audio_files(folder_path: str) -> list[Path]:
    folder = Path(folder_path).expanduser()
    try:
        return sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS
        )
    except OSError:
        return []


def _variant_type(title: str) -> str:
    normalized = _normalized_display_title(title)
    for variant_type, keywords in _VARIANT_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return variant_type
    return "original"


def _base_release_title(title: str) -> str:
    normalized = _normalized_display_title(title)
    cleaned = _YEAR_PREFIX_RE.sub("", normalized)
    for pattern in _VARIANT_STRIP_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return cleaned or normalized


def _normalized_display_title(title: str) -> str:
    normalized = normalize_lookup_text(title)
    return _YEAR_PREFIX_RE.sub("", normalized)


def _normalized_track_title(title: str) -> str:
    return normalize_lookup_text(title)


def _metadata_completeness(detail, tags: list[dict]) -> int:
    score = 0
    if normalize_lookup_text(detail.album_artist):
        score += 20
    if normalize_lookup_text(detail.genre):
        score += 10
    if normalize_lookup_text(detail.release_year):
        score += 10
    if tags and all(normalize_lookup_text(str(item.get("title") or "")) for item in tags):
        score += 20
    if tags and all(str(item.get("tracknumber") or "").strip() not in {"", "0"} for item in tags):
        score += 15
    if tags and all(str(item.get("artist") or "").strip() not in {"", "Unknown artist"} for item in tags):
        score += 15
    if not detail.issues:
        score += 10
    return min(100, score)


def _provider_confidence_score(metadata_intelligence: dict | None) -> int:
    if not metadata_intelligence:
        return 0
    confidence = metadata_intelligence.get("confidence") or {}
    try:
        return max(0, min(100, int(confidence.get("score") or 0)))
    except (TypeError, ValueError):
        return 0


def _quality_score(
    *,
    lossless: bool,
    avg_bitrate: int | None,
    max_sample_rate: int | None,
    max_bit_depth: int | None,
    artwork_pixels: int,
    metadata_completeness: int,
    provider_confidence: int,
    replaygain_ratio: float,
    track_count: int,
    issue_count: int,
) -> int:
    score = 0
    score += 30 if lossless else 10
    if avg_bitrate:
        if avg_bitrate >= 900000:
            score += 12
        elif avg_bitrate >= 320000:
            score += 10
        elif avg_bitrate >= 256000:
            score += 8
        elif avg_bitrate >= 192000:
            score += 6
        else:
            score += 3
    if max_sample_rate:
        if max_sample_rate >= 96000:
            score += 10
        elif max_sample_rate >= 48000:
            score += 7
        elif max_sample_rate >= 44100:
            score += 5
    if max_bit_depth:
        if max_bit_depth >= 24:
            score += 8
        elif max_bit_depth >= 16:
            score += 4
    if artwork_pixels >= 3000 * 3000:
        score += 10
    elif artwork_pixels >= 1000 * 1000:
        score += 6
    elif artwork_pixels > 0:
        score += 3
    score += round(metadata_completeness * 0.15)
    score += round(provider_confidence * 0.08)
    score += round(replaygain_ratio * 6)
    if track_count >= 10:
        score += 5
    score -= min(12, issue_count * 3)
    return max(0, min(100, score))


def _relationship_edge(left: ReleaseFacts, right: ReleaseFacts) -> ReleaseEdge | None:
    if left.folder_path == right.folder_path:
        return None

    shared_mb = set(left.musicbrainz_release_ids) & set(right.musicbrainz_release_ids)
    title_similarity = fuzz.ratio(left.base_title, right.base_title) if left.base_title and right.base_title else 0
    artist_similarity = fuzz.ratio(left.normalized_artist, right.normalized_artist) if left.normalized_artist and right.normalized_artist else 0
    if not shared_mb and artist_similarity < 92:
        return None
    if not shared_mb and title_similarity < 88:
        return None

    overlap_ratio = _track_overlap_ratio(left.normalized_track_titles, right.normalized_track_titles)
    total_duration_delta_ratio = _duration_delta_ratio(left.total_duration, right.total_duration)
    exact_track_titles = left.normalized_track_titles == right.normalized_track_titles
    exact_track_count = left.track_count == right.track_count
    same_variant = left.variant_type == right.variant_type
    same_year = left.year and right.year and left.year == right.year

    confidence = 0
    reasons: list[str] = []
    if shared_mb:
        confidence += 45
        reasons.append("MusicBrainz release ID matches.")
    if artist_similarity >= 98:
        confidence += 18
        reasons.append("Artist metadata matches exactly.")
    elif artist_similarity >= 92:
        confidence += 12
        reasons.append("Artist metadata is highly similar.")
    if title_similarity >= 98:
        confidence += 18
        reasons.append("Album titles match exactly after normalization.")
    elif title_similarity >= 90:
        confidence += 12
        reasons.append("Album titles are highly similar after normalization.")
    if exact_track_titles and exact_track_count:
        confidence += 25
        reasons.append(f"{left.track_count}/{right.track_count} track titles matched in order.")
    elif overlap_ratio >= 0.9:
        confidence += 18
        reasons.append(f"{round(overlap_ratio * 100)}% of track titles matched.")
    elif overlap_ratio >= 0.75:
        confidence += 10
        reasons.append(f"{round(overlap_ratio * 100)}% of track titles matched.")
    if total_duration_delta_ratio <= 0.02:
        confidence += 15
        reasons.append("Total runtime delta is under 2%.")
    elif total_duration_delta_ratio <= 0.05:
        confidence += 8
        reasons.append("Total runtime delta is under 5%.")
    if same_year:
        confidence += 5
        reasons.append("Release year matches.")
    if not reasons:
        return None

    if exact_track_titles and exact_track_count and total_duration_delta_ratio <= 0.02 and same_variant:
        strength = "exact_duplicate"
    elif overlap_ratio >= 0.9 and total_duration_delta_ratio <= 0.05:
        strength = "near_duplicate"
    elif confidence >= 55:
        strength = "related_release"
    elif confidence >= 40:
        strength = "possible_related_release"
    else:
        return None

    return ReleaseEdge(
        left=left.folder_path,
        right=right.folder_path,
        strength=strength,
        confidence=min(100, confidence),
        reasons=tuple(reasons),
    )


def _track_overlap_ratio(left_titles: tuple[str, ...], right_titles: tuple[str, ...]) -> float:
    if not left_titles or not right_titles:
        return 0.0
    left_counter = Counter(left_titles)
    right_counter = Counter(right_titles)
    shared = sum(min(left_counter[key], right_counter[key]) for key in left_counter.keys() | right_counter.keys())
    return shared / max(len(left_titles), len(right_titles))


def _duration_delta_ratio(left: float, right: float) -> float:
    if left <= 0 or right <= 0:
        return 1.0
    return abs(left - right) / max(left, right)


def _build_families(paths: list[str], edges: list[ReleaseEdge], facts_by_path: dict[str, ReleaseFacts]) -> list[list[str]]:
    parents = {path: path for path in paths}

    def find(path: str) -> str:
        while parents[path] != path:
            parents[path] = parents[parents[path]]
            path = parents[path]
        return path

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for edge in edges:
        union(edge.left, edge.right)

    groups: dict[str, list[str]] = {}
    for path in paths:
        groups.setdefault(find(path), []).append(path)

    families = []
    for member_paths in groups.values():
        families.append(sorted(member_paths, key=lambda item: (
            facts_by_path[item].normalized_artist,
            facts_by_path[item].base_title,
            facts_by_path[item].album_title,
            item,
        )))
    families.sort(key=lambda family: (
        facts_by_path[family[0]].normalized_artist,
        facts_by_path[family[0]].base_title,
        family[0],
    ))
    return families


def _rank_family_paths(facts_list: list[ReleaseFacts]) -> list[str]:
    return [
        facts.folder_path
        for facts in sorted(
            facts_list,
            key=lambda item: (
                -item.quality_score,
                -item.metadata_completeness,
                -item.artwork_pixels,
                0 if item.lossless else 1,
                -item.track_count,
                item.variant_type != "original",
                item.album_title.lower(),
                item.folder_path,
            ),
        )
    ]


def _family_id_for(facts_list: list[ReleaseFacts]) -> str:
    anchor = min(
        facts_list,
        key=lambda item: (
            item.normalized_artist,
            item.base_title,
            item.track_count,
            item.folder_path,
        ),
    )
    raw = f"{anchor.normalized_artist}|{anchor.base_title}"
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def _variant_id_for(facts: ReleaseFacts, family_id: str) -> str:
    raw = f"{family_id}|{facts.normalized_title}|{facts.track_count}|{round(facts.total_duration)}"
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def _edges_by_path(edges: list[ReleaseEdge]) -> dict[str, list[ReleaseEdge]]:
    result: dict[str, list[ReleaseEdge]] = {}
    for edge in edges:
        result.setdefault(edge.left, []).append(edge)
        result.setdefault(edge.right, []).append(edge)
    return result


def _relationship_status(
    *,
    path: str,
    ranked_paths: list[str],
    strongest: ReleaseEdge | None,
    possible: list[ReleaseEdge],
    fake_flac_status: str,
) -> str:
    if fake_flac_status == "suspicious":
        return "suspicious_release"
    if len(ranked_paths) <= 1:
        return "possible_related_release" if possible else "standalone"
    if path == ranked_paths[0]:
        return "best_version"
    if strongest and strongest.strength == "exact_duplicate":
        return "exact_duplicate"
    if strongest and strongest.strength == "near_duplicate":
        return "near_duplicate"
    return "better_version_available" if len(ranked_paths) > 1 else "related_release"


def _release_actions(
    facts: ReleaseFacts,
    best_facts: ReleaseFacts,
    *,
    status: str,
    ranked_paths: list[str],
    strongest: ReleaseEdge | None,
) -> list[ReleaseAction]:
    actions: list[ReleaseAction] = []
    if status == "best_version":
        actions.append(ReleaseAction("keep_best_version", "Keep best version", "This release currently ranks highest in its family.", "success"))
    if status in {"exact_duplicate", "near_duplicate"}:
        actions.append(ReleaseAction("archive_duplicate", "Archive duplicate", "Another copy in this family looks equal or better.", "warning"))
    if not facts.lossless and best_facts.lossless and best_facts.folder_path != facts.folder_path:
        actions.append(ReleaseAction("replace_lossy_release", "Replace lossy release", "A lossless family member is available with a stronger quality score.", "warning"))
    if facts.artwork_pixels < best_facts.artwork_pixels and best_facts.folder_path != facts.folder_path:
        actions.append(ReleaseAction("replace_artwork", "Replace artwork", "A related release has stronger artwork quality.", "info"))
    if facts.metadata_completeness < best_facts.metadata_completeness and best_facts.folder_path != facts.folder_path:
        actions.append(ReleaseAction("merge_metadata", "Merge metadata", "A related release has cleaner metadata coverage.", "info"))
    if facts.variant_type in {"deluxe", "expanded", "live", "anniversary", "japanese_edition"} and len(ranked_paths) > 1:
        actions.append(ReleaseAction("keep_both", "Keep both releases", "This looks like a meaningful alternate edition rather than a disposable duplicate.", "success"))
    if facts.fake_flac_status != "none":
        actions.append(ReleaseAction("mark_suspicious_release", "Mark suspicious release", "Audio-quality heuristics flagged this release for review.", "danger"))
    if not actions and strongest:
        actions.append(ReleaseAction("keep_best_version", "Review best version", "This release is related to another version and may need a keep-or-archive decision.", "info"))
    return actions


def _summary_reasons(facts: ReleaseFacts, strongest: ReleaseEdge | None, possible: list[ReleaseEdge]) -> list[str]:
    reasons = [
        f"Format: {facts.format_summary}.",
        f"Quality score: {facts.quality_score}/100.",
    ]
    if strongest:
        reasons.extend(strongest.reasons[:3])
    elif possible:
        reasons.append("A possible related release was detected, but the match stayed below the merge threshold.")
    return reasons


def _related_release_item(
    *,
    member_facts: ReleaseFacts,
    family_id: str,
    rank: int,
    current: bool,
    best_path: str,
    strongest: list[ReleaseEdge],
    status_override: str,
) -> dict:
    strongest_edge = max(strongest, key=lambda item: item.confidence, default=None)
    return {
        "releaseFamilyId": family_id,
        "releaseVariantId": _variant_id_for(member_facts, family_id),
        "title": member_facts.album_title,
        "artist": member_facts.artist,
        "year": member_facts.year or "Unknown",
        "trackCount": member_facts.track_count,
        "formatSummary": member_facts.format_summary,
        "qualityScore": member_facts.quality_score,
        "qualityRank": rank,
        "bestVersion": member_facts.folder_path == best_path,
        "releaseVariantType": member_facts.variant_type,
        "relationshipStatus": status_override,
        "duplicateConfidence": strongest_edge.confidence if strongest_edge else 0,
        "fakeFlacStatus": member_facts.fake_flac_status,
        "reasons": _summary_reasons(member_facts, strongest_edge, []),
        "releaseActions": [],
        "current": current,
    }


def _possible_related_item(current_path: str, edge: ReleaseEdge, facts_by_path: dict[str, ReleaseFacts]) -> dict:
    other_path = edge.right if edge.left == current_path else edge.left
    other = facts_by_path[other_path]
    family_id = _family_id_for([facts_by_path[current_path], other])
    return {
        "releaseFamilyId": family_id,
        "releaseVariantId": _variant_id_for(other, family_id),
        "title": other.album_title,
        "artist": other.artist,
        "year": other.year or "Unknown",
        "trackCount": other.track_count,
        "formatSummary": other.format_summary,
        "qualityScore": other.quality_score,
        "qualityRank": 0,
        "bestVersion": False,
        "releaseVariantType": other.variant_type,
        "relationshipStatus": "possible_related_release",
        "duplicateConfidence": edge.confidence,
        "fakeFlacStatus": other.fake_flac_status,
        "reasons": list(edge.reasons),
        "releaseActions": [],
        "current": False,
    }


def _format_summary(format_counter: Counter[str], lossless: bool, bitrates: list[int]) -> str:
    if not format_counter:
        return "Unknown"
    primary_format = format_counter.most_common(1)[0][0].upper()
    if lossless:
        return primary_format
    if bitrates:
        return f"{primary_format} {round(sum(bitrates) / len(bitrates) / 1000)}"
    return primary_format
