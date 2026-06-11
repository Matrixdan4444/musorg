from __future__ import annotations

import unittest

from musorg.core.issue_counts import summarize_actionable_issue_items


class IssueCountTests(unittest.TestCase):
    def test_zero_issue_items_are_clean(self):
        counts = summarize_actionable_issue_items([])
        self.assertEqual(counts, {"danger": 0, "warning": 0, "success": 1})

    def test_only_warning_and_danger_count(self):
        counts = summarize_actionable_issue_items([
            {"severity": "danger"},
            {"severity": "warning"},
            {"severity": "neutral"},
            {"severity": "success"},
            {"severity": "info"},
        ])
        self.assertEqual(counts["danger"], 1)
        self.assertEqual(counts["warning"], 1)
        self.assertEqual(counts["success"], 0)

    def test_recommendations_without_problems_do_not_count(self):
        counts = summarize_actionable_issue_items([
            {"severity": "neutral", "title": "Metadata complete"},
            {"severity": "success", "title": "Keep Recommended"},
        ])
        self.assertEqual(counts, {"danger": 0, "warning": 0, "success": 1})

    def test_smart_actions_without_problem_severity_do_not_count(self):
        counts = summarize_actionable_issue_items([
            {"severity": "success", "title": "Keep Recommended"},
            {"severity": "neutral", "title": "Cleanup Needed"},
        ])
        self.assertEqual(counts, {"danger": 0, "warning": 0, "success": 1})

    def test_mixed_warning_error_and_info_states_count_only_actionable(self):
        counts = summarize_actionable_issue_items([
            {"severity": "danger"},
            {"severity": "warning"},
            {"severity": "warning"},
            {"severity": "neutral"},
        ])
        self.assertEqual(counts, {"danger": 1, "warning": 2, "success": 0})


if __name__ == "__main__":
    unittest.main()
