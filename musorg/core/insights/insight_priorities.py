from __future__ import annotations

from musorg.core.insights.insight_types import InsightItem


_LOW_VALUE_DEDUPE_KEYS = {
    "quality:metadata_complete",
    "collection:multiple_variants",
}


def sort_insights(items: list[InsightItem]) -> list[InsightItem]:
    return sorted(items, key=lambda item: (-item.priority, item.scope != "album", item.title.lower(), item.id))


def dedupe_insights(items: list[InsightItem]) -> list[InsightItem]:
    deduped: dict[str, InsightItem] = {}
    for item in sort_insights(items):
        existing = deduped.get(item.dedupe_key)
        if existing is None or item.priority > existing.priority:
            deduped[item.dedupe_key] = item
    return sort_insights(list(deduped.values()))


def suppress_low_value_noise(items: list[InsightItem]) -> list[InsightItem]:
    if not items:
        return []
    has_high_signal = any(item.priority >= 70 for item in items)
    filtered = []
    for item in items:
        if has_high_signal and item.dedupe_key in _LOW_VALUE_DEDUPE_KEYS:
            continue
        filtered.append(item)
    return filtered


def summarize_insights(items: list[InsightItem], limit: int = 3) -> tuple[InsightItem | None, list[InsightItem]]:
    deduped = dedupe_insights(items)
    filtered = suppress_low_value_noise(deduped)
    top = filtered[0] if filtered else None
    summary = filtered[:limit]
    return top, summary
