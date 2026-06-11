from __future__ import annotations

from musorg.core.context import Context


def _runtime_diagnostic_event(run_id: str, message: str, payload: dict | None = None) -> dict:
    return {
        "severity": "info",
        "source": "Runtime",
        "channel": "diagnostic",
        "type": "dev_diagnostic",
        "stage": "pipeline",
        "message": message,
        "payload": payload or {},
        "runId": run_id,
        "_skip_dev_diagnostic": True,
    }


def publish_runtime_event(context: Context, event: dict) -> None:
    broadcaster = getattr(context, "log_broadcaster", None)
    run_id = getattr(context, "run_id", None)
    if not broadcaster or not run_id:
        return
    if getattr(context, "developer_mode", False) and event.get("type") != "dev_diagnostic":
        broadcaster.publish(_runtime_diagnostic_event(
            run_id,
            f"event emitted: {event.get('type') or 'log'}",
            {
                "eventType": event.get("type"),
                "stage": event.get("stage"),
                "albumId": event.get("albumId"),
            },
        ))
    broadcaster.publish({
        **event,
        "channel": event.get("channel") or "runtime",
        "runId": run_id,
        "_developerMode": bool(getattr(context, "developer_mode", False)),
    })
