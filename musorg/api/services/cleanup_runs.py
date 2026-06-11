from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class ActiveCleanupRun:
    run_id: str
    library_root: str


_RUN_LOCK = threading.Lock()
_ACTIVE_RUN: ActiveCleanupRun | None = None


def create_run_id() -> str:
    return uuid.uuid4().hex


def get_active_cleanup_run() -> ActiveCleanupRun | None:
    with _RUN_LOCK:
        return _ACTIVE_RUN


def try_start_cleanup_run(library_root: str) -> ActiveCleanupRun | None:
    global _ACTIVE_RUN
    with _RUN_LOCK:
        if _ACTIVE_RUN is not None:
            return None
        _ACTIVE_RUN = ActiveCleanupRun(run_id=create_run_id(), library_root=library_root)
        return _ACTIVE_RUN


def finish_cleanup_run(run_id: str) -> None:
    global _ACTIVE_RUN
    with _RUN_LOCK:
        if _ACTIVE_RUN and _ACTIVE_RUN.run_id == run_id:
            _ACTIVE_RUN = None
