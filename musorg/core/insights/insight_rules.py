from __future__ import annotations

from musorg.core.insights.insight_templates import (
    best_version_copy,
    better_version_copy,
    edition_variant_copy,
    exact_duplicate_copy,
    lossy_lossless_family_copy,
    metadata_complete_copy,
    multiple_variants_copy,
    near_duplicate_copy,
    possible_related_copy,
    remaster_family_copy,
    suspicious_audio_copy,
)
from musorg.core.insights.insight_types import InsightItem


def build_album_insights(
    *,
    path: str,
    summary: dict | None,
    related_payload: dict | None,
    metadata_intelligence: dict | None,
    variant_paths: dict[str, str],
) -> tuple[list[InsightItem], list[InsightItem], str | None]:
    if not summary or not related_payload:
        return [], [], None

    album_insights: list[InsightItem] = []
    family_insights: list[InsightItem] = []

    relationship_status = str(summary.get("relationshipStatus") or "standalone")
    best_version = bool(summary.get("bestVersion"))
    fake_flac_status = str(summary.get("fakeFlacStatus") or "none")
    variant_type = str(summary.get("releaseVariantType") or "unknown")
    quality_score = int(summary.get("qualityScore") or 0)
    family_items = [item for item in related_payload.get("family", []) if isinstance(item, dict)]
    possible_matches = [item for item in related_payload.get("possibleMatches", []) if isinstance(item, dict)]
    best_item = next((item for item in family_items if item.get("bestVersion")), None)
    best_related_path = _path_for_item(best_item, variant_paths)
    related_paths = tuple(
        sorted(
            {
                related_path
                for item in family_items
                if (related_path := _path_for_item(item, variant_paths)) and related_path != path
            }
        )
    )

    if fake_flac_status != "none":
        title, message = suspicious_audio_copy(fake_flac_status)
        album_insights.append(InsightItem(
            id=f"{path}:suspicious-audio",
            category="suspicious_audio",
            severity="danger" if fake_flac_status == "suspicious" else "warning",
            title=title,
            message=message,
            reasoning=_compact_reasons(
                [
                    "The stored audio profile looks less trustworthy than the container suggests.",
                    *summary.get("reasons", []),
                ],
            ),
            confidence=_confidence_from_status(fake_flac_status),
            related_paths=related_paths,
            actionable=True,
            recommendation_type="review_audio",
            generated_at=None,
            scope="album",
            priority=100,
            dedupe_key="suspicious_audio:source",
        ))

    if best_version or relationship_status == "best_version":
        title, message = best_version_copy()
        album_insights.append(InsightItem(
            id=f"{path}:best-version",
            category="recommendation",
            severity="success",
            title=title,
            message=message,
            reasoning=_compact_reasons(
                [
                    f"Quality score is {quality_score}/100.",
                    *summary.get("reasons", []),
                    *_metadata_reasoning(metadata_intelligence),
                ],
            ),
            confidence=max(80, int(summary.get("duplicateConfidence") or 0)),
            related_paths=related_paths,
            actionable=True,
            recommendation_type="keep_primary",
            generated_at=None,
            scope="album",
            priority=90,
            dedupe_key="recommendation:keep_primary",
        ))

    if relationship_status in {"better_version_available", "exact_duplicate", "near_duplicate"} and not best_version:
        title, message = better_version_copy()
        better_paths = tuple(path_value for path_value in (best_related_path,) if path_value and path_value != path)
        album_insights.append(InsightItem(
            id=f"{path}:better-version-available",
            category="recommendation",
            severity="warning",
            title=title,
            message=message,
            reasoning=_compact_reasons(
                [
                    "This copy is not the highest-ranked version in the family.",
                    *summary.get("reasons", []),
                ],
            ),
            confidence=max(70, int(summary.get("duplicateConfidence") or 0)),
            related_paths=better_paths,
            actionable=True,
            recommendation_type="replace_weaker",
            generated_at=None,
            scope="album",
            priority=85,
            dedupe_key="recommendation:replace_weaker",
        ))

    if relationship_status == "exact_duplicate":
        title, message = exact_duplicate_copy()
        album_insights.append(InsightItem(
            id=f"{path}:exact-duplicate",
            category="duplicate",
            severity="warning",
            title=title,
            message=message,
            reasoning=_compact_reasons(summary.get("reasons", [])),
            confidence=max(75, int(summary.get("duplicateConfidence") or 0)),
            related_paths=related_paths,
            actionable=True,
            recommendation_type="replace_weaker",
            generated_at=None,
            scope="album",
            priority=70,
            dedupe_key="duplicate:exact",
        ))
    elif relationship_status == "near_duplicate":
        title, message = near_duplicate_copy()
        album_insights.append(InsightItem(
            id=f"{path}:near-duplicate",
            category="duplicate",
            severity="warning",
            title=title,
            message=message,
            reasoning=_compact_reasons(summary.get("reasons", [])),
            confidence=max(65, int(summary.get("duplicateConfidence") or 0)),
            related_paths=related_paths,
            actionable=True,
            recommendation_type="keep_both",
            generated_at=None,
            scope="album",
            priority=68,
            dedupe_key="duplicate:near",
        ))

    if relationship_status == "possible_related_release" or possible_matches:
        title, message = possible_related_copy()
        possible_paths = tuple(
            sorted(
                {
                    candidate_path
                    for item in possible_matches
                    if (candidate_path := _path_for_item(item, variant_paths)) and candidate_path != path
                }
            )
        )
        album_insights.append(InsightItem(
            id=f"{path}:possible-related",
            category="collection",
            severity="neutral",
            title=title,
            message=message,
            reasoning=_compact_reasons(summary.get("reasons", [])),
            confidence=max(40, int(summary.get("duplicateConfidence") or 0)),
            related_paths=possible_paths,
            actionable=False,
            recommendation_type=None,
            generated_at=None,
            scope="album",
            priority=45,
            dedupe_key="collection:possible_related",
        ))

    if variant_type not in {"original", "unknown"}:
        variant_label = variant_type.replace("_", " ")
        title, message = edition_variant_copy(variant_label)
        album_insights.append(InsightItem(
            id=f"{path}:variant:{variant_type}",
            category="collection",
            severity="neutral",
            title=title,
            message=message,
            reasoning=_compact_reasons(
                [
                    f"Variant type resolved as {variant_label}.",
                    *summary.get("reasons", [])[:1],
                ],
            ),
            confidence=60,
            related_paths=related_paths,
            actionable=False,
            recommendation_type=None,
            generated_at=None,
            scope="album",
            priority=42,
            dedupe_key=f"collection:variant:{variant_type}",
        ))

    if _metadata_appears_complete(metadata_intelligence, summary):
        title, message = metadata_complete_copy()
        album_insights.append(InsightItem(
            id=f"{path}:metadata-complete",
            category="quality",
            severity="success",
            title=title,
            message=message,
            reasoning=_compact_reasons(_metadata_reasoning(metadata_intelligence)),
            confidence=int(((metadata_intelligence or {}).get("confidence") or {}).get("score") or 70),
            related_paths=(),
            actionable=False,
            recommendation_type=None,
            generated_at=None,
            scope="album",
            priority=25,
            dedupe_key="quality:metadata_complete",
        ))

    family_count = len(family_items)
    if family_count > 1:
        title, message = multiple_variants_copy(family_count)
        family_insights.append(InsightItem(
            id=f"{path}:family-count",
            category="collection",
            severity="neutral",
            title=title,
            message=message,
            reasoning=_compact_reasons([f"This family currently contains {family_count} owned releases."]),
            confidence=85,
            related_paths=related_paths,
            actionable=False,
            recommendation_type=None,
            generated_at=None,
            scope="family",
            priority=55,
            dedupe_key="collection:multiple_variants",
        ))

    variant_types = {str(item.get("releaseVariantType") or "unknown") for item in family_items}
    if "remaster" in variant_types and any(item not in {"remaster", "unknown"} for item in variant_types):
        title, message = remaster_family_copy()
        family_insights.append(InsightItem(
            id=f"{path}:remaster-family",
            category="collection",
            severity="neutral",
            title=title,
            message=message,
            reasoning=_compact_reasons(["The family includes remaster and non-remaster variants."]),
            confidence=80,
            related_paths=related_paths,
            actionable=False,
            recommendation_type=None,
            generated_at=None,
            scope="family",
            priority=54,
            dedupe_key="collection:remaster_family",
        ))

    format_summaries = {str(item.get("formatSummary") or "").upper() for item in family_items}
    has_lossless = any(summary_value in {"FLAC", "WAV", "AIFF", "AIF"} for summary_value in format_summaries)
    has_lossy = any(summary_value and summary_value not in {"FLAC", "WAV", "AIFF", "AIF"} for summary_value in format_summaries)
    if has_lossless and has_lossy:
        title, message = lossy_lossless_family_copy()
        family_insights.append(InsightItem(
            id=f"{path}:format-mix",
            category="collection",
            severity="neutral",
            title=title,
            message=message,
            reasoning=_compact_reasons(["Different format classes are present in the same release family."]),
            confidence=75,
            related_paths=related_paths,
            actionable=False,
            recommendation_type=None,
            generated_at=None,
            scope="family",
            priority=53,
            dedupe_key="collection:format_mix",
        ))

    recommendation_summary = _recommendation_summary(album_insights)
    return album_insights, family_insights, recommendation_summary


def _recommendation_summary(items: list[InsightItem]) -> str | None:
    for item in sorted(items, key=lambda entry: (-entry.priority, entry.title.lower())):
        if item.recommendation_type == "review_audio":
            return "Review audio provenance before keeping this as the primary version."
        if item.recommendation_type == "keep_primary":
            return "Recommended as primary version."
        if item.recommendation_type == "replace_weaker":
            return "A stronger version is already available in this family."
    return items[0].message if items else None


def _metadata_appears_complete(metadata_intelligence: dict | None, summary: dict) -> bool:
    if not metadata_intelligence:
        return False
    confidence = (metadata_intelligence.get("confidence") or {})
    suspicious = metadata_intelligence.get("suspiciousMetadata") or []
    if suspicious:
        return False
    if str(confidence.get("level") or "") != "high":
        return False
    return str(summary.get("relationshipStatus") or "") not in {"possible_related_release", "suspicious_release"}


def _metadata_reasoning(metadata_intelligence: dict | None) -> list[str]:
    if not metadata_intelligence:
        return []
    confidence = metadata_intelligence.get("confidence") or {}
    score = confidence.get("score")
    provider_decisions = metadata_intelligence.get("providerDecisions") or {}
    provider = provider_decisions.get("metadataProvider")
    reasons = list(confidence.get("reasons") or [])
    base = []
    if isinstance(score, int):
        base.append(f"Metadata confidence is {score}/100.")
    if provider:
        base.append(f"Metadata provider: {provider}.")
    return [*base, *reasons]


def _path_for_item(item: dict | None, variant_paths: dict[str, str]) -> str:
    if not item:
        return ""
    release_variant_id = str(item.get("releaseVariantId") or "")
    return variant_paths.get(release_variant_id, "")


def _confidence_from_status(status: str) -> int:
    if status == "suspicious":
        return 88
    if status == "likely":
        return 78
    return 62


def _compact_reasons(reasons: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    compact: list[str] = []
    for reason in reasons:
        cleaned = str(reason).strip()
        if not cleaned or cleaned in seen:
            continue
        compact.append(cleaned)
        seen.add(cleaned)
        if len(compact) >= 3:
            break
    return tuple(compact)
