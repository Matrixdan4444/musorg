from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from musorg.api.routes.logs import websocket_logs


class _CancelledQueue:
    async def get(self):
        raise asyncio.CancelledError


class _FakeWebSocket:
    def __init__(self, query_params: dict[str, str] | None = None) -> None:
        self.query_params = query_params or {}
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class LogsWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_logs_swallows_cancelled_queue_shutdown(self):
        websocket = _FakeWebSocket()
        queue = _CancelledQueue()

        with (
            patch("musorg.api.routes.logs.log_broadcaster.subscribe", return_value=(queue, "run-123")) as subscribe_mock,
            patch("musorg.api.routes.logs.log_broadcaster.history_for_run", return_value=[]) as history_mock,
            patch("musorg.api.routes.logs.log_broadcaster.unsubscribe") as unsubscribe_mock,
        ):
            await websocket_logs(websocket)

        self.assertTrue(websocket.accepted)
        self.assertEqual(len(websocket.messages), 1)
        self.assertEqual(websocket.messages[0]["type"], "connection")
        self.assertEqual(websocket.messages[0]["runId"], "run-123")
        self.assertEqual(websocket.messages[0]["payload"]["sessionState"], "RUN_PROGRESS")
        subscribe_mock.assert_called_once()
        history_mock.assert_called_once_with("run-123", None)
        unsubscribe_mock.assert_called_once_with(queue)

    async def test_websocket_logs_reports_idle_session_when_no_run_is_active(self):
        websocket = _FakeWebSocket()
        queue = _CancelledQueue()

        with (
            patch("musorg.api.routes.logs.log_broadcaster.subscribe", return_value=(queue, None)),
            patch("musorg.api.routes.logs.log_broadcaster.history_for_run", return_value=[]) as history_mock,
            patch("musorg.api.routes.logs.log_broadcaster.unsubscribe"),
        ):
            await websocket_logs(websocket)

        self.assertTrue(websocket.accepted)
        self.assertEqual(websocket.messages[0]["payload"]["activeRunId"], None)
        self.assertEqual(websocket.messages[0]["payload"]["sessionState"], "NO_ACTIVE_RUN")
        self.assertEqual(websocket.messages[0]["runId"], None)
        history_mock.assert_called_once_with(None, None)
