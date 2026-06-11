import json
import os
import shutil
import uuid
from datetime import datetime, timezone


class OperationJournal:
    def __init__(self, output_root: str, dry_run: bool = False, run_report=None):
        self.output_root = output_root
        self.dry_run = dry_run
        self.run_report = run_report
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self.operations: list[dict] = []
        self._backup_index = 0
        self._manifest_dir = os.path.join(output_root, ".musorg")
        self._backup_root = os.path.join(self._manifest_dir, "backups", self.run_id)
        self.manifest_path = os.path.join(self._manifest_dir, "manifests", f"{self.run_id}.json")

    def record(self, action: str, **details) -> None:
        self.operations.append({
            "action": action,
            "details": details,
        })

    def backup_path(self, original_path: str) -> str:
        self._backup_index += 1
        basename = os.path.basename(original_path.rstrip(os.sep)) or "item"
        return os.path.join(self._backup_root, f"{self._backup_index:04d}_{basename}")

    def move_to_backup(self, original_path: str) -> str:
        backup_path = self.backup_path(original_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.move(original_path, backup_path)
        return backup_path

    def finalize(self) -> None:
        if self.dry_run:
            return

        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        manifest = {
            "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "output_root": self.output_root,
            "backup_root": self._backup_root,
            "operations": self.operations,
        }
        with open(self.manifest_path, "w", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
