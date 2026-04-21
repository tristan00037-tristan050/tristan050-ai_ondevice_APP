from __future__ import annotations
import json, os, shutil, threading
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = "central_server_v3"

class PersistenceManager:
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def concurrent_guard(self):
        return self._lock

    def atomic_write_json(self, path: Path, data: Dict[str, Any]) -> bool:
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = dict(data)
        payload.setdefault("schema_version", SCHEMA_VERSION)
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
            return True
        except Exception:
            if tmp.exists():
                tmp.unlink()
            return False

    def rotate_backup(self, path: Path) -> None:
        path = Path(path)
        bak = Path(str(path) + ".bak")
        if path.exists():
            shutil.copy2(path, bak)

    def detect_corruption(self, path: Path, required_fields: Optional[list[str]]=None) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return True
        if data.get("schema_version") != SCHEMA_VERSION:
            return True
        if required_fields:
            for field in required_fields:
                if field not in data:
                    return True
        return False

    def load_with_fallback(self, path: Path, required_fields: Optional[list[str]]=None, empty_state: Optional[dict]=None) -> dict:
        path = Path(path)
        bak = Path(str(path) + ".bak")
        empty = dict(empty_state or {})
        empty.setdefault("schema_version", SCHEMA_VERSION)
        candidates = [path, bak]
        for candidate in candidates:
            if not candidate.exists():
                continue
            if self.detect_corruption(candidate, required_fields):
                continue
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
        return empty

    def save_state(self, filename: str, data: dict) -> bool:
        with self.concurrent_guard():
            path = self.state_dir / filename
            ok = self.atomic_write_json(path, data)
            if ok:
                self.rotate_backup(path)
            return ok

    def load_state(self, filename: str, required_fields: Optional[list[str]]=None, empty_state: Optional[dict]=None) -> dict:
        with self.concurrent_guard():
            return self.load_with_fallback(self.state_dir / filename, required_fields, empty_state)

    def ensure_consistent_bundle(self) -> bool:
        required = [
            "enterprise_kb_snapshot.json",
            "learning_jobs.json",
            "model_registry.json",
            "central_state.json",
        ]
        return all((self.state_dir / name).exists() for name in required)
