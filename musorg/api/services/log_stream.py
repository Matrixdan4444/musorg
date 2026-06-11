from __future__ import annotations

import asyncio
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from uuid import uuid4


MAX_EVENTS_PER_RUN = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LogSubscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


class LogEventBroadcaster:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[LogSubscriber] = set()
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_EVENTS_PER_RUN))
        self._active_run_id: str | None = None
        self._sequence_by_run = defaultdict(lambda: count(1))

    def set_active_run(self, run_id: str | None) -> None:
        with self._lock:
            self._active_run_id = run_id

    def active_run_id(self) -> str | None:
        with self._lock:
            return self._active_run_id

    def subscribe(self) -> tuple[asyncio.Queue, str | None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        subscriber = LogSubscriber(loop=loop, queue=queue)
        with self._lock:
            self._subscribers.add(subscriber)
            active_run_id = self._active_run_id
        return queue, active_run_id

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = {
                subscriber
                for subscriber in self._subscribers
                if subscriber.queue is not queue
            }

    def history_for_run(self, run_id: str | None, last_event_id: str | None = None) -> list[dict]:
        if not run_id:
            return []
        with self._lock:
            history = list(self._history.get(run_id, ()))
        if not last_event_id:
            return history

        for index, entry in enumerate(history):
            if entry.get("id") == last_event_id:
                return history[index + 1:]
        return history

    def publish(self, event: dict) -> None:
        structured_event = self._structured_event(event)
        run_id = structured_event.get("runId")
        with self._lock:
            if run_id:
                self._history[run_id].append(structured_event)
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(
                    self._enqueue_event,
                    subscriber.queue,
                    structured_event,
                )
            except RuntimeError:
                continue

        if event.get("_developerMode") and not event.get("_skip_dev_diagnostic"):
            diagnostic_name = "websocket_log_emit" if structured_event.get("type") == "log" else "websocket_emit"
            self.publish({
                "severity": "info",
                "source": "WebSocket",
                "channel": "diagnostic",
                "type": "dev_diagnostic",
                "stage": structured_event.get("stage"),
                "message": f"{diagnostic_name}: {structured_event.get('type') or 'log'}",
                "payload": {
                    "eventType": structured_event.get("type"),
                    "stage": structured_event.get("stage"),
                    "albumId": structured_event.get("albumId"),
                    "sequence": structured_event.get("sequence"),
                },
                "runId": run_id,
                "_skip_dev_diagnostic": True,
            })

    def _structured_event(self, event: dict) -> dict:
        run_id = event.get("runId")
        sequence = None
        if run_id:
            sequence = next(self._sequence_by_run[run_id])
        return {
            "id": event.get("id") or uuid4().hex,
            "timestamp": event.get("timestamp") or _now_iso(),
            "severity": event.get("severity") or "info",
            "source": event.get("source") or "Pipeline",
            "channel": event.get("channel") or "activity",
            "type": event.get("type") or "log",
            "stage": event.get("stage"),
            "message": event.get("message") or "",
            "payload": event.get("payload"),
            "albumId": event.get("albumId"),
            "runId": run_id,
            "sequence": sequence,
        }

    @staticmethod
    def _enqueue_event(queue: asyncio.Queue, event: dict) -> None:
        queue.put_nowait(event)


log_broadcaster = LogEventBroadcaster()
