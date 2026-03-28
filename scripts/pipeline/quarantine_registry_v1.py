from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class QuarantineRegistry:
    def __init__(self, output_dir: str):
        self.path = Path(output_dir) / "quarantine_registry.jsonl"
        self._entries: list[dict] = []

    def add(self, sha256: str, source_path: str, reason: str, domain: str) -> None:
        self._entries.append(
            {
                "sha256": sha256,
                "source_path": source_path,
                "reason": reason,
                "domain": domain,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def save(self) -> None:
        if not self._entries:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def count(self) -> int:
        return len(self._entries)

    def as_list(self) -> list[dict]:
        return list(self._entries)
