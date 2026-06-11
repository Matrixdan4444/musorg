from __future__ import annotations

import unittest
from unittest.mock import patch

from musorg.api.services.logs import get_logs_payload


class LogsServiceTests(unittest.TestCase):
    def test_get_logs_payload_returns_idle_dashboard_when_no_run_is_active(self):
        with (
            patch("musorg.api.services.logs.get_active_cleanup_run", return_value=None),
            patch("musorg.api.services.logs.log_broadcaster.history_for_run") as history_mock,
        ):
            payload = get_logs_payload()

        self.assertEqual(payload.activeRunId, None)
        self.assertEqual(payload.sessionState, "NO_ACTIVE_RUN")
        self.assertEqual(payload.logs, [])
        self.assertEqual([step.status for step in payload.steps], ["Idle", "Idle", "Idle", "Idle", "Idle"])
        history_mock.assert_not_called()

    def test_get_logs_payload_uses_only_active_run_history(self):
        history = [
            {
                "id": "run-started",
                "timestamp": "2026-05-22T10:00:00Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "run_started",
                "stage": None,
                "message": "started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 1,
            },
            {
                "id": "scan-finished",
                "timestamp": "2026-05-22T10:00:01Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "stage_completed",
                "stage": "scan_stage",
                "message": "scan done",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 2,
            },
            {
                "id": "visible-log",
                "timestamp": "2026-05-22T10:00:02Z",
                "severity": "info",
                "source": "Metadata",
                "channel": "activity",
                "type": "log",
                "stage": None,
                "message": "Matching album metadata...",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 3,
            },
        ]

        with (
            patch(
                "musorg.api.services.logs.get_active_cleanup_run",
                return_value=type("ActiveRun", (), {"run_id": "run-123"})(),
            ),
            patch("musorg.api.services.logs.log_broadcaster.history_for_run", return_value=history) as history_mock,
        ):
            payload = get_logs_payload()

        self.assertEqual(payload.activeRunId, "run-123")
        self.assertEqual(payload.sessionState, "RUN_PROGRESS")
        self.assertEqual([entry.message for entry in payload.logs], ["Matching album metadata..."])
        self.assertEqual(
            [step.status for step in payload.steps],
            ["Complete", "Complete", "Running", "Idle", "Idle"],
        )
        history_mock.assert_called_once_with("run-123")

    def test_get_logs_payload_promotes_matching_stage_on_runtime_matching_events(self):
        history = [
            {
                "id": "run-started",
                "timestamp": "2026-05-22T10:00:00Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "run_started",
                "stage": None,
                "message": "started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 1,
            },
            {
                "id": "scan-finished",
                "timestamp": "2026-05-22T10:00:01Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "stage_completed",
                "stage": "scan_stage",
                "message": "scan done",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 2,
            },
            {
                "id": "metadata-started",
                "timestamp": "2026-05-22T10:00:02Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "stage_started",
                "stage": "metadata_stage",
                "message": "metadata started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 3,
            },
            {
                "id": "fallback",
                "timestamp": "2026-05-22T10:00:03Z",
                "severity": "info",
                "source": "Metadata",
                "channel": "runtime",
                "type": "provider_fallback",
                "stage": "metadata_stage",
                "message": "falling back",
                "payload": {"progress": "matching"},
                "albumId": "album-1",
                "runId": "run-123",
                "sequence": 4,
            },
        ]

        with (
            patch(
                "musorg.api.services.logs.get_active_cleanup_run",
                return_value=type("ActiveRun", (), {"run_id": "run-123"})(),
            ),
            patch("musorg.api.services.logs.log_broadcaster.history_for_run", return_value=history),
        ):
            payload = get_logs_payload()

        self.assertEqual(
            [step.status for step in payload.steps],
            ["Complete", "Complete", "Running", "Idle", "Idle"],
        )

    def test_get_logs_payload_promotes_matching_stage_on_provider_activity_logs(self):
        history = [
            {
                "id": "run-started",
                "timestamp": "2026-05-22T10:00:00Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "run_started",
                "stage": None,
                "message": "started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 1,
            },
            {
                "id": "scan-finished",
                "timestamp": "2026-05-22T10:00:01Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "stage_completed",
                "stage": "scan_stage",
                "message": "scan done",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 2,
            },
            {
                "id": "deezer-log",
                "timestamp": "2026-05-22T10:00:02Z",
                "severity": "info",
                "source": "Deezer",
                "channel": "activity",
                "type": "log",
                "stage": None,
                "message": "Deezer match found for Artist — Album (9 tracks)",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 3,
            },
        ]

        with (
            patch(
                "musorg.api.services.logs.get_active_cleanup_run",
                return_value=type("ActiveRun", (), {"run_id": "run-123"})(),
            ),
            patch("musorg.api.services.logs.log_broadcaster.history_for_run", return_value=history),
        ):
            payload = get_logs_payload()

        self.assertEqual(
            [step.status for step in payload.steps],
            ["Complete", "Complete", "Running", "Idle", "Idle"],
        )

    def test_get_logs_payload_promotes_organizing_stage_on_matching_phase_completed(self):
        history = [
            {
                "id": "run-started",
                "timestamp": "2026-05-22T10:00:00Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "run_started",
                "stage": None,
                "message": "started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 1,
            },
            {
                "id": "matching-started",
                "timestamp": "2026-05-22T10:00:01Z",
                "severity": "info",
                "source": "Metadata",
                "channel": "runtime",
                "type": "matching_phase_started",
                "stage": "metadata_stage",
                "message": "matching started",
                "payload": {"totalAlbums": 2},
                "albumId": None,
                "runId": "run-123",
                "sequence": 2,
            },
            {
                "id": "matching-completed",
                "timestamp": "2026-05-22T10:00:02Z",
                "severity": "info",
                "source": "Metadata",
                "channel": "runtime",
                "type": "matching_phase_completed",
                "stage": "metadata_stage",
                "message": "matching completed",
                "payload": {"resolvedAlbums": 2, "totalAlbums": 2},
                "albumId": None,
                "runId": "run-123",
                "sequence": 3,
            },
            {
                "id": "grouping-started",
                "timestamp": "2026-05-22T10:00:03Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "stage_started",
                "stage": "group_by_album",
                "message": "grouping started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 4,
            },
        ]

        with (
            patch(
                "musorg.api.services.logs.get_active_cleanup_run",
                return_value=type("ActiveRun", (), {"run_id": "run-123"})(),
            ),
            patch("musorg.api.services.logs.log_broadcaster.history_for_run", return_value=history),
        ):
            payload = get_logs_payload()

        self.assertEqual(
            [step.status for step in payload.steps],
            ["Complete", "Complete", "Complete", "Running", "Idle"],
        )

    def test_get_logs_payload_ignores_late_metadata_stage_start_after_matching_begins(self):
        history = [
            {
                "id": "run-started",
                "timestamp": "2026-05-22T10:00:00Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "run_started",
                "stage": None,
                "message": "started",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 1,
            },
            {
                "id": "matching-started",
                "timestamp": "2026-05-22T10:00:01Z",
                "severity": "info",
                "source": "Metadata",
                "channel": "runtime",
                "type": "matching_phase_started",
                "stage": "metadata_stage",
                "message": "matching started",
                "payload": {"totalAlbums": 2},
                "albumId": None,
                "runId": "run-123",
                "sequence": 2,
            },
            {
                "id": "metadata-started-late",
                "timestamp": "2026-05-22T10:00:02Z",
                "severity": "info",
                "source": "Pipeline",
                "channel": "runtime",
                "type": "stage_started",
                "stage": "metadata_stage",
                "message": "metadata started late",
                "payload": None,
                "albumId": None,
                "runId": "run-123",
                "sequence": 3,
            },
        ]

        with (
            patch(
                "musorg.api.services.logs.get_active_cleanup_run",
                return_value=type("ActiveRun", (), {"run_id": "run-123"})(),
            ),
            patch("musorg.api.services.logs.log_broadcaster.history_for_run", return_value=history),
        ):
            payload = get_logs_payload()

        self.assertEqual(
            [step.status for step in payload.steps],
            ["Complete", "Complete", "Running", "Idle", "Idle"],
        )
