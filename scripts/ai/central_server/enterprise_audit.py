from __future__ import annotations
import json, hashlib
from pathlib import Path
from typing import Dict, Any

RAW_MARKERS = {"prompt","output","content","audio","text","payload","raw"}

class EnterpriseAudit:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen = set()

    def _contains_raw(self, data: Dict[str, Any]) -> bool:
        blob = json.dumps(data, ensure_ascii=False).lower()
        return any(marker in blob and "digest" not in blob for marker in RAW_MARKERS)

    def append(self, entry: Dict[str, Any]) -> bool:
        if self._contains_raw(entry):
            return False
        digest_key = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest_key in self._seen:
            return True
        self._seen.add(digest_key)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
