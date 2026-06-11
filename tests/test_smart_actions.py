from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from musorg.api.schemas.music import LibrarySettingsResponse
from musorg.api.services.library import get_album_actions_payload
from musorg.core.insights.insight_types import InsightRegistry
from musorg.core.release_intelligence import ReleaseIntelligenceRegistry
from musorg.core.smart_actions import build_smart_action_registry


class SmartActionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = "/library/A"

    def test_suspicious_audio_becomes_informational_and_not_primary(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    "releaseFamilyId": "fam-1",
                    "relationshipStatus": "best_version",
                    "bestVersion": True,
                    "duplicateConfidence": 91,
                    "fakeFlacStatus": "likely",
                    "reasons": ["Quality score: 90/100."],
                    "releaseActions": [],
                },
            }),
            _insight_registry([self.path]),
            runtime_state_by_path={self.path: {"processingState": "completed", "outputPath": "/out/A"}},
        )

        payload = registry.payloads_by_path[self.path]
        self.assertIsNone(payload["topAction"])
        audio_action = next(item for item in payload["albumActions"] if item["category"] == "suspicious_audio")
        self.assertEqual(audio_action["tier"], "informational")
        self.assertFalse(audio_action["primaryEligible"])
        self.assertFalse(audio_action["canMusorgFix"])
        self.assertEqual(audio_action["fixMethod"], "external_only")
        self.assertIsNone(audio_action["ctaLabel"])
        self.assertTrue(audio_action["blockingReason"])
        self.assertEqual(audio_action["autoFixStatus"], "not_auto_fixable")
        self.assertFalse(audio_action["autoFixSupported"])
        self.assertFalse(audio_action["autoFixAttempted"])
        self.assertEqual(audio_action["capability"], "informational_only")
        self.assertEqual(audio_action["suggestedFix"], "Compare this release with another source before treating it as primary.")

    def test_historical_cleanup_actions_do_not_create_active_problem(self):
        registry = build_smart_action_registry(
            _release_registry({self.path: _summary()}),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "artist"}, {"kind": "cover"}],
                    "suspiciousMetadata": [],
                },
            },
        )

        payload = registry.payloads_by_path[self.path]
        self.assertEqual(payload["albumActions"], [])
        self.assertIsNone(payload["topAction"])

    def test_artwork_only_cleanup_is_cosmetic_and_calm_for_strong_release(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "qualityScore": 82,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [{"id": "replace_artwork"}],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "cover"}],
                    "suspiciousMetadata": [{"id": "low-quality-artwork"}],
                },
            },
            runtime_state_by_path={self.path: {"processingState": "completed", "outputPath": "/out/A"}},
        )

        cleanup_action = next(item for item in registry.payloads_by_path[self.path]["albumActions"] if item["category"] == "artwork")
        self.assertEqual(cleanup_action["category"], "artwork")
        self.assertEqual(cleanup_action["impact"], "cosmetic")
        self.assertEqual(cleanup_action["severity"], "warning")
        self.assertEqual(cleanup_action["title"], "Minor artwork cleanup")
        self.assertEqual(cleanup_action["tier"], "review_needed")
        self.assertEqual(cleanup_action["executionMode"], "manual_only")
        self.assertFalse(cleanup_action["canMusorgFix"])
        self.assertEqual(cleanup_action["fixMethod"], "manual_review")
        self.assertIsNone(cleanup_action["ctaLabel"])
        self.assertEqual(cleanup_action["autoFixStatus"], "auto_fix_attempted")
        self.assertTrue(cleanup_action["autoFixSupported"])
        self.assertTrue(cleanup_action["autoFixAttempted"])
        self.assertEqual(cleanup_action["autoFixExplanation"], "Cleanup attempted an automatic correction, but the issue state did not improve.")
        self.assertEqual(cleanup_action["blockingReason"], "Cleanup attempted an automatic correction, but the issue state did not improve.")
        self.assertIn("minor artwork cleanup is still available", cleanup_action["contextSummary"].lower())
        self.assertEqual(cleanup_action["capability"], "manual_review_required")
        self.assertEqual(cleanup_action["suggestedFix"], "Review the remaining issue state before re-running cleanup.")
        self.assertEqual(cleanup_action["whyMatters"], "Artwork quality affects presentation only and does not change the audio content.")
        self.assertIn("Artwork quality was flagged by metadata analysis.", cleanup_action["reasoning"])
        self.assertIn("Metadata analysis", cleanup_action["detectedBy"])
        self.assertIsNone(cleanup_action["autoFixReason"])

    def test_metadata_only_cleanup_is_softened_for_strong_release(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "qualityScore": 80,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [{"id": "merge_metadata"}],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "artist"}],
                    "suspiciousMetadata": [],
                    "confidence": {"level": "medium"},
                },
            },
            runtime_state_by_path={self.path: {"processingState": "completed", "outputPath": "/out/A"}},
        )

        cleanup_action = next(item for item in registry.payloads_by_path[self.path]["albumActions"] if item["category"] == "metadata")
        self.assertEqual(cleanup_action["category"], "metadata")
        self.assertEqual(cleanup_action["impact"], "cosmetic")
        self.assertEqual(cleanup_action["severity"], "warning")
        self.assertEqual(cleanup_action["title"], "Minor metadata cleanup")
        self.assertEqual(cleanup_action["tier"], "review_needed")
        self.assertEqual(cleanup_action["executionMode"], "manual_only")
        self.assertFalse(cleanup_action["canMusorgFix"])
        self.assertEqual(cleanup_action["fixMethod"], "manual_review")
        self.assertIsNone(cleanup_action["ctaLabel"])
        self.assertEqual(cleanup_action["autoFixStatus"], "auto_fix_attempted")
        self.assertTrue(cleanup_action["autoFixSupported"])
        self.assertTrue(cleanup_action["autoFixAttempted"])
        self.assertEqual(cleanup_action["autoFixExplanation"], "Cleanup attempted an automatic correction, but the issue state did not improve.")
        self.assertEqual(cleanup_action["capability"], "manual_review_required")
        self.assertEqual(cleanup_action["suggestedFix"], "Review the remaining issue state before re-running cleanup.")
        self.assertIn("overall release quality is strong", cleanup_action["contextSummary"].lower())
        self.assertTrue(any("cleaner metadata coverage" in reason.lower() for reason in cleanup_action["reasoning"]))
        self.assertIsNone(cleanup_action["autoFixReason"])

    def test_provider_backed_sequencing_is_pending_before_cleanup(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "qualityScore": 81,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [{"id": "replace_artwork"}],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "cover"}],
                    "suspiciousMetadata": [
                        {"id": "low-quality-artwork"},
                        {
                            "id": "broken-sequencing",
                            "details": {
                                "missingTrackNumbers": [2],
                                "firstSequenceJump": {"disc": 1, "from": 4, "to": 7, "position": 5},
                            },
                        },
                    ],
                    "confidence": {"level": "high"},
                    "autoFixDiagnostics": {
                        "sequencing": {
                            "issueSignature": "sequencing:test",
                            "trustedProviderInputsAvailable": True,
                            "skipReason": None,
                            "blockingSignals": [],
                        },
                    },
                },
            },
            runtime_state_by_path={self.path: {"processingState": "idle", "outputPath": "/out/A"}},
        )

        top_action = registry.payloads_by_path[self.path]["topAction"]
        self.assertEqual(top_action["category"], "sequencing")
        self.assertEqual(top_action["impact"], "important")
        self.assertEqual(top_action["type"], "cleanup_needed")
        self.assertEqual(top_action["tier"], "automatic_fix_available")
        self.assertEqual(top_action["executionMode"], "auto_apply_in_cleanup")
        self.assertTrue(top_action["canMusorgFix"])
        self.assertEqual(top_action["fixMethod"], "global_cleanup")
        self.assertEqual(top_action["ctaLabel"], "Run Cleanup")
        self.assertEqual(top_action["ctaIntent"], "run_cleanup")
        self.assertEqual(top_action["autoFixStatus"], "auto_fix_pending")
        self.assertTrue(top_action["autoFixSupported"])
        self.assertFalse(top_action["autoFixAttempted"])
        self.assertEqual(top_action["afterAction"], "Musorg will attempt to restore track and disc numbering from trusted metadata providers.")
        self.assertIsNone(top_action["blockingReason"])
        self.assertEqual(top_action["capability"], "auto_fixable")
        self.assertEqual(top_action["resolutionConfidence"], "high")
        self.assertEqual(top_action["suggestedFix"], "Re-run cleanup to apply provider-backed track numbering.")
        self.assertEqual(top_action["autoFixReason"], "Provider-backed track numbering can be applied safely during cleanup.")
        self.assertIn("Playback order or disc grouping may be incorrect in music players.", top_action["whyMatters"])
        self.assertTrue(any("Missing track numbers detected on tracks 2." == item for item in top_action["evidence"]))
        self.assertTrue(any("Track sequence jumps from 4 to 7 on disc 1." == item for item in top_action["evidence"]))

    def test_provider_backed_sequencing_becomes_failed_after_cleanup_if_unresolved(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "qualityScore": 81,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [{"id": "replace_artwork"}],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "cover"}],
                    "suspiciousMetadata": [
                        {"id": "low-quality-artwork"},
                        {
                            "id": "broken-sequencing",
                            "details": {
                                "missingTrackNumbers": [2],
                                "firstSequenceJump": {"disc": 1, "from": 4, "to": 7, "position": 5},
                            },
                        },
                    ],
                    "confidence": {"level": "high"},
                    "autoFixDiagnostics": {
                        "sequencing": {
                            "issueSignature": "sequencing:test",
                            "trustedProviderInputsAvailable": True,
                            "skipReason": None,
                            "blockingSignals": [],
                        },
                    },
                },
            },
            runtime_state_by_path={self.path: {"processingState": "completed", "outputPath": "/out/A"}},
        )

        top_action = registry.payloads_by_path[self.path]["topAction"]
        self.assertEqual(top_action["category"], "sequencing")
        self.assertEqual(top_action["impact"], "important")
        self.assertEqual(top_action["type"], "review_needed")
        self.assertEqual(top_action["tier"], "review_needed")
        self.assertEqual(top_action["executionMode"], "manual_only")
        self.assertFalse(top_action["canMusorgFix"])
        self.assertEqual(top_action["fixMethod"], "manual_review")
        self.assertIsNone(top_action["ctaLabel"])
        self.assertEqual(top_action["autoFixStatus"], "auto_fix_failed")
        self.assertTrue(top_action["autoFixSupported"])
        self.assertTrue(top_action["autoFixAttempted"])
        self.assertEqual(top_action["autoFixExplanation"], "Cleanup attempted provider-backed correction, but sequencing validation still failed.")
        self.assertEqual(top_action["blockingReason"], "Cleanup attempted provider-backed correction, but sequencing validation still failed.")
        self.assertEqual(top_action["capability"], "manual_review_required")
        self.assertEqual(top_action["resolutionConfidence"], "high")
        self.assertEqual(top_action["suggestedFix"], "Review the blocking provider signals before trying cleanup again.")
        self.assertIsNone(top_action["autoFixReason"])
        self.assertIn("Playback order or disc grouping may be incorrect in music players.", top_action["whyMatters"])
        self.assertTrue(any("Missing track numbers detected on tracks 2." == item for item in top_action["evidence"]))
        self.assertTrue(any("Track sequence jumps from 4 to 7 on disc 1." == item for item in top_action["evidence"]))

    def test_valid_interleaved_multi_disc_album_does_not_create_sequencing_action(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "qualityScore": 81,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "genre"}, {"kind": "provider_selection"}],
                    "suspiciousMetadata": [],
                    "confidence": {"level": "high"},
                    "autoFixDiagnostics": {
                        "sequencing": {
                            "issueSignature": "sequencing:clean",
                            "trustedProviderInputsAvailable": True,
                            "skipReason": None,
                            "blockingSignals": [],
                        },
                    },
                },
            },
            runtime_state_by_path={self.path: {"processingState": "completed", "outputPath": "/out/A"}},
        )

        payload = registry.payloads_by_path[self.path]
        self.assertIsNone(payload["topAction"])
        self.assertFalse(any(item["category"] == "sequencing" for item in payload["albumActions"]))

    def test_ambiguous_sequencing_downgrades_from_primary(self):
        registry = build_smart_action_registry(
            _release_registry({self.path: {**_summary(), "qualityScore": 79}}),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "suspiciousMetadata": [
                        {
                            "id": "broken-sequencing",
                            "details": {"firstSequenceJump": {"disc": 1, "from": 4, "to": 7, "position": 5}},
                        },
                        {"id": "provider-disagreement"},
                    ],
                    "confidence": {"level": "medium"},
                    "autoFixDiagnostics": {
                        "sequencing": {
                            "issueSignature": "sequencing:blocked",
                            "trustedProviderInputsAvailable": False,
                            "skipReason": "provider_conflict",
                            "blockingSignals": [
                                "MusicBrainz track count: 13",
                                "Deezer track count: 14",
                                "Local track count: 13",
                                "Provider disagreement prevents safe renumbering.",
                            ],
                        },
                    },
                },
            },
        )

        top_action = registry.payloads_by_path[self.path]["topAction"]
        self.assertEqual(top_action["type"], "review_needed")
        self.assertEqual(top_action["tier"], "review_needed")
        self.assertEqual(top_action["executionMode"], "manual_only")
        self.assertFalse(top_action["canMusorgFix"])
        self.assertEqual(top_action["fixMethod"], "manual_review")
        self.assertIsNone(top_action["ctaLabel"])
        self.assertEqual(top_action["autoFixStatus"], "auto_fix_blocked")
        self.assertTrue(top_action["blockingReason"])
        self.assertEqual(top_action["skipReason"], "provider_conflict")
        self.assertTrue(top_action["blockingSignals"])
        self.assertTrue(any("MusicBrainz track count" in item or "Deezer track count" in item for item in top_action["blockingSignals"]))

    def test_low_confidence_replace_downgrades_to_review(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    "releaseFamilyId": "fam-1",
                    "relationshipStatus": "better_version_available",
                    "bestVersion": False,
                    "duplicateConfidence": 74,
                    "fakeFlacStatus": "none",
                    "reasons": ["A stronger copy exists in the family."],
                    "releaseActions": [{"id": "replace_lossy_release"}],
                },
            }),
            _insight_registry([self.path]),
        )

        payload = registry.payloads_by_path[self.path]
        self.assertEqual(payload["topAction"]["type"], "review_needed")
        self.assertEqual(payload["topAction"]["tier"], "review_needed")
        self.assertFalse(payload["topAction"]["canMusorgFix"])
        self.assertEqual(payload["topAction"]["fixMethod"], "manual_review")
        self.assertTrue(payload["topAction"]["blockingReason"])
        self.assertEqual(payload["topAction"]["autoFixStatus"], "not_auto_fixable")
        self.assertFalse(any(item["type"] == "replace_recommended" for item in payload["albumActions"]))

    def test_completed_cleanup_does_not_reemit_pending_for_same_metadata_issue(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "qualityScore": 76,
                    "releaseActions": [{"id": "merge_metadata"}],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "artist"}],
                    "confidence": {"level": "medium"},
                },
            },
            runtime_state_by_path={self.path: {"processingState": "completed", "outputPath": "/out/A"}},
        )

        cleanup_action = next(item for item in registry.payloads_by_path[self.path]["albumActions"] if item["category"] == "metadata")
        self.assertNotEqual(cleanup_action["autoFixStatus"], "auto_fix_pending")
        self.assertFalse(cleanup_action["canMusorgFix"])
        self.assertIsNone(cleanup_action["ctaLabel"])

    def test_top_action_resists_same_band_replacement(self):
        first = build_smart_action_registry(
            _release_registry({
                self.path: {
                    "releaseFamilyId": "fam-1",
                    "relationshipStatus": "exact_duplicate",
                    "bestVersion": False,
                    "duplicateConfidence": 87,
                    "fakeFlacStatus": "none",
                    "reasons": ["13/13 tracks matched."],
                    "releaseActions": [],
                },
            }),
            _insight_registry([self.path]),
            duplicate_handling="move_duplicates_to_archive",
        )
        self.assertEqual(first.payloads_by_path[self.path]["topAction"]["type"], "archive_recommended")
        self.assertEqual(first.payloads_by_path[self.path]["topAction"]["tier"], "fix_prepared")
        self.assertFalse(first.payloads_by_path[self.path]["topAction"]["canMusorgFix"])
        self.assertIsNone(first.payloads_by_path[self.path]["topAction"]["ctaLabel"])

        second = build_smart_action_registry(
            _release_registry({
                self.path: {
                    "releaseFamilyId": "fam-1",
                    "relationshipStatus": "exact_duplicate",
                    "bestVersion": False,
                    "duplicateConfidence": 87,
                    "fakeFlacStatus": "none",
                    "reasons": ["13/13 tracks matched."],
                    "releaseActions": [{"id": "replace_lossy_release"}],
                },
            }),
            _insight_registry([self.path]),
            duplicate_handling="move_duplicates_to_archive",
        )

        self.assertEqual(second.payloads_by_path[self.path]["topAction"]["type"], "archive_recommended")
        self.assertEqual(second.payloads_by_path[self.path]["topAction"]["tier"], "fix_prepared")
        self.assertTrue(any(item["type"] == "replace_recommended" for item in second.payloads_by_path[self.path]["albumActions"]))

    def test_keep_everything_downgrades_duplicate_archive_recommendation(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    "releaseFamilyId": "fam-1",
                    "relationshipStatus": "exact_duplicate",
                    "bestVersion": False,
                    "duplicateConfidence": 91,
                    "fakeFlacStatus": "none",
                    "reasons": ["13/13 tracks matched."],
                    "releaseActions": [],
                },
            }),
            _insight_registry([self.path]),
        )

        top_action = registry.payloads_by_path[self.path]["topAction"]
        self.assertEqual(top_action["type"], "review_needed")
        self.assertEqual(top_action["tier"], "review_needed")
        self.assertFalse(any(item["type"] == "archive_recommended" for item in registry.payloads_by_path[self.path]["albumActions"]))

    def test_generic_cleanup_wording_is_absent(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    **_summary(),
                    "releaseActions": [{"id": "merge_metadata"}],
                },
            }),
            _insight_registry([self.path]),
            metadata_intelligence_by_path={
                self.path: {
                    "cleanupActions": [{"kind": "artist"}],
                    "suspiciousMetadata": [{"id": "provider-disagreement"}],
                    "confidence": {"level": "low"},
                },
            },
        )

        action = registry.payloads_by_path[self.path]["topAction"]
        rendered = " ".join([
            action["title"],
            action["message"],
            action["whyMatters"],
            action["suggestedFix"],
            *action["evidence"],
            *action["reasoning"],
        ]).lower()
        self.assertNotIn("cleanup opportunities are still available", rendered)
        self.assertNotIn("metadata review signals are still present", rendered)
        self.assertNotIn("metadata or artwork cleanup is still recommended", rendered)

    def test_family_duplicate_cluster_becomes_grouped_action(self):
        paths = ("/library/A", "/library/B", "/library/C")
        registry = build_smart_action_registry(
            _release_registry({
                paths[0]: {
                    "releaseFamilyId": "fam-2",
                    "relationshipStatus": "best_version",
                    "bestVersion": True,
                    "duplicateConfidence": 93,
                    "fakeFlacStatus": "none",
                    "reasons": [],
                    "releaseActions": [],
                },
                paths[1]: {
                    "releaseFamilyId": "fam-2",
                    "relationshipStatus": "exact_duplicate",
                    "bestVersion": False,
                    "duplicateConfidence": 93,
                    "fakeFlacStatus": "none",
                    "reasons": [],
                    "releaseActions": [],
                },
                paths[2]: {
                    "releaseFamilyId": "fam-2",
                    "relationshipStatus": "better_version_available",
                    "bestVersion": False,
                    "duplicateConfidence": 90,
                    "fakeFlacStatus": "none",
                    "reasons": [],
                    "releaseActions": [{"id": "replace_lossy_release"}],
                },
            }),
            _insight_registry(paths),
            runtime_state_by_path={path: {"processingState": "completed", "outputPath": f"/out/{index}"} for index, path in enumerate(paths)},
            duplicate_handling="move_duplicates_to_archive",
        )

        self.assertTrue(any(action["group"] == "collection" for action in registry.collection_actions))
        self.assertTrue(any("Family Cleanup Recommended" in action["title"] for action in registry.collection_actions))
        duplicate_payload = registry.payloads_by_path[paths[1]]
        self.assertTrue(duplicate_payload["familyActions"])
        self.assertEqual(duplicate_payload["familyActions"][0]["tier"], "fix_prepared")
        self.assertTrue(any(item["suppressedByActionId"] for item in duplicate_payload["suppressedActions"]))

    def test_grouped_action_ids_are_deterministic(self):
        paths = ("/library/A", "/library/B", "/library/C")
        registry_one = build_smart_action_registry(
            _release_registry({path: _duplicate_summary("fam-7", 91) for path in paths}),
            _insight_registry(paths),
            duplicate_handling="move_duplicates_to_archive",
        )
        registry_two = build_smart_action_registry(
            _release_registry({path: _duplicate_summary("fam-7", 91) for path in reversed(paths)}),
            _insight_registry(tuple(reversed(paths))),
            duplicate_handling="move_duplicates_to_archive",
        )

        family_action_one = registry_one.payloads_by_path[paths[0]]["familyActions"][0]
        family_action_two = registry_two.payloads_by_path[paths[0]]["familyActions"][0]
        self.assertEqual(family_action_one["id"], family_action_two["id"])
        self.assertEqual(registry_one.collection_actions[0]["id"], registry_two.collection_actions[0]["id"])

    def test_collection_actions_split_same_domain_by_remediation_status(self):
        paths = ("/library/A", "/library/B")
        registry = build_smart_action_registry(
            _release_registry({
                paths[0]: {
                    **_summary(),
                    "qualityScore": 82,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [{"id": "replace_artwork"}],
                },
                paths[1]: {
                    **_summary(),
                    "qualityScore": 79,
                    "bestVersion": True,
                    "relationshipStatus": "best_version",
                    "releaseActions": [{"id": "replace_artwork"}],
                },
            }),
            _insight_registry(paths),
            metadata_intelligence_by_path={
                paths[0]: {
                    "cleanupActions": [{"kind": "cover"}],
                    "suspiciousMetadata": [{"id": "low-quality-artwork"}],
                    "autoFixDiagnostics": {
                        "artwork": {
                            "issueSignature": "artwork:pending",
                            "trustedProviderInputsAvailable": True,
                            "skipReason": None,
                            "blockingSignals": [],
                        },
                    },
                },
                paths[1]: {
                    "cleanupActions": [{"kind": "cover"}],
                    "suspiciousMetadata": [{"id": "low-quality-artwork"}],
                    "autoFixDiagnostics": {
                        "artwork": {
                            "issueSignature": "artwork:blocked",
                            "trustedProviderInputsAvailable": False,
                            "skipReason": "provider_data_unavailable",
                            "blockingSignals": ["No trusted provider artwork available."],
                        },
                    },
                },
            },
            runtime_state_by_path={
                paths[0]: {"processingState": "idle", "outputPath": "/out/A"},
                paths[1]: {"processingState": "idle", "outputPath": "/out/B"},
            },
        )

        self.assertEqual(len(registry.collection_actions), 2)
        self.assertEqual({action["autoFixStatus"] for action in registry.collection_actions}, {"auto_fix_pending", "auto_fix_blocked"})

    def test_registry_cache_is_snapshot_scoped(self):
        release_registry = _release_registry({self.path: _summary()})
        insight_registry = _insight_registry([self.path])

        first = build_smart_action_registry(release_registry, insight_registry)
        second = build_smart_action_registry(release_registry, insight_registry)

        self.assertIs(first, second)

        third = build_smart_action_registry(
            _release_registry({self.path: {**_summary(), "fakeFlacStatus": "possible"}}),
            insight_registry,
        )
        self.assertIsNot(first, third)

    def test_large_family_payload_is_capped(self):
        paths = tuple(f"/library/{index}" for index in range(12))
        release_registry = _release_registry({
            path: _duplicate_summary("fam-9", 92)
            for path in paths
        })
        registry = build_smart_action_registry(release_registry, _insight_registry(paths))

        family_actions = registry.payloads_by_path[paths[0]]["familyActions"]
        self.assertTrue(family_actions)
        self.assertLessEqual(len(family_actions[0]["affectedAlbumPaths"]), 8)

    def test_reasoning_is_capped_and_deduplicated(self):
        registry = build_smart_action_registry(
            _release_registry({
                self.path: {
                    "releaseFamilyId": "fam-1",
                    "relationshipStatus": "near_duplicate",
                    "bestVersion": False,
                    "duplicateConfidence": 68,
                    "fakeFlacStatus": "none",
                    "reasons": [
                        "A" * 200,
                        "13/13 tracks matched.",
                        "13/13 tracks matched.",
                        "Artwork differs.",
                        "Metadata differs.",
                    ],
                    "releaseActions": [],
                },
            }),
            _insight_registry([self.path]),
        )

        reasoning = registry.payloads_by_path[self.path]["topAction"]["reasoning"]
        self.assertLessEqual(len(reasoning), 3)
        self.assertTrue(all(len(item) <= 140 for item in reasoning))
        self.assertEqual(len(reasoning), len(set(reasoning)))

    def test_failures_degrade_to_empty_actions(self):
        with patch("musorg.core.smart_actions.smart_action_engine.build_album_actions", side_effect=RuntimeError("boom")):
            registry = build_smart_action_registry(
                _release_registry({self.path: _summary()}),
                _insight_registry([self.path]),
            )

        payload = registry.payloads_by_path[self.path]
        self.assertIsNone(payload["topAction"])
        self.assertEqual(payload["albumActions"], [])
        self.assertEqual(payload["familyActions"], [])


class SmartActionServiceTests(unittest.TestCase):
    def test_album_actions_payload_serializes_snapshot_and_related_ids(self):
        with TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            album_dir = root / "Album"
            album_dir.mkdir()
            album_id = get_encoded_id(str(album_dir.resolve()))
            settings_state = LibrarySettingsResponse(
                libraryRoot=str(root),
                outputRoot=str(root / "out"),
                developerMode=False,
                language="en",
                duplicateHandling="prefer_best_version",
                filenameCompatibility="preserve_original",
                isConfigured=True,
                isAvailable=True,
                source="settings",
                pickerAvailable=True,
            )
            release_registry = _release_registry({
                str(album_dir.resolve()): {
                    "releaseFamilyId": "fam-3",
                    "relationshipStatus": "best_version",
                    "bestVersion": True,
                    "duplicateConfidence": 87,
                    "fakeFlacStatus": "none",
                    "reasons": ["Quality score: 88/100."],
                    "releaseActions": [],
                },
            })
            insight_registry = _insight_registry([str(album_dir.resolve())])
            with (
                patch("musorg.api.services.library.get_library_settings_state", return_value=settings_state),
                patch("musorg.api.services.library._latest_metadata_intelligence_by_path", return_value={}),
                patch("musorg.api.services.library.build_release_intelligence_registry", return_value=release_registry),
                patch("musorg.api.services.library.build_insight_registry", return_value=insight_registry),
                patch("musorg.api.services.library._latest_output_path_by_source", return_value={}),
                patch("musorg.api.services.library.resolve_album_runtime_state", return_value=type("Resolution", (), {
                    "processing_state": None,
                    "output_path": None,
                    "resolved_folder_path": str(album_dir.resolve()),
                    "resolved_mode": "source",
                })()),
            ):
                payload = get_album_actions_payload(album_id)

            self.assertTrue(payload.snapshotId)
            self.assertIsNone(payload.topAction)
        self.assertEqual(payload.snapshotId, payload.actionSummary[0].snapshotId)
        self.assertEqual(payload.actionSummary[0].type, "keep_recommended")
        self.assertEqual(payload.actionSummary[0].tier, "informational")
        self.assertFalse(payload.actionSummary[0].primaryEligible)
        self.assertFalse(payload.actionSummary[0].canMusorgFix)
        self.assertEqual(payload.actionSummary[0].fixMethod, "external_only")


def _summary() -> dict:
    return {
        "releaseFamilyId": "fam-default",
        "relationshipStatus": "standalone",
        "bestVersion": False,
        "duplicateConfidence": 0,
        "fakeFlacStatus": "none",
        "reasons": [],
        "releaseActions": [],
    }


def _duplicate_summary(family_id: str, confidence: int) -> dict:
    return {
        "releaseFamilyId": family_id,
        "relationshipStatus": "exact_duplicate",
        "bestVersion": False,
        "duplicateConfidence": confidence,
        "fakeFlacStatus": "none",
        "reasons": ["13/13 tracks matched."],
        "releaseActions": [],
    }


def _release_registry(summaries: dict[str, dict]) -> ReleaseIntelligenceRegistry:
    return ReleaseIntelligenceRegistry(summaries_by_path=summaries, related_payload_by_path={})


def _insight_registry(paths: tuple[str, ...] | list[str]) -> InsightRegistry:
    return InsightRegistry(
        summaries_by_path={path: {} for path in paths},
        payloads_by_path={path: {"albumInsights": []} for path in paths},
    )


def get_encoded_id(folder_path: str) -> str:
    import base64

    return base64.urlsafe_b64encode(folder_path.encode("utf-8")).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
