from __future__ import annotations

from musorg.api.schemas.music import LogEntrySchema, LogsResponse, LogStepSchema
from musorg.api.services.cleanup_runs import get_active_cleanup_run
from musorg.api.services.log_stream import log_broadcaster


_STEP_LABELS = {
    "scan_stage": "Scanning",
    "metadata_stage": "Reading Metadata",
    "group_by_album": "Matching",
    "organize_stage": "Organizing",
    "done": "All done",
}

_ORDERED_STAGE_IDS = (
    "scan_stage",
    "metadata_stage",
    "group_by_album",
    "organize_stage",
)

_MATCHING_PROGRESS_EVENT_TYPES = {
    "album_processing_started",
    "metadata_match",
    "provider_fallback",
    "fallback_triggered",
    "issue_detected",
    "metadata_resolved",
}
_MATCHING_PHASE_STARTED = "matching_phase_started"
_MATCHING_PHASE_COMPLETED = "matching_phase_completed"


def get_logs_payload() -> LogsResponse:
    active_run = get_active_cleanup_run()
    if active_run is None:
        return LogsResponse(
            activeRunId=None,
            sessionState="NO_ACTIVE_RUN",
            steps=_idle_steps(),
            logs=[],
        )

    history = log_broadcaster.history_for_run(active_run.run_id)
    return LogsResponse(
        activeRunId=active_run.run_id,
        sessionState=_session_state_for_history(history),
        steps=_steps_for_history(history),
        logs=[
            LogEntrySchema(**entry)
            for entry in history
            if entry.get("channel") == "activity"
        ],
    )


def _idle_steps() -> list[LogStepSchema]:
    return [
        LogStepSchema(id="scan_stage", title=_STEP_LABELS["scan_stage"], status="Idle"),
        LogStepSchema(id="metadata_stage", title=_STEP_LABELS["metadata_stage"], status="Idle"),
        LogStepSchema(id="group_by_album", title=_STEP_LABELS["group_by_album"], status="Idle"),
        LogStepSchema(id="organize_stage", title=_STEP_LABELS["organize_stage"], status="Idle"),
        LogStepSchema(id="done", title=_STEP_LABELS["done"], status="Idle"),
    ]


def _starting_steps() -> list[LogStepSchema]:
    return [
        LogStepSchema(id="scan_stage", title=_STEP_LABELS["scan_stage"], status="Running"),
        LogStepSchema(id="metadata_stage", title=_STEP_LABELS["metadata_stage"], status="Idle"),
        LogStepSchema(id="group_by_album", title=_STEP_LABELS["group_by_album"], status="Idle"),
        LogStepSchema(id="organize_stage", title=_STEP_LABELS["organize_stage"], status="Idle"),
        LogStepSchema(id="done", title=_STEP_LABELS["done"], status="Idle"),
    ]


def _steps_for_history(history: list[dict]) -> list[LogStepSchema]:
    steps = _starting_steps()

    for entry in history:
        event_type = str(entry.get("type") or "")
        stage = str(entry.get("stage") or "")

        if event_type == "run_started":
            steps = _starting_steps()
            continue

        if event_type == "run_failed":
            for step in steps:
                if step.status == "Running":
                    step.status = "Complete"
            steps[-1].status = "Failed"
            continue

        if event_type in {"pipeline_completed", "run_completed", "run_finished"}:
            for step in steps[:-1]:
                step.status = "Complete"
            steps[-1].status = "Complete"
            continue

        if event_type == _MATCHING_PHASE_STARTED:
            steps = _promote_matching_stage(steps)
            continue

        if event_type == _MATCHING_PHASE_COMPLETED:
            steps = _promote_organizing_stage(steps)
            continue

        if _should_ignore_internal_stage_transition(steps, event_type, stage):
            continue

        if event_type == "stage_started":
            steps = _apply_stage_started(steps, stage)
            continue

        if event_type in {"stage_completed", "stage_finished"}:
            steps = _apply_stage_completed(steps, stage)
            continue

        if _is_matching_progress_event(entry):
            steps = _promote_matching_stage(steps)

    return steps


def _is_matching_progress_event(entry: dict) -> bool:
    event_type = str(entry.get("type") or "")
    stage = str(entry.get("stage") or "")
    channel = str(entry.get("channel") or "")
    source = str(entry.get("source") or "")
    message = str(entry.get("message") or "")

    if stage == "metadata_stage" and event_type in _MATCHING_PROGRESS_EVENT_TYPES:
        return True
    if event_type != "log" or channel != "activity":
        return False
    if source in {"Deezer", "MusicBrainz"}:
        return True
    return source == "Metadata" and message.startswith("Matching album metadata")


def _promote_matching_stage(steps: list[LogStepSchema]) -> list[LogStepSchema]:
    for step in steps:
        if step.id == "scan_stage":
            step.status = "Complete"
        elif step.id == "metadata_stage":
            step.status = "Complete"
        elif step.id == "group_by_album":
            step.status = "Running"
        elif step.id == "organize_stage":
            step.status = "Idle"
        elif step.id == "done":
            step.status = "Idle"
    return steps


def _promote_organizing_stage(steps: list[LogStepSchema]) -> list[LogStepSchema]:
    for step in steps:
        if step.id in {"scan_stage", "metadata_stage", "group_by_album"}:
            step.status = "Complete"
        elif step.id == "organize_stage":
            step.status = "Running"
        elif step.id == "done":
            step.status = "Idle"
    return steps


def _should_ignore_internal_stage_transition(steps: list[LogStepSchema], event_type: str, stage: str) -> bool:
    if stage == "group_by_album" and event_type in {"stage_started", "stage_completed", "stage_finished"}:
        return True
    if (
        stage == "metadata_stage"
        and event_type == "stage_started"
        and any(step.id == "group_by_album" and step.status == "Running" for step in steps)
    ):
        return True
    if stage == "metadata_stage" and event_type in {"stage_completed", "stage_finished"}:
        return any(step.id == "organize_stage" and step.status in {"Running", "Complete"} for step in steps)
    return False


def _apply_stage_started(steps: list[LogStepSchema], stage: str) -> list[LogStepSchema]:
    stage_index = _ORDERED_STAGE_IDS.index(stage) if stage in _ORDERED_STAGE_IDS else -1
    if stage_index == -1:
        return steps

    for index, step in enumerate(steps[:-1]):
        if index < stage_index:
            step.status = "Complete"
        elif index == stage_index:
            step.status = "Running"
        else:
            step.status = "Idle"
    return steps


def _apply_stage_completed(steps: list[LogStepSchema], stage: str) -> list[LogStepSchema]:
    stage_index = _ORDERED_STAGE_IDS.index(stage) if stage in _ORDERED_STAGE_IDS else -1
    if stage_index == -1:
        return steps

    steps[stage_index].status = "Complete"
    next_stage_index = stage_index + 1
    if next_stage_index < len(_ORDERED_STAGE_IDS):
        steps[next_stage_index].status = "Running"
    else:
        steps[-1].status = "Complete"
    return steps


def _session_state_for_history(history: list[dict]) -> str:
    if not history:
        return "RUN_START"

    latest_type = str(history[-1].get("type") or "")
    if latest_type in {"pipeline_completed", "run_completed", "run_finished", "run_failed"}:
        return "RUN_COMPLETE"

    if any(
        str(entry.get("type") or "") in {
            "stage_started",
            "stage_completed",
            "stage_finished",
            _MATCHING_PHASE_STARTED,
            _MATCHING_PHASE_COMPLETED,
        }
        for entry in history
    ):
        return "RUN_PROGRESS"

    return "RUN_START"
