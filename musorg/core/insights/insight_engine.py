from __future__ import annotations

from musorg.core.insights.insight_priorities import summarize_insights
from musorg.core.insights.insight_rules import build_album_insights
from musorg.core.insights.insight_types import InsightItem, InsightRegistry
from musorg.core.release_intelligence import ReleaseIntelligenceRegistry


def build_insight_registry(
    release_registry: ReleaseIntelligenceRegistry,
    metadata_intelligence_by_path: dict[str, dict] | None = None,
) -> InsightRegistry:
    metadata_intelligence_by_path = metadata_intelligence_by_path or {}
    summaries_by_path: dict[str, dict] = {}
    payloads_by_path: dict[str, dict] = {}
    variant_paths = {
        str(summary.get("releaseVariantId") or ""): path
        for path, summary in release_registry.summaries_by_path.items()
        if summary.get("releaseVariantId")
    }

    for path, summary in release_registry.summaries_by_path.items():
        related_payload = release_registry.related_payload_by_path.get(path)
        album_insights, family_insights, recommendation_summary = build_album_insights(
            path=path,
            summary=summary,
            related_payload=related_payload,
            metadata_intelligence=metadata_intelligence_by_path.get(path),
            variant_paths=variant_paths,
        )
        ordered = [*album_insights, *family_insights]
        top, summary_items = summarize_insights(ordered)
        summaries_by_path[path] = {
            "topInsight": _serialize_item(top) if top else None,
            "insightSummary": [_serialize_item(item) for item in summary_items],
            "insightCount": len(ordered),
        }
        payloads_by_path[path] = {
            "albumId": "",
            "topInsight": _serialize_item(top) if top else None,
            "insightSummary": [_serialize_item(item) for item in summary_items],
            "insightCount": len(ordered),
            "recommendationSummary": recommendation_summary,
            "albumInsights": [_serialize_item(item) for item in album_insights],
            "familyInsights": [_serialize_item(item) for item in family_insights],
        }

    return InsightRegistry(
        summaries_by_path=summaries_by_path,
        payloads_by_path=payloads_by_path,
    )


def _serialize_item(item: InsightItem) -> dict:
    return {
        "id": item.id,
        "category": item.category,
        "severity": item.severity,
        "title": item.title,
        "message": item.message,
        "reasoning": list(item.reasoning),
        "confidence": item.confidence,
        "relatedAlbumPaths": list(item.related_paths),
        "actionable": item.actionable,
        "recommendationType": item.recommendation_type,
        "generatedAt": item.generated_at,
        "scope": item.scope,
    }
