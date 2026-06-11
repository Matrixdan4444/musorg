from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from musorg.api.schemas.music import LogsResponse
from musorg.api.services.log_stream import log_broadcaster
from musorg.api.services.logs import get_logs_payload


router = APIRouter(tags=["logs"])


@router.get("/logs", response_model=LogsResponse)
def logs() -> LogsResponse:
    return get_logs_payload()


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    requested_run_id = websocket.query_params.get("runId")
    last_event_id = websocket.query_params.get("lastEventId")
    queue, active_run_id = log_broadcaster.subscribe()
    try:
        target_run_id = requested_run_id or active_run_id
        session_state = "RUN_PROGRESS" if active_run_id else "NO_ACTIVE_RUN"
        await websocket.send_json({
            "id": "connection",
            "timestamp": "",
            "severity": "info",
            "source": "Logs",
            "channel": "runtime",
            "type": "connection",
            "stage": None,
            "message": "connected",
            "payload": {
                "activeRunId": active_run_id,
                "requestedRunId": target_run_id,
                "sessionState": session_state,
            },
            "albumId": None,
            "runId": target_run_id,
        })
        for entry in log_broadcaster.history_for_run(target_run_id, last_event_id):
            await websocket.send_json(entry)

        while True:
            event = await queue.get()
            event_run_id = event.get("runId")
            if requested_run_id and event_run_id != requested_run_id:
                continue
            await websocket.send_json(event)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        log_broadcaster.unsubscribe(queue)
