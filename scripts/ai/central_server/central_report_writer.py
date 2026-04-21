from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
from .central_persistence import PersistenceManager

RAW_MARKERS = {"prompt","output","content","audio","payload","raw"}

class CentralReportWriter:
    def __init__(self, persistence: PersistenceManager):
        self.persistence = persistence

    def write_report(self, path: Path, data: Dict[str, Any]) -> bool:
        blob = json.dumps(data, ensure_ascii=False).lower()
        if any(x in blob and "digest" not in blob for x in RAW_MARKERS):
            raise ValueError("raw content forbidden")
        return self.persistence.atomic_write_json(Path(path), data)
