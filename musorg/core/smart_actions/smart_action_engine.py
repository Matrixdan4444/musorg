from __future__ import annotations

from collections import defaultdict
from hashlib import sha1
import json
import logging

from musorg.core.insights.insight_types import InsightRegistry
from musorg.core.release_intelligence import ReleaseIntelligenceRegistry
from musorg.core.smart_actions.action_priorities import apply_suppression, normalize_action, should_keep_existing_top, sort_actions
from musorg.core.smart_actions.action_reasoning import collection_priority_copy
from musorg.core.smart_actions.action_rules import build_album_actions, build_family_action
from musorg.core.smart_actions.action_types import SmartAction, SmartActionRegistry

logger = logging.getLogger(__name__)

_MAX_ACTION_SUMMARY = 3
_MAX_COLLECTION_ACTIONS = 5
_MAX_COLLECTION_REASONING = 2
_REGISTRY_CACHE: tuple[str, SmartActionRegistry] | None = None
_TOP_ACTION_MEMORY: dict[str, str] = {}


def build_smart_action_registry(
    release_registry: ReleaseIntelligenceRegistry,
    insight_registry: InsightRegistry,
    metadata_intelligence_by_path: dict[str, dict] | None = None,
    runtime_state_by_path: dict[str, dict] | None = None,
    duplicate_handling: str = "keep_everything",
) -> SmartActionRegistry:
    metadata_intelligence_by_path = metadata_intelligence_by_path or {}
    runtime_state_by_path = runtime_state_by_path or {}
    snapshot_id = _snapshot_id(
        release_registry,
        insight_registry,
        metadata_intelligence_by_path,
        runtime_state_by_path,
        duplicate_handling,
    )
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE and _REGISTRY_CACHE[0] == snapshot_id:
        return _REGISTRY_CACHE[1]
    try:
        registry = _build_registry(
            release_registry,
            insight_registry,
            metadata_intelligence_by_path,
            runtime_state_by_path,
            snapshot_id,
            duplicate_handling,
        )
    except Exception:
        logger.exception("Failed to build smart action registry for snapshot %s", snapshot_id)
        registry = SmartActionRegistry(
            snapshot_id=snapshot_id,
            summaries_by_path={},
            payloads_by_path={},
            collection_actions=(),
        )
    _REGISTRY_CACHE = (snapshot_id, registry)
    return registry


def _build_registry(
    release_registry: ReleaseIntelligenceRegistry,
    insight_registry: InsightRegistry,
    metadata_intelligence_by_path: dict[str, dict],
    runtime_state_by_path: dict[str, dict],
    snapshot_id: str,
    duplicate_handling: str,
) -> SmartActionRegistry:
    family_paths_by_id: dict[str, list[str]] = defaultdict(list)
    for path, summary in release_registry.summaries_by_path.items():
        family_id = str(summary.get("releaseFamilyId") or path)
        family_paths_by_id[family_id].append(path)

    family_actions_by_id: dict[str, SmartAction] = {}
    for family_id, paths in family_paths_by_id.items():
        try:
            action = build_family_action(
                family_id=family_id,
                family_paths=tuple(sorted(paths)),
                summaries_by_path=release_registry.summaries_by_path,
                snapshot_id=snapshot_id,
                duplicate_handling=duplicate_handling,
            )
        except Exception:
            logger.exception("Failed to build family smart actions for family %s", family_id)
            action = None
        if action is not None:
            family_actions_by_id[family_id] = normalize_action(action)

    summaries_by_path: dict[str, dict] = {}
    payloads_by_path: dict[str, dict] = {}
    for path, summary in release_registry.summaries_by_path.items():
        family_id = str(summary.get("releaseFamilyId") or path)
        try:
            album_actions = build_album_actions(
                path=path,
                summary=summary,
                insights_payload=insight_registry.payloads_by_path.get(path),
                metadata_intelligence=metadata_intelligence_by_path.get(path),
                runtime_state=runtime_state_by_path.get(path),
                snapshot_id=snapshot_id,
                duplicate_handling=duplicate_handling,
            )
        except Exception:
            logger.exception("Failed to build album smart actions for %s", path)
            album_actions = []
        family_action = family_actions_by_id.get(family_id)
        combined_actions = list(album_actions)
        if family_action and path in family_action.affected_paths:
            combined_actions.append(family_action)
        visible_actions, suppressed_actions = apply_suppression(combined_actions)
        top_action = _select_top_action(path, visible_actions)
        visible_actions = _promote_top_action(visible_actions, top_action)
        visible_album_actions = [item for item in visible_actions if item.group == "album"]
        visible_family_actions = [item for item in visible_actions if item.group == "family"]
        summaries_by_path[path] = {
            "snapshotId": snapshot_id,
            "topAction": _serialize_action(top_action) if top_action else None,
            "actionSummary": [_serialize_action(item) for item in visible_actions[:_MAX_ACTION_SUMMARY]],
            "actionCount": len(visible_actions) + len(suppressed_actions),
        }
        payloads_by_path[path] = {
            "albumId": "",
            "snapshotId": snapshot_id,
            "topAction": _serialize_action(top_action) if top_action else None,
            "actionSummary": [_serialize_action(item) for item in visible_actions[:_MAX_ACTION_SUMMARY]],
            "actionCount": len(visible_actions) + len(suppressed_actions),
            "recommendationSummary": top_action.message if top_action else None,
            "albumActions": [_serialize_action(item) for item in visible_album_actions],
            "familyActions": [_serialize_action(item) for item in visible_family_actions],
            "suppressedActions": [_serialize_action(item) for item in suppressed_actions],
        }

    collection_actions = _build_collection_actions(tuple(family_actions_by_id.values()), payloads_by_path)
    return SmartActionRegistry(
        snapshot_id=snapshot_id,
        summaries_by_path=summaries_by_path,
        payloads_by_path=payloads_by_path,
        collection_actions=tuple(_serialize_action(item) for item in collection_actions),
    )


def _build_collection_actions(family_actions: tuple[SmartAction, ...], payloads_by_path: dict[str, dict]) -> list[SmartAction]:
    grouped: dict[tuple[str, str, str, str], list[SmartAction]] = defaultdict(list)
    for payload in payloads_by_path.values():
        for raw_item in payload.get("albumActions") or []:
            if (
                not isinstance(raw_item, dict)
                or raw_item.get("suppressedByActionId")
            ):
                continue
            try:
                action = _deserialize_action(raw_item)
            except Exception:
                logger.exception("Failed to deserialize album smart action for collection aggregation")
                continue
            grouped[_collection_group_key(action)].append(action)
    grouped_family = list(family_actions)
    actions: list[SmartAction] = []
    if grouped_family:
        grouped_family_actions: dict[tuple[str, str, str, str], list[SmartAction]] = defaultdict(list)
        for item in grouped_family:
            grouped_family_actions[_collection_group_key(item)].append(item)
        for items in grouped_family_actions.values():
            actions.append(_collection_action(items))
    for items in grouped.values():
        if items[0].type == "keep_recommended":
            continue
        actions.append(_collection_action(items))
    return sort_actions(actions)[:_MAX_COLLECTION_ACTIONS]


def _collection_action(items: list[SmartAction]) -> SmartAction:
    ordered = sort_actions(items)
    first = ordered[0]
    affected_paths = tuple(sorted({path for item in items for path in item.affected_paths}))
    count = len(affected_paths) or len(items)
    group_key = _collection_group_key(first)
    return normalize_action(SmartAction(
        id=_grouped_collection_id(first.snapshot_id, ":".join(group_key), affected_paths),
        type=first.type,
        group="collection",
        severity=first.severity,
        category=first.category,
        impact=first.impact,
        title=collection_priority_copy(first.title, count),
        message=first.message,
        reasoning=first.reasoning[:_MAX_COLLECTION_REASONING],
        source_signals=first.source_signals,
        detected_by=first.detected_by,
        tier=first.tier,
        execution_mode=first.execution_mode,
        primary_eligible=first.primary_eligible,
        auto_fix_reason=first.auto_fix_reason,
        prepared_fix=first.prepared_fix,
        can_musorg_fix=first.can_musorg_fix,
        fix_method=first.fix_method,
        cta_label=first.cta_label,
        cta_intent=first.cta_intent,
        after_action=first.after_action,
        blocking_reason=first.blocking_reason,
        auto_fix_status=first.auto_fix_status,
        auto_fix_supported=first.auto_fix_supported,
        auto_fix_attempted=first.auto_fix_attempted,
        auto_fix_explanation=first.auto_fix_explanation,
        skip_reason=first.skip_reason,
        blocking_signals=first.blocking_signals,
        capability=first.capability,
        why_matters=first.why_matters,
        suggested_fix=first.suggested_fix,
        evidence=first.evidence,
        resolution_confidence=first.resolution_confidence,
        confidence=first.confidence,
        confidence_band=first.confidence_band,
        affected_paths=affected_paths,
        actionable=True,
        destructive=first.destructive,
        recommended=True,
        reversible=True,
        priority=first.priority,
        snapshot_id=first.snapshot_id,
        generated_from_snapshot_id=first.generated_from_snapshot_id,
        generated_at=first.generated_at,
        context_summary=first.context_summary,
        dismissible=first.dismissible,
        snoozable=first.snoozable,
        persistent=True,
    ))


def _collection_group_key(action: SmartAction) -> tuple[str, str, str, str]:
    return (
        _collection_bucket(action),
        _normalized_health_status(action.auto_fix_status),
        action.cta_intent if action.cta_label else "none",
        "actionable" if action.cta_label and action.cta_intent != "none" else "none",
    )


def _collection_bucket(action: SmartAction) -> str:
    if action.category in {"metadata", "artwork", "processing", "suspicious_audio"}:
        return action.category
    if action.category in {"sequencing", "duplicate", "release_quality", "collection_cleanup"}:
        return action.category
    if action.type == "processing_needed":
        return "processing"
    if action.type == "review_needed":
        return "suspicious_audio"
    return "metadata"


def _normalized_health_status(auto_fix_status: str) -> str:
    if auto_fix_status == "auto_fix_pending":
        return "available"
    if auto_fix_status == "auto_fix_blocked":
        return "blocked"
    if auto_fix_status in {"auto_fix_failed", "auto_fix_attempted"}:
        return "failed"
    return "not_fixable"


def _serialize_action(action: SmartAction | None) -> dict | None:
    if action is None:
        return None
    return {
        "id": action.id,
        "type": action.type,
        "group": action.group,
        "severity": action.severity,
        "category": action.category,
        "impact": action.impact,
        "title": action.title,
        "message": action.message,
        "reasoning": list(action.reasoning),
        "sourceSignals": list(action.source_signals),
        "detectedBy": list(action.detected_by),
        "tier": action.tier,
        "executionMode": action.execution_mode,
        "primaryEligible": action.primary_eligible,
        "autoFixReason": action.auto_fix_reason,
        "preparedFix": action.prepared_fix,
        "canMusorgFix": action.can_musorg_fix,
        "fixMethod": action.fix_method,
        "ctaLabel": action.cta_label,
        "ctaIntent": action.cta_intent,
        "afterAction": action.after_action,
        "blockingReason": action.blocking_reason,
        "autoFixStatus": action.auto_fix_status,
        "autoFixSupported": action.auto_fix_supported,
        "autoFixAttempted": action.auto_fix_attempted,
        "autoFixExplanation": action.auto_fix_explanation,
        "skipReason": action.skip_reason,
        "blockingSignals": list(action.blocking_signals),
        "capability": action.capability,
        "whyMatters": action.why_matters,
        "suggestedFix": action.suggested_fix,
        "evidence": list(action.evidence),
        "resolutionConfidence": action.resolution_confidence,
        "confidence": action.confidence,
        "confidenceBand": action.confidence_band,
        "affectedAlbumPaths": list(action.affected_paths),
        "actionable": action.actionable,
        "destructive": action.destructive,
        "recommended": action.recommended,
        "reversible": action.reversible,
        "priority": action.priority,
        "snapshotId": action.snapshot_id,
        "generatedFromSnapshotId": action.generated_from_snapshot_id,
        "generatedAt": action.generated_at,
        "contextSummary": action.context_summary,
        "dismissible": action.dismissible,
        "snoozable": action.snoozable,
        "persistent": action.persistent,
        "suppressedByActionId": action.suppressed_by_action_id,
        "suppressedReason": action.suppressed_reason,
        "supersededByActionId": action.superseded_by_action_id,
    }


def _deserialize_action(item: dict) -> SmartAction:
    return normalize_action(SmartAction(
        id=str(item.get("id") or ""),
        type=str(item.get("type") or "review_needed"),  # type: ignore[arg-type]
        group=str(item.get("group") or "album"),  # type: ignore[arg-type]
        severity=str(item.get("severity") or "warning"),  # type: ignore[arg-type]
        category=str(item.get("category") or "metadata"),  # type: ignore[arg-type]
        impact=str(item.get("impact") or "moderate"),  # type: ignore[arg-type]
        title=str(item.get("title") or ""),
        message=str(item.get("message") or ""),
        reasoning=tuple(str(reason) for reason in (item.get("reasoning") or [])),
        source_signals=tuple(str(reason) for reason in (item.get("sourceSignals") or [])),
        detected_by=tuple(str(reason) for reason in (item.get("detectedBy") or [])),
        tier=str(item.get("tier") or "review_needed"),  # type: ignore[arg-type]
        execution_mode=str(item.get("executionMode") or "manual_only"),  # type: ignore[arg-type]
        primary_eligible=bool(item.get("primaryEligible", True)),
        auto_fix_reason=item.get("autoFixReason"),
        prepared_fix=item.get("preparedFix"),
        can_musorg_fix=bool(item.get("canMusorgFix")),
        fix_method=str(item.get("fixMethod") or "manual_review"),  # type: ignore[arg-type]
        cta_label=item.get("ctaLabel"),
        cta_intent=str(item.get("ctaIntent") or "none"),  # type: ignore[arg-type]
        after_action=item.get("afterAction"),
        blocking_reason=item.get("blockingReason"),
        auto_fix_status=str(item.get("autoFixStatus") or "not_auto_fixable"),  # type: ignore[arg-type]
        auto_fix_supported=bool(item.get("autoFixSupported")),
        auto_fix_attempted=bool(item.get("autoFixAttempted")),
        auto_fix_explanation=str(item.get("autoFixExplanation") or ""),
        skip_reason=item.get("skipReason"),
        blocking_signals=tuple(str(reason) for reason in (item.get("blockingSignals") or [])),
        capability=str(item.get("capability") or "informational_only"),  # type: ignore[arg-type]
        why_matters=str(item.get("whyMatters") or ""),
        suggested_fix=str(item.get("suggestedFix") or ""),
        evidence=tuple(str(reason) for reason in (item.get("evidence") or [])),
        resolution_confidence=str(item.get("resolutionConfidence") or "medium"),  # type: ignore[arg-type]
        confidence=int(item.get("confidence") or 0),
        confidence_band=str(item.get("confidenceBand") or "low"),  # type: ignore[arg-type]
        affected_paths=tuple(str(path) for path in (item.get("affectedAlbumPaths") or [])),
        actionable=bool(item.get("actionable")),
        destructive=bool(item.get("destructive")),
        recommended=bool(item.get("recommended")),
        reversible=bool(item.get("reversible")),
        priority=int(item.get("priority") or 0),
        snapshot_id=str(item.get("snapshotId") or ""),
        generated_from_snapshot_id=str(item.get("generatedFromSnapshotId") or ""),
        generated_at=item.get("generatedAt"),
        context_summary=item.get("contextSummary"),
        dismissible=bool(item.get("dismissible")),
        snoozable=bool(item.get("snoozable")),
        persistent=bool(item.get("persistent")),
        suppressed_by_action_id=item.get("suppressedByActionId"),
        suppressed_reason=item.get("suppressedReason"),
        superseded_by_action_id=item.get("supersededByActionId"),
    ))


def _snapshot_id(
    release_registry: ReleaseIntelligenceRegistry,
    insight_registry: InsightRegistry,
    metadata_intelligence_by_path: dict[str, dict],
    runtime_state_by_path: dict[str, dict],
    duplicate_handling: str,
) -> str:
    payload = {
        "release": release_registry.summaries_by_path,
        "insight": insight_registry.summaries_by_path,
        "metadata": metadata_intelligence_by_path,
        "runtime": runtime_state_by_path,
        "duplicateHandling": duplicate_handling,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha1(encoded.encode("utf-8")).hexdigest()[:12]


def _select_top_action(path: str, visible_actions: list[SmartAction]) -> SmartAction | None:
    primary_actions = [item for item in visible_actions if item.primary_eligible]
    if not primary_actions:
        _TOP_ACTION_MEMORY.pop(path, None)
        return None
    candidate = primary_actions[0]
    current_id = _TOP_ACTION_MEMORY.get(path)
    current = next((item for item in primary_actions if item.id == current_id), None)
    chosen = current if current and should_keep_existing_top(current, candidate) else candidate
    _TOP_ACTION_MEMORY[path] = chosen.id
    return chosen


def _promote_top_action(items: list[SmartAction], top_action: SmartAction | None) -> list[SmartAction]:
    if top_action is None:
        return items
    promoted = [item for item in items if item.id == top_action.id]
    if not promoted:
        return items
    return promoted + [item for item in items if item.id != top_action.id]


def _grouped_collection_id(snapshot_id: str, action_type: str, affected_paths: tuple[str, ...]) -> str:
    token = sha1("|".join((snapshot_id, action_type, *affected_paths)).encode("utf-8")).hexdigest()[:10]
    return f"collection:{action_type}:{token}"
