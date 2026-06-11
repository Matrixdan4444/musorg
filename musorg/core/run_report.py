import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class RunReport:
    def __init__(self, root_path: str, dry_run: bool = False, run_id: str | None = None):
        self.root_path = root_path
        self.dry_run = dry_run
        self.run_id = run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
        self.started_at = _now_iso()
        self.summary_path = os.path.join(root_path, ".musorg", "runs", f"{self.run_id}.json")
        self.changed_albums: list[dict] = []
        self.skipped_items: list[dict] = []
        self.duplicates: list[dict] = []
        self.unresolved_matches: list[dict] = []
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.stage_timings: list[dict] = []
        self.profile_metrics: dict[str, dict] = {}
        self._changed_album_keys: set[tuple] = set()
        self._changed_album_indexes: dict[tuple, int] = {}
        self._lock = threading.Lock()

    def note_log(self, event: dict) -> None:
        level = event.get("level")
        entry = {
            "stage": event.get("stage"),
            "message": event.get("message"),
            "at": _now_iso(),
        }
        if level == "warning":
            self.warnings.append(entry)
        elif level == "error":
            self.errors.append(entry)

    def record_skipped_item(self, path: str, reason: str, stage: str = "Metadata") -> None:
        self.skipped_items.append({
            "path": path,
            "reason": reason,
            "stage": stage,
        })

    def record_duplicate(
        self,
        category: str,
        source_path: str | None = None,
        requested_destination: str | None = None,
        resolved_destination: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.duplicates.append({
            "category": category,
            "source_path": source_path,
            "requested_destination": requested_destination,
            "resolved_destination": resolved_destination,
            "details": details or {},
        })

    def record_unresolved_match(
        self,
        artist: str,
        album: str,
        source_dir: str,
        track_count: int,
        preferred_release_type: str | None = None,
    ) -> None:
        self.unresolved_matches.append({
            "artist": artist,
            "album": album,
            "source_dir": source_dir,
            "track_count": track_count,
            "preferred_release_type": preferred_release_type,
            "services": ["musicbrainz", "deezer"],
        })

    def record_changed_album(
        self,
        key: tuple,
        before: dict,
        after: dict,
        track_count: int,
        *,
        album_id: str | None = None,
        metadata_intelligence: dict | None = None,
    ) -> None:
        normalized_before = {name: _normalize_text(value) for name, value in before.items()}
        normalized_after = {name: _normalize_text(value) for name, value in after.items()}
        if normalized_before == normalized_after or key in self._changed_album_keys:
            return

        self._changed_album_keys.add(key)
        self.changed_albums.append({
            "album_id": album_id,
            "source_dir": normalized_before.get("source_dir"),
            "track_count": track_count,
            "before": normalized_before,
            "after": normalized_after,
            "output_dir": None,
            "metadata_intelligence": metadata_intelligence,
        })
        self._changed_album_indexes[key] = len(self.changed_albums) - 1

    def update_changed_album(
        self,
        key: tuple,
        *,
        output_dir: str | None = None,
        metadata_intelligence: dict | None = None,
    ) -> None:
        index = self._changed_album_indexes.get(key)
        if index is None:
            return
        entry = self.changed_albums[index]
        if output_dir:
            entry["output_dir"] = _normalize_text(output_dir)
        if metadata_intelligence is not None:
            entry["metadata_intelligence"] = metadata_intelligence

    def record_timing(self, name: str, duration_seconds: float, count: int = 1) -> None:
        with self._lock:
            metric = self.profile_metrics.setdefault(name, {
                "count": 0,
                "total_seconds": 0.0,
                "min_seconds": None,
                "max_seconds": 0.0,
            })
            metric["count"] += count
            metric["total_seconds"] += duration_seconds
            metric["min_seconds"] = (
                duration_seconds
                if metric["min_seconds"] is None
                else min(metric["min_seconds"], duration_seconds)
            )
            metric["max_seconds"] = max(metric["max_seconds"], duration_seconds)

    def record_count(self, name: str, count: int = 1) -> None:
        self.record_timing(name, 0.0, count=count)

    def record_stage_timing(self, stage: str, duration_seconds: float) -> None:
        with self._lock:
            self.stage_timings.append({
                "stage": stage,
                "seconds": duration_seconds,
            })
        self.record_timing(f"stage:{stage}", duration_seconds)

    @contextmanager
    def measure(self, name: str, *, stage: bool = False):
        started_at = perf_counter()
        try:
            yield
        finally:
            duration_seconds = perf_counter() - started_at
            if stage:
                self.record_stage_timing(name, duration_seconds)
            else:
                self.record_timing(name, duration_seconds)

    def profiling_summary(self) -> dict:
        metrics = {}
        for name, metric in self.profile_metrics.items():
            count = metric["count"] or 0
            total_seconds = metric["total_seconds"]
            metrics[name] = {
                "count": count,
                "total_seconds": round(total_seconds, 6),
                "avg_seconds": round(total_seconds / count, 6) if count else 0.0,
                "min_seconds": round(metric["min_seconds"] or 0.0, 6),
                "max_seconds": round(metric["max_seconds"], 6),
            }

        return {
            "stage_timings": [
                {
                    "stage": item["stage"],
                    "seconds": round(item["seconds"], 6),
                }
                for item in self.stage_timings
            ],
            "metrics": metrics,
        }

    def finalize(self, context) -> str:
        os.makedirs(os.path.dirname(self.summary_path), exist_ok=True)
        operation_journal = getattr(context, "operation_journal", None)
        profiling = self.profiling_summary()
        summary = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": _now_iso(),
            "root_path": self.root_path,
            "dry_run": self.dry_run,
            "output_root": getattr(operation_journal, "output_root", None),
            "manifest_path": getattr(operation_journal, "manifest_path", None),
            "counts": {
                "files_scanned": len(getattr(context, "files", [])),
                "tracks_ready": len(getattr(context, "tracks", [])),
                "albums_grouped": len(getattr(context, "albums", {}) or {}),
                "changed_albums": len(self.changed_albums),
                "skipped_items": len(self.skipped_items),
                "duplicates": len(self.duplicates),
                "unresolved_matches": len(self.unresolved_matches),
                "warnings": len(self.warnings),
                "errors": len(self.errors),
            },
            "profiling": profiling,
            "changed_albums": self.changed_albums,
            "skipped_items": self.skipped_items,
            "duplicates": self.duplicates,
            "unresolved_matches": self.unresolved_matches,
            "warnings": self.warnings,
            "errors": self.errors,
        }
        with open(self.summary_path, "w", encoding="utf-8") as summary_file:
            json.dump(summary, summary_file, ensure_ascii=False, indent=2)
        return self.summary_path
