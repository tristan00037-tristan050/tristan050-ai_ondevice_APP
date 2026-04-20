from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict
import json
import os
import shutil
import tempfile
import threading


class PersistenceError(RuntimeError):
    pass


class TeamPersistence:
    REQUIRED_TOP_LEVEL = {
        "kb_snapshot": dict,
        "finetune_jobs": dict,
        "coverage_stats": dict,
        "server_state": dict,
    }

    def __init__(self, state_dir: str = "tmp/team_state") -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.kb_path = self.state_dir / "kb_snapshot.json"
        self.jobs_path = self.state_dir / "finetune_jobs.json"
        self.coverage_path = self.state_dir / "coverage_stats.json"
        self.state_path = self.state_dir / "team_server_state.json"
        self._write_lock = threading.Lock()

    @contextmanager
    def concurrent_guard(self):
        self._write_lock.acquire()
        try:
            yield
        finally:
            self._write_lock.release()

    def atomic_write_json(self, path: str | Path, data: Any) -> bool:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            return True
        except Exception as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            finally:
                raise PersistenceError(str(exc)) from exc

    def rotate_backup(self, path: str | Path) -> Path | None:
        path = Path(path)
        if not path.exists():
            return None
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        return backup

    def detect_corruption(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return True
        if path.name == "kb_snapshot.json":
            return not isinstance(payload, dict)
        if path.name == "finetune_jobs.json":
            return not isinstance(payload, dict)
        if path.name == "coverage_stats.json":
            return not isinstance(payload, dict)
        if path.name == "team_server_state.json":
            return not isinstance(payload, dict)
        return False

    def _restore_from_backup(self, path: Path) -> Any:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            return None
        try:
            payload = json.loads(backup.read_text(encoding="utf-8"))
            self.atomic_write_json(path, payload)
            return payload
        except Exception:
            return None

    def load_with_fallback(self, path: str | Path, default: Any) -> Any:
        path = Path(path)
        if not path.exists():
            restored = self._restore_from_backup(path)
            return default if restored is None else restored
        try:
            if self.detect_corruption(path):
                restored = self._restore_from_backup(path)
                return default if restored is None else restored
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            restored = self._restore_from_backup(path)
            return default if restored is None else restored

    def save_state(self, *, kb_snapshot: Dict[str, Any], finetune_jobs: Dict[str, Any], coverage_stats: Dict[str, Any], server_state: Dict[str, Any]) -> None:
        with self.concurrent_guard():
            for path in (self.kb_path, self.jobs_path, self.coverage_path, self.state_path):
                self.rotate_backup(path)
            self.atomic_write_json(self.kb_path, kb_snapshot)
            self.rotate_backup(self.kb_path)
            self.atomic_write_json(self.jobs_path, finetune_jobs)
            self.rotate_backup(self.jobs_path)
            self.atomic_write_json(self.coverage_path, coverage_stats)
            self.rotate_backup(self.coverage_path)
            self.atomic_write_json(self.state_path, server_state)
            self.rotate_backup(self.state_path)

    def load_state(self) -> Dict[str, Any]:
        state = {
            "kb_snapshot": self.load_with_fallback(self.kb_path, {}),
            "finetune_jobs": self.load_with_fallback(self.jobs_path, {}),
            "coverage_stats": self.load_with_fallback(self.coverage_path, {}),
            "server_state": self.load_with_fallback(self.state_path, {}),
        }
        if not all(isinstance(state[k], self.REQUIRED_TOP_LEVEL[k]) for k in self.REQUIRED_TOP_LEVEL):
            raise PersistenceError("schema_mismatch")
        return state
