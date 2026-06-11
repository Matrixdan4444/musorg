from __future__ import annotations

import unittest

from musorg.core.insights import build_insight_registry
from musorg.core.release_intelligence import ReleaseIntelligenceRegistry


class InsightEngineTests(unittest.TestCase):
    def test_best_version_outranks_metadata_praise(self):
        path = "/library/A"
        release_registry = ReleaseIntelligenceRegistry(
            summaries_by_path={
                path: {
                    "releaseFamilyId": "fam-1",
                    "releaseVariantId": "var-1",
                    "releaseVariantType": "original",
                    "relationshipStatus": "best_version",
                    "qualityScore": 91,
                    "qualityRank": 1,
                    "duplicateConfidence": 92,
                    "relatedReleaseCount": 1,
                    "bestVersion": True,
                    "fakeFlacStatus": "none",
                    "formatSummary": "FLAC",
                    "reasons": ["Higher artwork quality.", "More complete metadata."],
                    "releaseActions": [],
                },
            },
            related_payload_by_path={
                path: {
                    "releaseFamilyId": "fam-1",
                    "current": {
                        "releaseVariantId": "var-1",
                        "releaseVariantType": "original",
                        "relationshipStatus": "best_version",
                        "qualityScore": 91,
                        "bestVersion": True,
                        "formatSummary": "FLAC",
                        "reasons": ["Higher artwork quality."],
                        "current": True,
                    },
                    "family": [
                        {
                            "releaseVariantId": "var-1",
                            "releaseVariantType": "original",
                            "relationshipStatus": "best_version",
                            "qualityScore": 91,
                            "bestVersion": True,
                            "formatSummary": "FLAC",
                            "reasons": ["Higher artwork quality."],
                            "current": True,
                        },
                        {
                            "releaseVariantId": "var-2",
                            "releaseVariantType": "original",
                            "relationshipStatus": "better_version_available",
                            "qualityScore": 68,
                            "bestVersion": False,
                            "formatSummary": "MP3 320",
                            "reasons": ["Lower quality score."],
                            "current": False,
                        },
                    ],
                    "possibleMatches": [],
                },
            },
        )
        metadata_by_path = {
            path: {
                "confidence": {"score": 95, "level": "high", "label": "High confidence", "reasons": ["Metadata is consistent."]},
                "providerDecisions": {"metadataProvider": "deezer"},
                "suspiciousMetadata": [],
            },
        }

        registry = build_insight_registry(release_registry, metadata_by_path)
        summary = registry.summaries_by_path[path]

        self.assertEqual(summary["topInsight"]["title"], "Best version")
        self.assertEqual(summary["topInsight"]["message"], "Recommended as primary version.")
        self.assertTrue(all(item["title"] != "Metadata complete" for item in summary["insightSummary"]))

    def test_suspicious_audio_outranks_best_version(self):
        path = "/library/B"
        release_registry = ReleaseIntelligenceRegistry(
            summaries_by_path={
                path: {
                    "releaseFamilyId": "fam-2",
                    "releaseVariantId": "var-3",
                    "releaseVariantType": "original",
                    "relationshipStatus": "best_version",
                    "qualityScore": 88,
                    "qualityRank": 1,
                    "duplicateConfidence": 88,
                    "relatedReleaseCount": 0,
                    "bestVersion": True,
                    "fakeFlacStatus": "likely",
                    "formatSummary": "FLAC",
                    "reasons": ["Quality score: 88/100."],
                    "releaseActions": [],
                },
            },
            related_payload_by_path={
                path: {
                    "releaseFamilyId": "fam-2",
                    "current": {
                        "releaseVariantId": "var-3",
                        "releaseVariantType": "original",
                        "relationshipStatus": "best_version",
                        "qualityScore": 88,
                        "bestVersion": True,
                        "formatSummary": "FLAC",
                        "reasons": ["Quality score: 88/100."],
                        "current": True,
                    },
                    "family": [
                        {
                            "releaseVariantId": "var-3",
                            "releaseVariantType": "original",
                            "relationshipStatus": "best_version",
                            "qualityScore": 88,
                            "bestVersion": True,
                            "formatSummary": "FLAC",
                            "reasons": ["Quality score: 88/100."],
                            "current": True,
                        },
                    ],
                    "possibleMatches": [],
                },
            },
        )

        registry = build_insight_registry(release_registry, {})
        summary = registry.summaries_by_path[path]
        payload = registry.payloads_by_path[path]

        self.assertEqual(summary["topInsight"]["title"], "Likely lossy source")
        self.assertEqual(payload["recommendationSummary"], "Review audio provenance before keeping this as the primary version.")


if __name__ == "__main__":
    unittest.main()
