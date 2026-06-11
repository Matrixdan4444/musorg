from __future__ import annotations

import unittest

from musorg.api.services.workspace_runtime import runtime_issue_counts


class WorkspaceRuntimeIssueCountsTests(unittest.TestCase):
    def test_clean_multi_disc_metadata_does_not_add_warning_count(self):
        counts = runtime_issue_counts(
            [],
            metadata_intelligence={
                "suspiciousMetadata": [],
            },
            complete=True,
        )

        self.assertEqual(counts["danger"], 0)
        self.assertEqual(counts["warning"], 0)
        self.assertEqual(counts["success"], 1)

    def test_broken_sequencing_metadata_still_counts_as_warning(self):
        counts = runtime_issue_counts(
            [],
            metadata_intelligence={
                "suspiciousMetadata": [
                    {
                        "id": "broken-sequencing",
                        "label": "Track sequencing looks broken",
                        "severity": "warning",
                        "message": "Track numbering or ordering in the local album looks inconsistent.",
                    },
                ],
            },
            complete=True,
        )

        self.assertEqual(counts["danger"], 0)
        self.assertEqual(counts["warning"], 1)
        self.assertEqual(counts["success"], 0)
