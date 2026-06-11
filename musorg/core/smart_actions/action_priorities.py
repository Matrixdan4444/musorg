from __future__ import annotations

from collections.abc import Iterable

from musorg.core.smart_actions.action_types import SmartAction


_CONFIDENCE_BAND_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "very_high": 3,
}

_TYPE_PRIORITY = {
    "review_needed": 100,
    "replace_recommended": 88,
    "archive_recommended": 84,
    "processing_needed": 72,
    "cleanup_needed": 58,
    "keep_recommended": 50,
}

_TIER_ORDER = {
    "automatic_fix_available": 3,
    "fix_prepared": 2,
    "review_needed": 1,
    "informational": 0,
}

_SEVERITY_ORDER = {
    "danger": 3,
    "warning": 2,
    "success": 1,
    "neutral": 0,
}

_ALLOWED_SEVERITIES = {
    "keep_recommended": {"success", "neutral"},
    "cleanup_needed": {"warning", "neutral"},
    "processing_needed": {"warning"},
    "review_needed": {"warning", "danger"},
    "archive_recommended": {"warning"},
    "replace_recommended": {"warning"},
}

_DEFAULT_SEVERITY = {
    "keep_recommended": "success",
    "cleanup_needed": "warning",
    "processing_needed": "warning",
    "review_needed": "warning",
    "archive_recommended": "warning",
    "replace_recommended": "warning",
}

MAX_REASONING_ITEMS = 3
MAX_REASONING_CHARS = 140
MAX_EVIDENCE_ITEMS = 4
MAX_EVIDENCE_CHARS = 140
MAX_BLOCKING_SIGNALS = 4
MAX_AFFECTED_PATHS = 8


def confidence_band(score: int) -> str:
    if score >= 90:
        return "very_high"
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def sort_actions(items: list[SmartAction]) -> list[SmartAction]:
    normalized = [normalize_action(item) for item in items]
    return sorted(
        normalized,
        key=lambda item: (
            -_TIER_ORDER[item.tier],
            not item.primary_eligible,
            -item.priority,
            -_SEVERITY_ORDER[item.severity],
            -_TYPE_PRIORITY[item.type],
            -_CONFIDENCE_BAND_ORDER[item.confidence_band],
            item.group != "album",
            item.title.lower(),
            item.id,
        ),
    )


def apply_suppression(items: list[SmartAction]) -> tuple[list[SmartAction], list[SmartAction]]:
    if not items:
        return [], []
    ordered = sort_actions(items)
    visible: list[SmartAction] = []
    suppressed: list[SmartAction] = []
    for item in ordered:
        blocking = next((candidate for candidate in visible if _should_suppress(candidate, item)), None)
        if blocking:
            suppressed.append(_copy_with_suppression(item, blocking.id, _suppression_reason(blocking, item)))
            continue
        visible.append(item)
    return visible, suppressed


def _should_suppress(current: SmartAction, candidate: SmartAction) -> bool:
    if current.group == "family" and candidate.group == "album" and candidate.type in {"archive_recommended", "replace_recommended"}:
        return True
    if current.type == "review_needed" and candidate.type in {"keep_recommended", "archive_recommended", "replace_recommended"}:
        return True
    if current.type in {"replace_recommended", "archive_recommended"} and candidate.type == "keep_recommended":
        return True
    if current.type == candidate.type:
        return True
    return False


def _suppression_reason(current: SmartAction, candidate: SmartAction) -> str:
    if current.group == "family" and candidate.group == "album":
        return "A grouped family recommendation already covers this release cluster."
    return f"{candidate.title} was hidden because {current.title} is more important right now."


def _copy_with_suppression(item: SmartAction, action_id: str, reason: str) -> SmartAction:
    return normalize_action(SmartAction(
        id=item.id,
        type=item.type,
        group=item.group,
        severity=item.severity,
        category=item.category,
        impact=item.impact,
        title=item.title,
        message=item.message,
        reasoning=item.reasoning,
        source_signals=item.source_signals,
        detected_by=item.detected_by,
        tier=item.tier,
        execution_mode=item.execution_mode,
        primary_eligible=item.primary_eligible,
        auto_fix_reason=item.auto_fix_reason,
        prepared_fix=item.prepared_fix,
        can_musorg_fix=item.can_musorg_fix,
        fix_method=item.fix_method,
        cta_label=item.cta_label,
        cta_intent=item.cta_intent,
        after_action=item.after_action,
        blocking_reason=item.blocking_reason,
        auto_fix_status=item.auto_fix_status,
        auto_fix_supported=item.auto_fix_supported,
        auto_fix_attempted=item.auto_fix_attempted,
        auto_fix_explanation=item.auto_fix_explanation,
        skip_reason=item.skip_reason,
        blocking_signals=item.blocking_signals,
        capability=item.capability,
        why_matters=item.why_matters,
        suggested_fix=item.suggested_fix,
        evidence=item.evidence,
        resolution_confidence=item.resolution_confidence,
        confidence=item.confidence,
        confidence_band=item.confidence_band,
        affected_paths=item.affected_paths,
        actionable=item.actionable,
        destructive=item.destructive,
        recommended=item.recommended,
        reversible=item.reversible,
        priority=item.priority,
        snapshot_id=item.snapshot_id,
        generated_from_snapshot_id=item.generated_from_snapshot_id,
        generated_at=item.generated_at,
        context_summary=item.context_summary,
        dismissible=item.dismissible,
        snoozable=item.snoozable,
        persistent=item.persistent,
        suppressed_by_action_id=action_id,
        suppressed_reason=reason,
        superseded_by_action_id=action_id,
    ))


def normalize_action(item: SmartAction) -> SmartAction:
    severity = item.severity
    if severity not in _ALLOWED_SEVERITIES[item.type]:
        severity = _DEFAULT_SEVERITY[item.type]
    reasoning = tuple(_normalize_reasoning(item.reasoning))
    evidence = tuple(_normalize_items(item.evidence, MAX_EVIDENCE_ITEMS, MAX_EVIDENCE_CHARS))
    blocking_signals = tuple(_normalize_items(item.blocking_signals, MAX_BLOCKING_SIGNALS, MAX_EVIDENCE_CHARS))
    normalized_paths = tuple(sorted(dict.fromkeys(item.affected_paths)))
    affected_paths = normalized_paths if item.group == "collection" else normalized_paths[:MAX_AFFECTED_PATHS]
    return SmartAction(
        id=item.id,
        type=item.type,
        group=item.group,
        severity=severity,  # type: ignore[arg-type]
        category=item.category,
        impact=item.impact,
        title=item.title.strip(),
        message=item.message.strip(),
        reasoning=reasoning,
        source_signals=tuple(sorted(dict.fromkeys(signal for signal in item.source_signals if signal))),
        detected_by=tuple(sorted(dict.fromkeys(label for label in item.detected_by if label))),
        tier=item.tier,
        execution_mode=item.execution_mode,
        primary_eligible=item.primary_eligible,
        auto_fix_reason=" ".join(str(item.auto_fix_reason or "").split()).strip() or None,
        prepared_fix=item.prepared_fix,
        can_musorg_fix=item.can_musorg_fix,
        fix_method=item.fix_method,
        cta_label=" ".join(str(item.cta_label or "").split()).strip() or None,
        cta_intent=item.cta_intent,
        after_action=" ".join(str(item.after_action or "").split()).strip() or None,
        blocking_reason=" ".join(str(item.blocking_reason or "").split()).strip() or None,
        auto_fix_status=item.auto_fix_status,
        auto_fix_supported=item.auto_fix_supported,
        auto_fix_attempted=item.auto_fix_attempted,
        auto_fix_explanation=" ".join(str(item.auto_fix_explanation or "").split()).strip(),
        skip_reason=item.skip_reason,
        blocking_signals=blocking_signals,
        capability=item.capability,
        why_matters=" ".join(str(item.why_matters or "").split()).strip(),
        suggested_fix=" ".join(str(item.suggested_fix or "").split()).strip(),
        evidence=evidence,
        resolution_confidence=item.resolution_confidence,
        confidence=item.confidence,
        confidence_band=item.confidence_band,
        affected_paths=affected_paths,
        actionable=item.actionable,
        destructive=item.destructive,
        recommended=item.recommended,
        reversible=item.reversible,
        priority=item.priority,
        snapshot_id=item.snapshot_id,
        generated_from_snapshot_id=item.generated_from_snapshot_id,
        generated_at=item.generated_at,
        context_summary=item.context_summary.strip() if isinstance(item.context_summary, str) and item.context_summary.strip() else None,
        dismissible=item.dismissible,
        snoozable=item.snoozable,
        persistent=item.persistent,
        suppressed_by_action_id=item.suppressed_by_action_id,
        suppressed_reason=item.suppressed_reason,
        superseded_by_action_id=item.superseded_by_action_id,
    )


def should_keep_existing_top(current: SmartAction, candidate: SmartAction) -> bool:
    current = normalize_action(current)
    candidate = normalize_action(candidate)
    if current.id == candidate.id:
        return True
    if current.primary_eligible and not candidate.primary_eligible:
        return True
    if _TIER_ORDER[candidate.tier] > _TIER_ORDER[current.tier]:
        return False
    if _TIER_ORDER[candidate.tier] < _TIER_ORDER[current.tier]:
        return True
    if candidate.generated_from_snapshot_id != current.generated_from_snapshot_id and current.id not in {candidate.suppressed_by_action_id, candidate.superseded_by_action_id}:
        if _SEVERITY_ORDER[candidate.severity] > _SEVERITY_ORDER[current.severity]:
            return False
        if candidate.type == "review_needed" and current.type != "review_needed":
            return False
    if _SEVERITY_ORDER[candidate.severity] > _SEVERITY_ORDER[current.severity]:
        return False
    if _CONFIDENCE_BAND_ORDER[candidate.confidence_band] > _CONFIDENCE_BAND_ORDER[current.confidence_band]:
        return False
    if candidate.type == "review_needed" and current.type != "review_needed":
        return False
    if candidate.type in {"replace_recommended", "archive_recommended"} and current.type == "keep_recommended":
        return False
    return True


def _normalize_reasoning(reasoning: Iterable[str]) -> list[str]:
    return _normalize_items(reasoning, MAX_REASONING_ITEMS, MAX_REASONING_CHARS)


def _normalize_items(items: Iterable[str], limit: int, max_chars: int) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in items:
        value = " ".join(str(raw_item or "").split()).strip()
        if not value:
            continue
        if len(value) > max_chars:
            value = value[: max_chars - 1].rstrip() + "…"
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
        if len(normalized) >= limit:
            break
    return normalized
