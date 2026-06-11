from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SmartActionType = Literal[
    "keep_recommended",
    "archive_recommended",
    "replace_recommended",
    "cleanup_needed",
    "processing_needed",
    "review_needed",
]
SmartActionSeverity = Literal["danger", "warning", "success", "neutral"]
SmartActionGroup = Literal["album", "family", "collection"]
SmartActionConfidenceBand = Literal["low", "medium", "high", "very_high"]
SmartActionCapability = Literal["auto_fixable", "semi_auto_fixable", "manual_review_required", "informational_only"]
SmartActionResolutionConfidence = Literal["low", "medium", "high"]
SmartActionTier = Literal["automatic_fix_available", "fix_prepared", "review_needed", "informational"]
SmartActionExecutionMode = Literal["auto_apply_in_cleanup", "staged_confirmation", "manual_only", "none"]
SmartActionFixMethod = Literal["global_cleanup", "manual_review", "external_only"]
SmartActionCtaIntent = Literal["run_cleanup", "none"]
SmartActionAutoFixStatus = Literal["auto_fix_pending", "auto_fix_attempted", "auto_fix_blocked", "auto_fix_failed", "not_auto_fixable"]
SmartActionSkipReason = Literal[
    "provider_conflict",
    "confidence_too_low",
    "track_mapping_ambiguous",
    "release_structure_mismatch",
    "unsafe_metadata_overwrite",
    "provider_data_unavailable",
    "unsupported_fix_path",
]
SmartActionCategory = Literal[
    "metadata",
    "artwork",
    "sequencing",
    "duplicate",
    "release_quality",
    "suspicious_audio",
    "collection_cleanup",
    "processing",
]
SmartActionImpact = Literal["cosmetic", "moderate", "important"]


@dataclass(frozen=True)
class SmartAction:
    id: str
    type: SmartActionType
    group: SmartActionGroup
    severity: SmartActionSeverity
    category: SmartActionCategory
    impact: SmartActionImpact
    title: str
    message: str
    reasoning: tuple[str, ...]
    source_signals: tuple[str, ...]
    detected_by: tuple[str, ...]
    tier: SmartActionTier
    execution_mode: SmartActionExecutionMode
    primary_eligible: bool
    auto_fix_reason: str | None
    prepared_fix: dict[str, Any] | None
    can_musorg_fix: bool
    fix_method: SmartActionFixMethod
    cta_label: str | None
    cta_intent: SmartActionCtaIntent
    after_action: str | None
    blocking_reason: str | None
    auto_fix_status: SmartActionAutoFixStatus
    auto_fix_supported: bool
    auto_fix_attempted: bool
    auto_fix_explanation: str
    skip_reason: SmartActionSkipReason | None
    blocking_signals: tuple[str, ...]
    capability: SmartActionCapability
    why_matters: str
    suggested_fix: str
    evidence: tuple[str, ...]
    resolution_confidence: SmartActionResolutionConfidence
    confidence: int
    confidence_band: SmartActionConfidenceBand
    affected_paths: tuple[str, ...]
    actionable: bool
    destructive: bool
    recommended: bool
    reversible: bool
    priority: int
    snapshot_id: str
    generated_from_snapshot_id: str
    generated_at: str | None
    context_summary: str | None
    dismissible: bool
    snoozable: bool
    persistent: bool
    suppressed_by_action_id: str | None = None
    suppressed_reason: str | None = None
    superseded_by_action_id: str | None = None


@dataclass(frozen=True)
class SmartActionRegistry:
    snapshot_id: str
    summaries_by_path: dict[str, dict]
    payloads_by_path: dict[str, dict]
    collection_actions: tuple[dict, ...]
