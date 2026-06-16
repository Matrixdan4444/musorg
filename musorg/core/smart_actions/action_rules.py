from __future__ import annotations

from hashlib import sha1

from musorg.core.smart_actions.action_priorities import confidence_band, normalize_action
from musorg.core.smart_actions.action_reasoning import (
    archive_duplicate_copy,
    compound_cleanup_copy,
    family_duplicate_copy,
    keep_primary_copy,
    metadata_review_copy,
    minor_artwork_cleanup_copy,
    minor_metadata_cleanup_copy,
    processing_needed_copy,
    replace_better_copy,
    release_quality_review_copy,
    release_structure_review_copy,
    review_audio_copy,
    review_duplicate_copy,
    sequencing_review_copy,
)
from musorg.core.smart_actions.action_types import SmartAction

_ARTWORK_SUSPICIOUS_IDS = {"low-quality-artwork"}
_SEQUENCING_SUSPICIOUS_IDS = {"broken-sequencing", "duplicate-tracks", "track-count-mismatch"}
_IMPORTANT_SUSPICIOUS_IDS = {"mixed-primary-artists", "unofficial-release"}
_MODERATE_SUSPICIOUS_IDS = {"provider-disagreement", "conflicting-release-year", "runtime-mismatch", "suspicious-release-title"}

DEFAULT_DUPLICATE_HANDLING = "keep_everything"


def normalize_duplicate_handling_settings(value: object | None) -> str:
    if value in {"keep_everything", "prefer_best_version", "move_duplicates_to_archive"}:
        return str(value)
    return DEFAULT_DUPLICATE_HANDLING


def duplicate_handling_settings_to_api(value: object | None) -> str:
    return normalize_duplicate_handling_settings(value)


def build_album_actions(
    *,
    path: str,
    summary: dict | None,
    insights_payload: dict | None,
    metadata_intelligence: dict | None,
    runtime_state: dict | None,
    snapshot_id: str,
    duplicate_handling: str = DEFAULT_DUPLICATE_HANDLING,
) -> list[SmartAction]:
    summary = summary or {}
    insights_payload = insights_payload or {}
    runtime_state = runtime_state or {}
    actions: list[SmartAction] = []
    strong_release = _is_strong_release(summary, runtime_state)
    duplicate_mode = normalize_duplicate_handling_settings(duplicate_handling)
    allow_archive_recommendations = duplicate_mode == "move_duplicates_to_archive"
    show_preferred_version = duplicate_mode != "keep_everything"

    relationship_status = str(summary.get("relationshipStatus") or "standalone")
    duplicate_confidence = int(summary.get("duplicateConfidence") or 0)
    fake_flac_status = str(summary.get("fakeFlacStatus") or "none")
    best_version = bool(summary.get("bestVersion"))
    processing_state = str(runtime_state.get("processingState") or "idle")
    release_actions = {
        str(item.get("id"))
        for item in (summary.get("releaseActions") or [])
        if isinstance(item, dict)
    }
    metadata_cleanup_actions = metadata_intelligence.get("cleanupActions") or [] if metadata_intelligence else []
    suspicious_metadata = metadata_intelligence.get("suspiciousMetadata") or [] if metadata_intelligence else []
    auto_fix_diagnostics = metadata_intelligence.get("autoFixDiagnostics") or {} if metadata_intelligence else {}
    confidence_level = str(((metadata_intelligence or {}).get("confidence") or {}).get("level") or "")

    if fake_flac_status != "none":
        title, message = review_audio_copy(fake_flac_status)
        actions.append(_action(
            action_id=f"{path}:review-audio",
            action_type="review_needed",
            group="album",
            severity="danger" if fake_flac_status == "suspicious" else "warning",
            category="suspicious_audio",
            impact="important",
            title=title,
            message=message,
            reasoning=(
                "Audio analysis flagged lossy-looking release characteristics.",
                "Detected by release intelligence and audio-quality heuristics.",
            ),
            source_signals=(
                f"release_intelligence.fake_flac_status.{fake_flac_status}",
                "insight.suspicious_audio",
            ),
            detected_by=("Release intelligence", "Audio quality analysis"),
            tier="informational",
            execution_mode="none",
            primary_eligible=False,
            auto_fix_reason=None,
            prepared_fix=None,
            can_musorg_fix=False,
            fix_method="external_only",
            cta_label=None,
            cta_intent="none",
            after_action=None,
            blocking_reason="Musorg cannot verify audio provenance safely through cleanup.",
            auto_fix_status="not_auto_fixable",
            auto_fix_supported=False,
            auto_fix_attempted=False,
            auto_fix_explanation="Automatic correction is not available for audio provenance concerns.",
            skip_reason="unsupported_fix_path",
            blocking_signals=(),
            capability="informational_only",
            why_matters="Release provenance may be unreliable even if the files are stored in a lossless container.",
            suggested_fix="Compare this release with another source before treating it as primary.",
            evidence=(
                f"Release intelligence marked this copy as {fake_flac_status.replace('_', ' ')}.",
            ),
            resolution_confidence="medium" if fake_flac_status == "possible" else "high",
            confidence=max(70, duplicate_confidence),
            snapshot_id=snapshot_id,
            affected_paths=(path,),
            priority=100,
            destructive=False,
            recommended=True,
            context_summary=None,
            dismissible=False,
            snoozable=False,
            persistent=True,
        ))

    if relationship_status == "exact_duplicate":
        title, message = archive_duplicate_copy()
        severity = "warning"
        confidence = max(duplicate_confidence, 78)
        action_type = "archive_recommended" if allow_archive_recommendations and confidence >= 85 else "review_needed"
        if action_type == "review_needed":
            title, message = review_duplicate_copy()
        actions.append(_action(
            action_id=f"{path}:duplicate",
            action_type=action_type,
            group="album",
            severity=severity,
            category="duplicate",
            impact="important" if action_type == "archive_recommended" else "moderate",
            title=title,
            message=message,
            reasoning=tuple(summary.get("reasons") or []),
            source_signals=("release_intelligence.relationship_status.exact_duplicate",),
            detected_by=("Release intelligence",),
            tier="fix_prepared" if action_type == "archive_recommended" else "review_needed",
            execution_mode="staged_confirmation" if action_type == "archive_recommended" else "manual_only",
            primary_eligible=True,
            auto_fix_reason="Musorg identified a stronger duplicate with high-confidence family matching." if action_type == "archive_recommended" else None,
            prepared_fix=_prepared_fix(
                kind="archive_duplicate",
                summary="Archive the weaker duplicate after confirming the stronger keep candidate.",
                source_paths=(path,),
                planned_changes=("Keep the stronger duplicate", "Archive the weaker duplicate"),
            ) if action_type == "archive_recommended" else None,
            can_musorg_fix=False,
            fix_method="manual_review",
            cta_label=None,
            cta_intent="none",
            after_action="Musorg will keep the stronger duplicate plan visible while you decide which copy to keep." if action_type == "archive_recommended" else None,
            blocking_reason=None if action_type == "archive_recommended" else "Musorg cannot safely choose which duplicate to archive from the current evidence.",
            auto_fix_status="not_auto_fixable",
            auto_fix_supported=False,
            auto_fix_attempted=False,
            auto_fix_explanation="Duplicate cleanup needs user review before any archive decision is safe.",
            skip_reason="unsupported_fix_path",
            blocking_signals=(),
            capability="semi_auto_fixable" if action_type == "archive_recommended" else "manual_review_required",
            why_matters="Keeping redundant duplicate copies can make the library harder to manage.",
            suggested_fix=(
                "Compare this copy with the stronger duplicate before archiving it."
                if action_type == "archive_recommended"
                else "Compare both releases before deciding which duplicate to keep."
            ),
            evidence=tuple(summary.get("reasons") or ()),
            resolution_confidence="high" if action_type == "archive_recommended" else "medium",
            confidence=confidence,
            snapshot_id=snapshot_id,
            affected_paths=(path,),
            priority=84 if action_type == "archive_recommended" else 90,
            destructive=action_type == "archive_recommended",
            recommended=True,
            context_summary=None,
            dismissible=False,
            snoozable=False,
            persistent=True,
        ))
    elif relationship_status == "near_duplicate":
        title, message = review_duplicate_copy()
        actions.append(_action(
            action_id=f"{path}:near-duplicate",
            action_type="review_needed",
            group="album",
            severity="warning",
            category="duplicate",
            impact="moderate",
            title=title,
            message=message,
            reasoning=tuple(summary.get("reasons") or []),
            source_signals=("release_intelligence.relationship_status.near_duplicate",),
            detected_by=("Release intelligence",),
            tier="review_needed",
            execution_mode="manual_only",
            primary_eligible=True,
            auto_fix_reason=None,
            prepared_fix=None,
            can_musorg_fix=False,
            fix_method="manual_review",
            cta_label=None,
            cta_intent="none",
            after_action=None,
            blocking_reason="Musorg cannot safely pick a winner from these near-duplicate releases.",
            auto_fix_status="not_auto_fixable",
            auto_fix_supported=False,
            auto_fix_attempted=False,
            auto_fix_explanation="Automatic correction is not currently supported for near-duplicate release conflicts.",
            skip_reason="unsupported_fix_path",
            blocking_signals=(),
            capability="manual_review_required",
            why_matters="Near-duplicate releases can leave multiple slightly different copies in the library.",
            suggested_fix="Compare the related releases before choosing which version to keep.",
            evidence=tuple(summary.get("reasons") or ()),
            resolution_confidence="medium",
            confidence=max(65, duplicate_confidence),
            snapshot_id=snapshot_id,
            affected_paths=(path,),
            priority=92,
            destructive=False,
            recommended=True,
            context_summary=None,
            dismissible=False,
            snoozable=False,
            persistent=True,
        ))

    if relationship_status == "better_version_available" or "replace_lossy_release" in release_actions:
        title, message = replace_better_copy()
        confidence = max(72, duplicate_confidence)
        action_type = "replace_recommended" if allow_archive_recommendations and confidence >= 85 else "review_needed"
        if action_type == "review_needed":
            title, message = review_duplicate_copy()
        actions.append(_action(
            action_id=f"{path}:replace",
            action_type=action_type,
            group="album",
            severity="warning",
            category="duplicate",
            impact="important" if action_type == "replace_recommended" else "moderate",
            title=title,
            message=message,
            reasoning=tuple(summary.get("reasons") or []),
            source_signals=tuple(
                signal
                for signal in (
                    "release_intelligence.relationship_status.better_version_available" if relationship_status == "better_version_available" else "",
                    "release_intelligence.release_action.replace_lossy_release" if "replace_lossy_release" in release_actions else "",
                    "insight.recommendation.replace_weaker" if _has_recommendation(insights_payload, "replace_weaker") else "",
                )
                if signal
            ),
            detected_by=("Release intelligence",),
            tier="fix_prepared" if action_type == "replace_recommended" else "review_needed",
            execution_mode="staged_confirmation" if action_type == "replace_recommended" else "manual_only",
            primary_eligible=True,
            auto_fix_reason="Musorg identified a stronger related version with high-confidence family evidence." if action_type == "replace_recommended" else None,
            prepared_fix=_prepared_fix(
                kind="replace_release",
                summary="Replace this weaker release with the stronger related version after confirmation.",
                source_paths=(path,),
                planned_changes=("Keep the stronger related version", "Archive or replace the weaker version"),
            ) if action_type == "replace_recommended" else None,
            can_musorg_fix=False,
            fix_method="manual_review",
            cta_label=None,
            cta_intent="none",
            after_action="Musorg has prepared a safer keep/replace recommendation for this release family." if action_type == "replace_recommended" else None,
            blocking_reason=None if action_type == "replace_recommended" else "Musorg cannot safely replace this version until the related releases are reviewed.",
            auto_fix_status="not_auto_fixable",
            auto_fix_supported=False,
            auto_fix_attempted=False,
            auto_fix_explanation="Release replacement still needs a user decision before Musorg can change which version to keep.",
            skip_reason="unsupported_fix_path",
            blocking_signals=(),
            capability="semi_auto_fixable" if action_type == "replace_recommended" else "manual_review_required",
            why_matters="A weaker version can stay in the library even though a stronger related release already exists.",
            suggested_fix=(
                "Use the stronger related version as primary and review this copy before replacing it."
                if action_type == "replace_recommended"
                else "Compare the stronger related version before replacing this copy."
            ),
            evidence=tuple(summary.get("reasons") or ()),
            resolution_confidence="high" if action_type == "replace_recommended" else "medium",
            confidence=confidence,
            snapshot_id=snapshot_id,
            affected_paths=(path,),
            priority=88 if action_type == "replace_recommended" else 90,
            destructive=action_type == "replace_recommended",
            recommended=True,
            context_summary=None,
            dismissible=False,
            snoozable=False,
            persistent=True,
        ))

    if show_preferred_version and (best_version or relationship_status == "best_version"):
        title, message = keep_primary_copy()
        actions.append(_action(
            action_id=f"{path}:keep",
            action_type="keep_recommended",
            group="album",
            severity="success",
            category="release_quality",
            impact="moderate",
            title=title,
            message=message,
            reasoning=tuple(summary.get("reasons") or []),
            source_signals=tuple(
                signal
                for signal in (
                    "release_intelligence.relationship_status.best_version",
                    "insight.recommendation.keep_primary" if _has_recommendation(insights_payload, "keep_primary") else "",
                )
                if signal
            ),
            detected_by=("Release intelligence", "Insights"),
            tier="informational",
            execution_mode="none",
            primary_eligible=False,
            auto_fix_reason=None,
            prepared_fix=None,
            can_musorg_fix=False,
            fix_method="external_only",
            cta_label=None,
            cta_intent="none",
            after_action=None,
            blocking_reason="This is recommendation context, not a corrective cleanup action.",
            auto_fix_status="not_auto_fixable",
            auto_fix_supported=False,
            auto_fix_attempted=False,
            auto_fix_explanation="This recommendation does not represent a corrective cleanup action.",
            skip_reason="unsupported_fix_path",
            blocking_signals=(),
            capability="informational_only",
            why_matters="Keeping one clear primary version helps avoid confusion across related releases.",
            suggested_fix="Use this as the primary version when choosing between related releases.",
            evidence=tuple(summary.get("reasons") or ()),
            resolution_confidence="high",
            confidence=max(75, duplicate_confidence),
            snapshot_id=snapshot_id,
            affected_paths=(path,),
            priority=50,
            destructive=False,
            recommended=True,
            context_summary=None,
            dismissible=False,
            snoozable=False,
            persistent=True,
        ))

    if processing_state in {"failed", "missing_output"}:
        title, message = processing_needed_copy(processing_state)
        actions.append(_action(
            action_id=f"{path}:processing",
            action_type="processing_needed",
            group="album",
            severity="warning",
            category="processing",
            impact="important",
            title=title,
            message=message,
            reasoning=(
                f"Current processing state is {processing_state.replace('_', ' ')}.",
                "This affects whether the cleaned release is available in the output library.",
                "Detected by runtime processing state.",
            ),
            source_signals=(f"runtime.processing_state.{processing_state}",),
            detected_by=("Processing runtime",),
            tier="automatic_fix_available",
            execution_mode="auto_apply_in_cleanup",
            primary_eligible=True,
            auto_fix_reason="Cleanup can rebuild the missing or failed output deterministically.",
            prepared_fix=None,
            can_musorg_fix=True,
            fix_method="global_cleanup",
            cta_label="Run Cleanup",
            cta_intent="run_cleanup",
            after_action="Musorg will rerun cleanup and rebuild the processed output for this album during the current library pass.",
            blocking_reason=None,
            auto_fix_status="auto_fix_pending",
            auto_fix_supported=True,
            auto_fix_attempted=False,
            auto_fix_explanation="Cleanup can rebuild the missing or failed output on the next run.",
            skip_reason=None,
            blocking_signals=(),
            capability="auto_fixable",
            why_matters="The cleaned version may be missing from the output library until processing succeeds.",
            suggested_fix="Re-run cleanup for this album.",
            evidence=(f"Current processing state: {processing_state.replace('_', ' ')}.",),
            resolution_confidence="high",
            confidence=85,
            snapshot_id=snapshot_id,
            affected_paths=(path,),
            priority=72,
            destructive=False,
            recommended=True,
            context_summary=None,
            dismissible=False,
            snoozable=False,
            persistent=True,
        ))

    cleanup_action = _build_cleanup_action(
        path=path,
        summary=summary,
        metadata_cleanup_actions=metadata_cleanup_actions,
        suspicious_metadata=suspicious_metadata,
        auto_fix_diagnostics=auto_fix_diagnostics,
        release_actions=release_actions,
        confidence_level=confidence_level,
        strong_release=strong_release,
        processing_state=processing_state,
        snapshot_id=snapshot_id,
    )
    if cleanup_action:
        actions.append(cleanup_action)

    return actions


def build_family_action(
    *,
    family_id: str,
    family_paths: tuple[str, ...],
    summaries_by_path: dict[str, dict],
    snapshot_id: str,
    duplicate_handling: str = DEFAULT_DUPLICATE_HANDLING,
) -> SmartAction | None:
    duplicate_paths = [
        path
        for path in family_paths
        if str((summaries_by_path.get(path) or {}).get("relationshipStatus") or "standalone")
        in {"exact_duplicate", "near_duplicate", "better_version_available"}
    ]
    if len(duplicate_paths) < 2:
        return None
    duplicate_mode = normalize_duplicate_handling_settings(duplicate_handling)
    confidence = max(int((summaries_by_path.get(path) or {}).get("duplicateConfidence") or 0) for path in duplicate_paths)
    title, message = family_duplicate_copy(len(duplicate_paths))
    action_type = "review_needed" if confidence < 85 or duplicate_mode != "move_duplicates_to_archive" else "archive_recommended"
    action_id = _grouped_action_id(snapshot_id, family_id, action_type, duplicate_paths)
    return _action(
        action_id=action_id,
        action_type=action_type,
        group="family",
        severity="warning",
        category="collection_cleanup",
        impact="important" if confidence >= 85 else "moderate",
        title=title,
        message=message,
        reasoning=(
            "Release comparison grouped several lower-quality copies into one family.",
            "This matters because only one or two versions may need to stay in the library.",
            "Detected by release-family duplicate analysis.",
        ),
        source_signals=("release_intelligence.family.duplicate_cluster",),
        detected_by=("Release intelligence",),
        tier="fix_prepared" if confidence >= 85 else "review_needed",
        execution_mode="staged_confirmation" if confidence >= 85 else "manual_only",
        primary_eligible=True,
        auto_fix_reason="Musorg grouped this family into a high-confidence duplicate cluster." if confidence >= 85 else None,
        prepared_fix=_prepared_fix(
            kind="family_duplicate_cleanup",
            summary="Review the proposed keep/archive plan for this duplicate family.",
            source_paths=tuple(sorted(duplicate_paths)),
            planned_changes=("Keep the strongest versions", "Archive weaker duplicates"),
        ) if confidence >= 85 else None,
        can_musorg_fix=False,
        fix_method="manual_review",
        cta_label=None,
        cta_intent="none",
        after_action="Musorg will keep this grouped duplicate plan available while you review the family." if confidence >= 85 else None,
        blocking_reason=None if confidence >= 85 else "Musorg cannot safely collapse this family without user review.",
        auto_fix_status="not_auto_fixable",
        auto_fix_supported=False,
        auto_fix_attempted=False,
        auto_fix_explanation="Family duplicate cleanup still needs a user decision before files are changed.",
        skip_reason="unsupported_fix_path",
        blocking_signals=(),
        capability="semi_auto_fixable" if confidence >= 85 else "manual_review_required",
        why_matters="Grouped duplicate families can leave several redundant copies in the collection.",
        suggested_fix="Review the proposed duplicate cleanup for this family." if confidence >= 85 else "Compare the releases in this family and keep only the strongest versions.",
        evidence=(f"{len(duplicate_paths)} related releases were grouped into one duplicate cluster.",),
        resolution_confidence="high" if confidence >= 85 else "medium",
        confidence=max(70, confidence),
        snapshot_id=snapshot_id,
        affected_paths=tuple(sorted(duplicate_paths)),
        priority=94,
        destructive=confidence >= 85,
        recommended=True,
        context_summary=None,
        dismissible=False,
        snoozable=False,
        persistent=True,
    )


def _has_recommendation(insights_payload: dict | None, recommendation_type: str) -> bool:
    if not insights_payload:
        return False
    for item in (insights_payload.get("albumInsights") or []):
        if isinstance(item, dict) and str(item.get("recommendationType") or "") == recommendation_type:
            return True
    return False


def _action(
    *,
    action_id: str,
    action_type: str,
    group: str,
    severity: str,
    category: str,
    impact: str,
    title: str,
    message: str,
    reasoning: tuple[str, ...],
    source_signals: tuple[str, ...],
    detected_by: tuple[str, ...],
    tier: str,
    execution_mode: str,
    primary_eligible: bool,
    auto_fix_reason: str | None,
    prepared_fix: dict | None,
    can_musorg_fix: bool,
    fix_method: str,
    cta_label: str | None,
    cta_intent: str,
    after_action: str | None,
    blocking_reason: str | None,
    auto_fix_status: str,
    auto_fix_supported: bool,
    auto_fix_attempted: bool,
    auto_fix_explanation: str,
    skip_reason: str | None,
    blocking_signals: tuple[str, ...],
    capability: str,
    why_matters: str,
    suggested_fix: str,
    evidence: tuple[str, ...],
    resolution_confidence: str,
    confidence: int,
    snapshot_id: str,
    affected_paths: tuple[str, ...],
    priority: int,
    destructive: bool,
    recommended: bool,
    context_summary: str | None,
    dismissible: bool,
    snoozable: bool,
    persistent: bool,
) -> SmartAction:
    return normalize_action(SmartAction(
        id=action_id,
        type=action_type,  # type: ignore[arg-type]
        group=group,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        impact=impact,  # type: ignore[arg-type]
        title=title,
        message=message,
        reasoning=reasoning,
        source_signals=source_signals,
        detected_by=detected_by,
        tier=tier,  # type: ignore[arg-type]
        execution_mode=execution_mode,  # type: ignore[arg-type]
        primary_eligible=primary_eligible,
        auto_fix_reason=auto_fix_reason,
        prepared_fix=prepared_fix,
        can_musorg_fix=can_musorg_fix,
        fix_method=fix_method,  # type: ignore[arg-type]
        cta_label=cta_label,
        cta_intent=cta_intent,  # type: ignore[arg-type]
        after_action=after_action,
        blocking_reason=blocking_reason,
        auto_fix_status=auto_fix_status,  # type: ignore[arg-type]
        auto_fix_supported=auto_fix_supported,
        auto_fix_attempted=auto_fix_attempted,
        auto_fix_explanation=auto_fix_explanation,
        skip_reason=skip_reason,  # type: ignore[arg-type]
        blocking_signals=blocking_signals,
        capability=capability,  # type: ignore[arg-type]
        why_matters=why_matters,
        suggested_fix=suggested_fix,
        evidence=evidence,
        resolution_confidence=resolution_confidence,  # type: ignore[arg-type]
        confidence=confidence,
        confidence_band=confidence_band(confidence),  # type: ignore[arg-type]
        affected_paths=affected_paths,
        actionable=True,
        destructive=destructive,
        recommended=recommended,
        reversible=True,
        priority=priority,
        snapshot_id=snapshot_id,
        generated_from_snapshot_id=snapshot_id,
        generated_at=None,
        context_summary=context_summary,
        dismissible=dismissible,
        snoozable=snoozable,
        persistent=persistent,
    ))


def _grouped_action_id(snapshot_id: str, family_id: str, action_type: str, members: list[str] | tuple[str, ...]) -> str:
    normalized_members = tuple(sorted(members))
    token = sha1("|".join((snapshot_id, family_id, action_type, *normalized_members)).encode("utf-8")).hexdigest()[:10]
    return f"{family_id}:{action_type}:{token}"


def _build_cleanup_action(
    *,
    path: str,
    summary: dict,
    metadata_cleanup_actions: list[dict],
    suspicious_metadata: list[dict],
    auto_fix_diagnostics: dict,
    release_actions: set[str],
    confidence_level: str,
    strong_release: bool,
    processing_state: str,
    snapshot_id: str,
) -> SmartAction | None:
    suspicious_items = {
        str(item.get("id") or ""): item
        for item in suspicious_metadata
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    suspicious_ids = set(suspicious_items)
    cleanup_kinds = {str(item.get("kind") or "") for item in metadata_cleanup_actions if isinstance(item, dict)}
    has_artwork_hint = "replace_artwork" in release_actions or bool(suspicious_ids & _ARTWORK_SUSPICIOUS_IDS)
    has_metadata_hint = "merge_metadata" in release_actions or bool(suspicious_ids & _MODERATE_SUSPICIOUS_IDS) or confidence_level in {"low", "suspicious"}
    has_sequencing_hint = bool(suspicious_ids & _SEQUENCING_SUSPICIOUS_IDS)
    has_important_hint = bool(suspicious_ids & _IMPORTANT_SUSPICIOUS_IDS)

    if not (suspicious_ids or {"replace_artwork", "merge_metadata"} & release_actions or confidence_level in {"low", "suspicious"}):
        return None

    categories = {
        category
        for category, enabled in (
            ("artwork", has_artwork_hint),
            ("metadata", has_metadata_hint),
            ("sequencing", has_sequencing_hint),
            ("release_quality", has_important_hint and not has_sequencing_hint),
        )
        if enabled
    }
    category = _primary_cleanup_category(categories)
    impact = _cleanup_impact(suspicious_ids, categories, confidence_level)
    fix_profile = _cleanup_fix_profile(
        category=category,
        impact=impact,
        suspicious_ids=suspicious_ids,
        suspicious_items=suspicious_items,
        release_actions=release_actions,
        confidence_level=confidence_level,
    )
    truth = _cleanup_truth_profile(
        category=category,
        impact=impact,
        suspicious_ids=suspicious_ids,
        diagnostics=auto_fix_diagnostics,
        processing_state=processing_state,
    )
    action_fields = _action_fields_from_truth(
        category=category,
        impact=impact,
        base=fix_profile,
        truth=truth,
    )
    severity = "neutral" if impact == "cosmetic" and action_fields["tier"] != "review_needed" else "danger" if has_important_hint and action_fields["tier"] == "review_needed" else "warning"
    action_type = action_fields["action_type"]
    title, message = _cleanup_copy(category, categories, impact)
    context_summary = (
        "Overall release quality is strong, but minor metadata cleanup is still available."
        if strong_release and impact == "cosmetic" and category == "metadata"
        else "Overall release quality is strong, but minor artwork cleanup is still available."
        if strong_release and impact == "cosmetic" and category == "artwork"
        else None
    )
    reasoning = _cleanup_reasoning(
        category=category,
        impact=impact,
        suspicious_ids=suspicious_ids,
        suspicious_items=suspicious_items,
        cleanup_kinds=cleanup_kinds,
        release_actions=release_actions,
        strong_release=strong_release,
        confidence_level=confidence_level,
    )
    evidence = _cleanup_evidence(
        category=category,
        suspicious_ids=suspicious_ids,
        suspicious_items=suspicious_items,
        release_actions=release_actions,
        confidence_level=confidence_level,
    )
    source_signals = _cleanup_source_signals(
        suspicious_ids=suspicious_ids,
        release_actions=release_actions,
        confidence_level=confidence_level,
    )
    detected_by = _cleanup_detected_by(categories, suspicious_ids, release_actions, confidence_level)
    why_matters = _cleanup_why_matters(category, impact, suspicious_ids)
    suggested_fix = _cleanup_suggested_fix(
        category,
        impact,
        suspicious_ids,
        suspicious_items,
        release_actions,
        confidence_level,
        truth["auto_fix_status"],
    )
    resolution_confidence = _cleanup_resolution_confidence(category, suspicious_ids, suspicious_items, release_actions, confidence_level)
    return _action(
        action_id=f"{path}:cleanup:{category}",
        action_type=action_type,
        group="album",
        severity=severity,
        category=category,
        impact=impact,
        title=title,
        message=message,
        reasoning=reasoning,
        source_signals=source_signals,
        detected_by=detected_by,
        tier=action_fields["tier"],
        execution_mode=action_fields["execution_mode"],
        primary_eligible=action_fields["primary_eligible"],
        auto_fix_reason=action_fields["auto_fix_reason"],
        prepared_fix=None,
        can_musorg_fix=action_fields["can_musorg_fix"],
        fix_method=action_fields["fix_method"],
        cta_label=action_fields["cta_label"],
        cta_intent=action_fields["cta_intent"],
        after_action=action_fields["after_action"],
        blocking_reason=action_fields["blocking_reason"],
        auto_fix_status=truth["auto_fix_status"],
        auto_fix_supported=truth["auto_fix_supported"],
        auto_fix_attempted=truth["auto_fix_attempted"],
        auto_fix_explanation=truth["auto_fix_explanation"],
        skip_reason=truth["skip_reason"],
        blocking_signals=tuple(truth["blocking_signals"]),
        capability=action_fields["capability"],
        why_matters=why_matters,
        suggested_fix=suggested_fix,
        evidence=evidence,
        resolution_confidence=resolution_confidence,
        confidence=76 if impact == "important" else 64 if impact == "moderate" else 54,
        snapshot_id=snapshot_id,
        affected_paths=(path,),
        priority=82 if impact == "important" else 66 if impact == "moderate" else 38,
        destructive=False,
        recommended=True,
        context_summary=context_summary,
        dismissible=impact == "cosmetic",
        snoozable=impact == "cosmetic",
        persistent=impact != "cosmetic",
    )


def _is_strong_release(summary: dict, runtime_state: dict) -> bool:
    quality_score = int(summary.get("qualityScore") or 0)
    relationship_status = str(summary.get("relationshipStatus") or "standalone")
    processing_state = str(runtime_state.get("processingState") or "idle")
    return (
        processing_state in {"completed", "idle"}
        and str(summary.get("fakeFlacStatus") or "none") == "none"
        and relationship_status not in {"exact_duplicate", "near_duplicate", "better_version_available", "suspicious_release"}
        and (bool(summary.get("bestVersion")) or quality_score >= 75)
    )


def _cleanup_impact(suspicious_ids: set[str], categories: set[str], confidence_level: str) -> str:
    if suspicious_ids & _IMPORTANT_SUSPICIOUS_IDS:
        return "important"
    if suspicious_ids & _SEQUENCING_SUSPICIOUS_IDS:
        return "important" if {"broken-sequencing", "duplicate-tracks"} & suspicious_ids else "moderate"
    if suspicious_ids & _MODERATE_SUSPICIOUS_IDS or confidence_level in {"low", "suspicious"}:
        return "moderate"
    if categories == {"artwork"} or categories == {"metadata"}:
        return "cosmetic"
    return "moderate"


def _primary_cleanup_category(categories: set[str]) -> str:
    for category in ("sequencing", "release_quality", "metadata", "artwork"):
        if category in categories:
            return category
    return "metadata"


def _cleanup_copy(category: str, categories: set[str], impact: str) -> tuple[str, str]:
    if len(categories) > 1:
        return compound_cleanup_copy(categories, important=impact == "important")
    if category == "artwork":
        return minor_artwork_cleanup_copy()
    if category == "metadata":
        return metadata_review_copy() if impact != "cosmetic" else minor_metadata_cleanup_copy()
    if category == "sequencing":
        return sequencing_review_copy() if impact == "important" else release_structure_review_copy()
    return release_quality_review_copy()


def _cleanup_reasoning(
    *,
    category: str,
    impact: str,
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    cleanup_kinds: set[str],
    release_actions: set[str],
    strong_release: bool,
    confidence_level: str,
) -> tuple[str, ...]:
    trigger = _trigger_reason(category, suspicious_ids, suspicious_items, cleanup_kinds, release_actions, confidence_level)
    why = _cleanup_why_matters(category, impact, suspicious_ids)
    subsystem = _subsystem_reason(category, suspicious_ids, release_actions, confidence_level)
    notes: list[str] = [trigger, why, subsystem]
    if strong_release and impact == "cosmetic":
        notes.append("This is cosmetic and does not affect core release quality.")
    return tuple(notes)


def _cleanup_source_signals(*, suspicious_ids: set[str], release_actions: set[str], confidence_level: str) -> tuple[str, ...]:
    signals = [f"metadata_intelligence.suspicious_metadata.{issue_id}" for issue_id in sorted(suspicious_ids)]
    if "replace_artwork" in release_actions:
        signals.append("release_intelligence.release_action.replace_artwork")
    if "merge_metadata" in release_actions:
        signals.append("release_intelligence.release_action.merge_metadata")
    if confidence_level in {"low", "suspicious"}:
        signals.append(f"metadata_intelligence.confidence.{confidence_level}")
    return tuple(signals)


def _cleanup_detected_by(categories: set[str], suspicious_ids: set[str], release_actions: set[str], confidence_level: str) -> tuple[str, ...]:
    labels: list[str] = []
    if suspicious_ids or confidence_level in {"low", "suspicious"}:
        labels.append("Metadata analysis")
    if "replace_artwork" in release_actions or "merge_metadata" in release_actions:
        labels.append("Release comparison")
    if "sequencing" in categories:
        labels.append("Track structure checks")
    return tuple(labels or ["Metadata analysis"])


def _trigger_reason(
    category: str,
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    cleanup_kinds: set[str],
    release_actions: set[str],
    confidence_level: str,
) -> str:
    if "broken-sequencing" in suspicious_ids:
        evidence = _sequencing_evidence(suspicious_items.get("broken-sequencing"))
        return evidence[0] if evidence else "Track numbering appears non-sequential and was flagged by metadata analysis."
    if "duplicate-tracks" in suspicious_ids:
        evidence = _duplicate_track_evidence(suspicious_items.get("duplicate-tracks"))
        return evidence[0] if evidence else "Several tracks look duplicated within the album group."
    if "track-count-mismatch" in suspicious_ids:
        evidence = _track_count_evidence(suspicious_items.get("track-count-mismatch"))
        return evidence[0] if evidence else "Track structure differs from provider evidence for this release."
    if "provider-disagreement" in suspicious_ids:
        return "Metadata analysis found a provider disagreement for this release."
    if "mixed-primary-artists" in suspicious_ids:
        return "Several tracks have inconsistent primary artist metadata."
    if "unofficial-release" in suspicious_ids or "suspicious-release-title" in suspicious_ids:
        return "Release metadata looks noisy or unofficial and was flagged for review."
    if "replace_artwork" in release_actions or "low-quality-artwork" in suspicious_ids:
        return "Artwork quality was flagged by metadata analysis."
    if "merge_metadata" in release_actions:
        return "Release comparison found a family member with cleaner metadata coverage."
    if confidence_level in {"low", "suspicious"}:
        return "Metadata confidence is incomplete for this release."
    if category == "metadata" and {"artist", "albumartist"} & cleanup_kinds:
        return "Artist tags were normalized, but metadata confidence is not fully settled."
    return "Metadata analysis found follow-up cleanup signals for this release."


def _impact_reason(category: str, impact: str) -> str:
    return _cleanup_why_matters(category, impact, set())


def _subsystem_reason(category: str, suspicious_ids: set[str], release_actions: set[str], confidence_level: str) -> str:
    if category == "artwork" and ("replace_artwork" in release_actions or "low-quality-artwork" in suspicious_ids):
        return "Detected by metadata analysis and related-release comparison."
    if category == "sequencing":
        return "Detected by metadata analysis and track structure checks."
    if category == "release_quality":
        return "Detected by metadata analysis and release-quality heuristics."
    if "merge_metadata" in release_actions:
        return "Detected by release comparison against related family members."
    if confidence_level in {"low", "suspicious"}:
        return "Detected by metadata confidence analysis."
    return "Detected by metadata analysis."


def _cleanup_capability(category: str, impact: str, suspicious_ids: set[str], release_actions: set[str], confidence_level: str) -> str:
    if category == "sequencing":
        return "manual_review_required"
    if category == "artwork":
        return "semi_auto_fixable"
    if category == "metadata":
        return "auto_fixable" if (suspicious_ids & {"provider-disagreement", "conflicting-release-year"} or "merge_metadata" in release_actions or confidence_level in {"low", "suspicious"}) else "semi_auto_fixable"
    if category == "release_quality":
        return "manual_review_required"
    if impact == "cosmetic":
        return "semi_auto_fixable"
    return "manual_review_required"


def _cleanup_fix_profile(
    *,
    category: str,
    impact: str,
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    release_actions: set[str],
    confidence_level: str,
) -> dict[str, object]:
    capability = _cleanup_capability(category, impact, suspicious_ids, release_actions, confidence_level)
    if category == "sequencing":
        if _has_deterministic_provider_numbering(suspicious_ids, suspicious_items, confidence_level):
            return {
                "tier": "automatic_fix_available",
                "execution_mode": "auto_apply_in_cleanup",
                "primary_eligible": True,
                "capability": "auto_fixable",
                "auto_fix_reason": "Provider-backed track numbering can be applied safely during cleanup.",
                "can_musorg_fix": True,
                "fix_method": "global_cleanup",
                "cta_label": "Run Cleanup",
                "cta_intent": "run_cleanup",
                "after_action": "Musorg will attempt to restore track and disc numbering from trusted metadata providers.",
                "blocking_reason": None,
            }
        if suspicious_ids & {"track-count-mismatch", "provider-disagreement", "runtime-mismatch"}:
            return {
                "tier": "review_needed",
                "execution_mode": "manual_only",
                "primary_eligible": True,
                "capability": "manual_review_required",
                "auto_fix_reason": None,
                "can_musorg_fix": False,
                "fix_method": "manual_review",
                "cta_label": None,
                "cta_intent": "none",
                "after_action": None,
                "blocking_reason": "Musorg cannot safely determine the correct sequence because provider evidence is conflicting.",
            }
        return {
            "tier": "informational",
            "execution_mode": "none",
            "primary_eligible": False,
            "capability": "informational_only",
            "auto_fix_reason": None,
            "can_musorg_fix": False,
            "fix_method": "external_only",
            "cta_label": None,
            "cta_intent": "none",
            "after_action": None,
            "blocking_reason": "Musorg detected a sequencing anomaly but does not have trusted provider evidence for a safe correction.",
        }
    if category == "release_quality":
        return {
            "tier": "review_needed",
            "execution_mode": "manual_only",
            "primary_eligible": True,
            "capability": "manual_review_required",
            "auto_fix_reason": None,
            "can_musorg_fix": False,
            "fix_method": "manual_review",
            "cta_label": None,
            "cta_intent": "none",
            "after_action": None,
            "blocking_reason": "Musorg cannot safely finalize this release because release-level metadata remains contradictory.",
        }
    return {
        "tier": "automatic_fix_available",
        "execution_mode": "auto_apply_in_cleanup",
        "primary_eligible": True,
        "capability": capability if capability != "informational_only" else "auto_fixable",
        "auto_fix_reason": _auto_fix_reason(category, impact, release_actions, confidence_level),
        "can_musorg_fix": True,
        "fix_method": "global_cleanup",
        "cta_label": "Run Cleanup",
        "cta_intent": "run_cleanup",
        "after_action": _after_action(category),
        "blocking_reason": None,
    }


def _cleanup_truth_profile(
    *,
    category: str,
    impact: str,
    suspicious_ids: set[str],
    diagnostics: dict,
    processing_state: str,
) -> dict[str, object]:
    category_diag = diagnostics.get(category) if isinstance(diagnostics, dict) else None
    if not isinstance(category_diag, dict):
        category_diag = {}
    supported = category in {"metadata", "artwork", "sequencing", "processing"}
    trusted_inputs = bool(category_diag.get("trustedProviderInputsAvailable"))
    skip_reason = category_diag.get("skipReason")
    blocking_signals = tuple(str(item) for item in (category_diag.get("blockingSignals") or []) if str(item).strip())
    completed = processing_state == "completed"

    if not supported:
        return {
            "auto_fix_status": "not_auto_fixable",
            "auto_fix_supported": False,
            "auto_fix_attempted": False,
            "auto_fix_explanation": "Automatic correction is not currently supported for this issue.",
            "skip_reason": "unsupported_fix_path",
            "blocking_signals": blocking_signals,
        }
    if skip_reason:
        return {
            "auto_fix_status": "auto_fix_blocked",
            "auto_fix_supported": True,
            "auto_fix_attempted": False,
            "auto_fix_explanation": _blocked_explanation(skip_reason),
            "skip_reason": skip_reason,
            "blocking_signals": blocking_signals,
        }
    if completed:
        if category == "sequencing" and trusted_inputs:
            return {
                "auto_fix_status": "auto_fix_failed",
                "auto_fix_supported": True,
                "auto_fix_attempted": True,
                "auto_fix_explanation": "Cleanup attempted provider-backed correction, but sequencing validation still failed.",
                "skip_reason": None,
                "blocking_signals": blocking_signals,
            }
        return {
            "auto_fix_status": "auto_fix_attempted",
            "auto_fix_supported": True,
            "auto_fix_attempted": True,
            "auto_fix_explanation": "Cleanup attempted an automatic correction, but the issue state did not improve.",
            "skip_reason": None,
            "blocking_signals": blocking_signals,
        }
    if category == "sequencing" and not trusted_inputs:
        return {
            "auto_fix_status": "auto_fix_blocked",
            "auto_fix_supported": True,
            "auto_fix_attempted": False,
            "auto_fix_explanation": "Musorg could not obtain trusted track numbering from metadata providers.",
            "skip_reason": "provider_data_unavailable",
            "blocking_signals": blocking_signals or ("No trusted metadata provider won release selection.",),
        }
    return {
        "auto_fix_status": "auto_fix_pending",
        "auto_fix_supported": True,
        "auto_fix_attempted": False,
        "auto_fix_explanation": _pending_explanation(category, impact),
        "skip_reason": None,
        "blocking_signals": blocking_signals,
    }


def _action_fields_from_truth(
    *,
    category: str,
    impact: str,
    base: dict[str, object],
    truth: dict[str, object],
) -> dict[str, object]:
    status = str(truth["auto_fix_status"])
    if status == "auto_fix_pending":
        return {**base, "action_type": "cleanup_needed"}
    if status == "not_auto_fixable":
        return {
            "action_type": "review_needed" if category in {"sequencing", "release_quality"} else "cleanup_needed",
            "tier": "informational" if impact == "cosmetic" else "review_needed",
            "execution_mode": "manual_only" if impact != "cosmetic" else "none",
            "primary_eligible": impact != "cosmetic",
            "capability": "informational_only" if impact == "cosmetic" else "manual_review_required",
            "auto_fix_reason": None,
            "can_musorg_fix": False,
            "fix_method": "manual_review" if impact != "cosmetic" else "external_only",
            "cta_label": None,
            "cta_intent": "none",
            "after_action": None,
            "blocking_reason": str(truth["auto_fix_explanation"]),
        }
    return {
        "action_type": "review_needed",
        "tier": "review_needed",
        "execution_mode": "manual_only",
        "primary_eligible": True,
        "capability": "manual_review_required",
        "auto_fix_reason": None,
        "can_musorg_fix": False,
        "fix_method": "manual_review",
        "cta_label": None,
        "cta_intent": "none",
        "after_action": None,
        "blocking_reason": str(truth["auto_fix_explanation"]),
    }


def _pending_explanation(category: str, impact: str) -> str:
    if category == "sequencing":
        return "This issue can be fixed automatically during the next cleanup run."
    if category == "artwork":
        return "Cleanup can refresh artwork automatically on the next run."
    if impact == "cosmetic":
        return "Cleanup can apply this minor correction automatically on the next run."
    return "Cleanup can apply this correction automatically on the next run."


def _blocked_explanation(skip_reason: object) -> str:
    mapping = {
        "provider_conflict": "Cleanup skipped automatic correction because providers disagree on the matched release.",
        "confidence_too_low": "Cleanup skipped automatic correction because metadata confidence is too low.",
        "track_mapping_ambiguous": "Cleanup skipped automatic correction because provider track mappings were ambiguous.",
        "release_structure_mismatch": "Cleanup skipped automatic correction because release structure does not match trusted provider data.",
        "unsafe_metadata_overwrite": "Cleanup skipped automatic correction because applying the change would risk an unsafe overwrite.",
        "provider_data_unavailable": "Cleanup skipped automatic correction because trusted provider data was unavailable.",
        "unsupported_fix_path": "Automatic correction is not currently supported for this issue.",
    }
    return mapping.get(str(skip_reason), "Automatic correction is unavailable for this issue.")


def _cleanup_why_matters(category: str, impact: str, suspicious_ids: set[str]) -> str:
    if category == "artwork":
        return "Artwork quality affects presentation only and does not change the audio content."
    if category == "sequencing":
        if "track-count-mismatch" in suspicious_ids:
            return "Album sequencing or release structure may display incorrectly in music players."
        return "Playback order or disc grouping may be incorrect in music players."
    if category == "release_quality":
        return "Release-level inconsistencies can point to the wrong edition or unreliable metadata."
    if impact == "cosmetic":
        return "This is a minor metadata cleanup and does not make the release unsafe to keep."
    return "Metadata may stay inconsistent across music players until it is reviewed."


def _cleanup_suggested_fix(
    category: str,
    impact: str,
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    release_actions: set[str],
    confidence_level: str,
    auto_fix_status: str,
) -> str:
    if auto_fix_status != "auto_fix_pending":
        if auto_fix_status == "auto_fix_blocked":
            return "Automatic correction is not currently available for this release."
        if auto_fix_status == "auto_fix_failed":
            return "Review the blocking provider signals before trying cleanup again."
        if auto_fix_status == "auto_fix_attempted":
            return "Review the remaining issue state before re-running cleanup."
        return "Review this release manually if you still want to change it."
    if category == "sequencing":
        if _has_deterministic_provider_numbering(suspicious_ids, suspicious_items, confidence_level):
            return "Re-run cleanup to apply provider-backed track numbering."
        if suspicious_ids & {"track-count-mismatch", "provider-disagreement", "runtime-mismatch"}:
            return "Review disc and track numbering for the flagged tracks."
        return "Review this sequencing warning only if playback order still looks wrong after cleanup."
    if category == "artwork":
        return "Refresh artwork from the stronger related release."
    if category == "metadata" and (suspicious_ids & {"provider-disagreement", "conflicting-release-year"} or "merge_metadata" in release_actions or confidence_level in {"low", "suspicious"}):
        return "Re-run metadata cleanup."
    if category == "release_quality":
        return "Review the selected release before treating this metadata as final."
    if impact == "cosmetic":
        return "Re-run metadata cleanup if you want to polish this release."
    return "Review this release before finalizing the metadata."


def _cleanup_resolution_confidence(
    category: str,
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    release_actions: set[str],
    confidence_level: str,
) -> str:
    if category == "sequencing" and (_sequencing_evidence(suspicious_items.get("broken-sequencing")) or _track_count_evidence(suspicious_items.get("track-count-mismatch"))):
        return "high"
    if category == "artwork":
        return "medium"
    if category == "metadata" and (suspicious_ids & {"provider-disagreement", "conflicting-release-year"} or "merge_metadata" in release_actions):
        return "medium"
    if confidence_level in {"low", "suspicious"}:
        return "low"
    return "medium"


def _cleanup_evidence(
    *,
    category: str,
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    release_actions: set[str],
    confidence_level: str,
) -> tuple[str, ...]:
    evidence: list[str] = []
    if "broken-sequencing" in suspicious_ids:
        evidence.extend(_sequencing_evidence(suspicious_items.get("broken-sequencing")))
    if "duplicate-tracks" in suspicious_ids:
        evidence.extend(_duplicate_track_evidence(suspicious_items.get("duplicate-tracks")))
    if "track-count-mismatch" in suspicious_ids:
        evidence.extend(_track_count_evidence(suspicious_items.get("track-count-mismatch")))
    if "provider-disagreement" in suspicious_ids:
        evidence.append("Providers disagreed on important release details.")
    if "conflicting-release-year" in suspicious_ids:
        details = suspicious_items.get("conflicting-release-year") or {}
        deezer_year = _detail_value(details, "deezerYear")
        musicbrainz_year = _detail_value(details, "musicbrainzYear")
        if deezer_year and musicbrainz_year:
            evidence.append(f"Providers suggested different years: {deezer_year} vs {musicbrainz_year}.")
    if "replace_artwork" in release_actions or "low-quality-artwork" in suspicious_ids:
        evidence.append("A related release offers stronger artwork coverage.")
    if "merge_metadata" in release_actions:
        evidence.append("A related release has cleaner metadata coverage.")
    if confidence_level in {"low", "suspicious"}:
        evidence.append("Metadata confidence is still incomplete for this release.")
    if category == "artwork" and not evidence:
        evidence.append("Artwork quality was flagged during metadata analysis.")
    return tuple(evidence)


def _auto_fix_reason(category: str, impact: str, release_actions: set[str], confidence_level: str) -> str | None:
    if category == "artwork":
        return "Cleanup can refresh artwork automatically from stronger release metadata."
    if category == "metadata":
        if "merge_metadata" in release_actions or confidence_level in {"low", "suspicious"}:
            return "Cleanup can reapply provider-backed metadata normalization safely."
        return "Cleanup can normalize these metadata fields automatically."
    if category == "processing":
        return "Cleanup can rebuild the processed output deterministically."
    if impact == "cosmetic":
        return "Cleanup can apply this polish step automatically."
    return "Cleanup can apply this correction automatically."


def _after_action(category: str) -> str:
    if category == "artwork":
        return "Musorg will attempt to refresh artwork coverage during the next cleanup run."
    if category == "metadata":
        return "Musorg will rerun metadata normalization and apply trusted provider values where available."
    if category == "sequencing":
        return "Musorg will attempt to restore track and disc numbering from trusted metadata providers."
    if category == "processing":
        return "Musorg will rerun cleanup and rebuild the processed output."
    return "Musorg will apply the available cleanup correction during the next cleanup run."


def _has_deterministic_provider_numbering(
    suspicious_ids: set[str],
    suspicious_items: dict[str, dict],
    confidence_level: str,
) -> bool:
    if not (suspicious_ids & _SEQUENCING_SUSPICIOUS_IDS):
        return False
    if suspicious_ids & {"track-count-mismatch", "provider-disagreement", "runtime-mismatch", "mixed-primary-artists", "unofficial-release"}:
        return False
    if confidence_level not in {"high", "medium"}:
        return False
    return bool(
        _sequencing_evidence(suspicious_items.get("broken-sequencing"))
        or _duplicate_track_evidence(suspicious_items.get("duplicate-tracks"))
    )


def _prepared_fix(
    *,
    kind: str,
    summary: str,
    source_paths: tuple[str, ...],
    planned_changes: tuple[str, ...],
) -> dict[str, object]:
    return {
        "kind": kind,
        "summary": summary,
        "sourceAlbumIds": list(source_paths),
        "targetAlbumIds": [],
        "plannedChanges": list(planned_changes),
    }


def _sequencing_evidence(item: dict | None) -> tuple[str, ...]:
    details = _details(item)
    evidence: list[str] = []
    missing = details.get("missingTrackNumbers") or []
    if isinstance(missing, list) and missing:
        evidence.append(f"Missing track numbers detected on tracks {_format_positions(missing)}.")
    duplicates = details.get("duplicateTrackNumbers") or []
    if isinstance(duplicates, list):
        for duplicate in duplicates[:2]:
            disc = int(duplicate.get("disc") or 1)
            track = int(duplicate.get("track") or 0)
            if track:
                evidence.append(f"Duplicate track number detected on disc {disc}: {track:02d}.")
    jump = details.get("firstSequenceJump") or {}
    if isinstance(jump, dict) and jump.get("from") and jump.get("to"):
        evidence.append(f"Track sequence jumps from {int(jump['from'])} to {int(jump['to'])} on disc {int(jump.get('disc') or 1)}.")
    reverse = details.get("firstOutOfOrderPair") or {}
    if isinstance(reverse, dict) and reverse.get("previousTrack") and reverse.get("currentTrack"):
        evidence.append(f"Track order reverses from {int(reverse['previousTrack'])} to {int(reverse['currentTrack'])} on disc {int(reverse.get('disc') or 1)}.")
    discs = details.get("discNumbers") or []
    if isinstance(discs, list) and discs:
        evidence.append(f"Disc numbering metadata is inconsistent: {_format_positions(discs)}.")
    return tuple(evidence)


def _duplicate_track_evidence(item: dict | None) -> tuple[str, ...]:
    details = _details(item)
    evidence: list[str] = []
    duplicates = details.get("duplicateTitles") or []
    if isinstance(duplicates, list):
        for duplicate in duplicates[:2]:
            title = str(duplicate.get("title") or "Unknown title")
            positions = duplicate.get("positions") or []
            if isinstance(positions, list) and positions:
                evidence.append(f'Duplicate title detected on tracks {_format_positions(positions)}: "{title}".')
    return tuple(evidence)


def _track_count_evidence(item: dict | None) -> tuple[str, ...]:
    details = _details(item)
    local_track_count = details.get("localTrackCount")
    provider_track_count = details.get("providerTrackCount")
    if local_track_count and provider_track_count:
        return (f"Provider track count differs from the local album: {int(local_track_count)} vs {int(provider_track_count)}.",)
    return ("Provider track count does not match the local album.",) if item else ()


def _details(item: dict | None) -> dict:
    if not isinstance(item, dict):
        return {}
    details = item.get("details")
    return details if isinstance(details, dict) else {}


def _detail_value(item: dict | None, key: str) -> str | None:
    details = _details(item)
    value = details.get(key)
    text = str(value).strip() if value not in (None, "") else ""
    return text or None


def _format_positions(values: list[object]) -> str:
    cleaned = [str(value) for value in values if value not in (None, "")]
    return ", ".join(cleaned[:4])
