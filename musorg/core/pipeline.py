from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from musorg.core.events import publish_runtime_event
from musorg.core.context import Context
from musorg.core.runtime_state import runtime_options
from musorg.core.run_report import RunReport
from musorg.core.stages.grouping import group_by_album
from musorg.core.stages.metadata_read import metadata_stage
from musorg.core.stages.organize import organize_stage
from musorg.core.stages.scan import scan_stage
from musorg.api.services.workspace_runtime import runtime_album_payload
from musorg.utils.debug import clear_log_sink, error, log, set_log_sink, success


@dataclass(frozen=True)
class RunResult:
    albums_processed: int
    tracks_processed: int
    output_path: str | None
    stats: dict


def _runtime_log_sink(context: Context):
    run_report = getattr(context, "run_report", None)
    broadcaster = getattr(context, "log_broadcaster", None)
    run_id = getattr(context, "run_id", None)
    developer_mode = bool(getattr(context, "developer_mode", False))

    def sink(event: dict) -> None:
        if run_report is not None:
            run_report.note_log(event)
        if broadcaster is None or not run_id:
            return
        source = event.get("stage") or "Pipeline"
        message = event.get("message") or ""
        is_diagnostic = str(message).startswith("[DEV MODE]") or source in {"Profile", "Logs"}
        broadcaster.publish({
            "severity": event.get("level") or "info",
            "source": source,
            "channel": "diagnostic" if is_diagnostic else "activity",
            "type": "log",
            "message": message,
            "payload": {"emoji": event.get("emoji")},
            "runId": run_id,
            "_developerMode": developer_mode,
        })

    return sink


def default_stages() -> list:
    return [
        scan_stage,
        metadata_stage,
        group_by_album,
        organize_stage,
    ]


def run_pipeline(
    path: str,
    apply: bool = True,
    output_root: str | None = None,
    developer_mode: bool = False,
) -> RunResult:
    _ensure_not_organized_input(path)
    context = Context(
        path,
        dry_run=not apply,
        output_root=output_root,
        developer_mode=developer_mode,
    )
    return Pipeline().run(context)


def run_pipeline_context(context: Context, stages: list | None = None) -> RunResult:
    _ensure_not_organized_input(context.root_path)
    stage_list = stages or default_stages()
    mode = "dry-run" if getattr(context, "dry_run", False) else "apply"
    context.run_report = RunReport(
        context.root_path,
        dry_run=getattr(context, "dry_run", False),
        run_id=getattr(context, "run_id", None),
    )
    with runtime_options(developer_mode=getattr(context, "developer_mode", False)):
        set_log_sink(_runtime_log_sink(context))
        log("Start", f"Starting music library cleanup ({mode})", "🚀")
        publish_runtime_event(context, {
            "severity": "info",
            "source": "Pipeline",
            "type": "run_started",
            "stage": "pipeline",
            "message": f"Started cleanup run for {context.root_path}",
            "payload": {"mode": mode},
        })
        if getattr(context, "developer_mode", False):
            log(
                "Pipeline",
                "[DEV MODE] Re-running release validation with metadata cache reads bypassed",
                "🧪",
            )

        try:
            for stage in stage_list:
                publish_runtime_event(context, {
                    "severity": "info",
                    "source": "Pipeline",
                    "type": "stage_started",
                    "stage": stage.__name__,
                    "message": f"Stage started: {stage.__name__}",
                    "payload": {"stage": stage.__name__},
                })
                with context.run_report.measure(stage.__name__, stage=True):
                    context = stage(context)
                publish_runtime_event(context, {
                    "severity": "success",
                    "source": "Pipeline",
                    "type": "stage_completed",
                    "stage": stage.__name__,
                    "message": f"Stage complete: {stage.__name__}",
                    "payload": {"stage": stage.__name__},
                })

            if getattr(context, "dry_run", False):
                success("Done", "Dry run complete")
            else:
                success("Done", "Music library cleanup completed")
            completed_albums = []
            for album_tracks in list(getattr(context, "albums", {}).values()):
                payload = runtime_album_payload(
                    album_tracks,
                    processing_state="completed",
                    output_path=getattr(getattr(context, "operation_journal", None), "output_root", None),
                    complete=True,
                )
                if payload:
                    completed_albums.append(payload)
            publish_runtime_event(context, {
                "severity": "success",
                "source": "Pipeline",
                "type": "pipeline_completed",
                "stage": "pipeline",
                "message": "Cleanup run completed",
                "payload": {
                    "outputRoot": getattr(getattr(context, "operation_journal", None), "output_root", None),
                    "albumsProcessed": len(getattr(context, "albums", {}) or {}),
                    "tracksProcessed": len(getattr(context, "tracks", [])),
                    "albums": completed_albums,
                },
            })
            return _build_run_result(context)
        except Exception as exc:
            context.errors.append(str(exc))
            error("Pipeline", f"Run failed: {exc}")
            publish_runtime_event(context, {
                "severity": "error",
                "source": "Pipeline",
                "type": "run_failed",
                "stage": "pipeline",
                "message": f"Cleanup run failed: {exc}",
                "payload": {"error": str(exc)},
            })
            raise
        finally:
            clear_log_sink()
            summary_path = context.run_report.finalize(context) if getattr(context, "run_report", None) else None
            if summary_path:
                metrics = context.run_report.profiling_summary().get("metrics", {})
                hotspots = []
                for name in ("stage:scan_stage", "metadata_fetch", "tag_write", "cover_processing", "stage:organize_stage"):
                    metric = metrics.get(name)
                    if metric:
                        hotspots.append(f"{name}={metric['total_seconds']:.3f}s")
                if hotspots:
                    log("Profile", ", ".join(hotspots), "⏱️")
                log("Logs", f"Run summary written to {summary_path}", "🗂️")


def _build_run_result(context: Context) -> RunResult:
    operation_journal = getattr(context, "operation_journal", None)
    run_report = getattr(context, "run_report", None)
    profiling = run_report.profiling_summary() if run_report else {}
    stats = {
        "files_scanned": len(getattr(context, "files", [])),
        "tracks_processed": len(getattr(context, "tracks", [])),
        "albums_processed": len(getattr(context, "albums", {}) or {}),
        "warnings": len(getattr(run_report, "warnings", [])) if run_report else 0,
        "errors": len(getattr(run_report, "errors", [])) if run_report else 0,
        "duplicates": len(getattr(run_report, "duplicates", [])) if run_report else 0,
        "unresolved_matches": len(getattr(run_report, "unresolved_matches", [])) if run_report else 0,
        "changed_albums": len(getattr(run_report, "changed_albums", [])) if run_report else 0,
        "dry_run": getattr(context, "dry_run", False),
        "profiling": profiling,
        "summary_path": getattr(run_report, "summary_path", None) if run_report else None,
    }
    return RunResult(
        albums_processed=stats["albums_processed"],
        tracks_processed=stats["tracks_processed"],
        output_path=getattr(operation_journal, "output_root", None),
        stats=stats,
    )


class Pipeline:
    def __init__(self):
        self.stages = default_stages()

    def run(self, context: Context) -> RunResult:
        return run_pipeline_context(context, stages=self.stages)


def _ensure_not_organized_input(path: str) -> None:
    input_path = Path(path).expanduser()
    if input_path.name.endswith("_organized"):
        raise ValueError(f"Input folder is already organized: {input_path}")
