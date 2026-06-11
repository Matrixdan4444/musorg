from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunOutputContext:
    run_id: str
    output_root: str


_RUN_OUTPUTS_LOCK = threading.Lock()
_RUN_OUTPUTS: dict[str, RunOutputContext] = {}


def register_run_output(run_id: str, output_root: str) -> RunOutputContext:
    context = RunOutputContext(run_id=run_id, output_root=output_root)
    with _RUN_OUTPUTS_LOCK:
        _RUN_OUTPUTS[run_id] = context
    return context


def get_run_output(run_id: str) -> RunOutputContext | None:
    with _RUN_OUTPUTS_LOCK:
        return _RUN_OUTPUTS.get(run_id)


def clear_run_output(run_id: str) -> None:
    with _RUN_OUTPUTS_LOCK:
        _RUN_OUTPUTS.pop(run_id, None)
