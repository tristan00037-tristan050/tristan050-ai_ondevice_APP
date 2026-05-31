"""Digest-only learning_event store and source link index for PR-E."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import RLock
from typing import Any

from .dlp_guard import assert_no_raw_or_secret_material
from .learning_event_schema import validate_learning_event


class LearningEventStore:
    def __init__(self, jsonl_path: Path | None = None) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.learning_event_link_index: dict[str, str] = {}
        self.jsonl_path = jsonl_path
        self._lock = RLock()
        if self.jsonl_path is not None and self.jsonl_path.exists():
            self._hydrate_from_jsonl()

    def _index_stored_event(self, stored: dict[str, Any]) -> None:
        event_id = stored["learning_event_id"]
        source_id = stored["source_usage_log_id"]
        if event_id in self.events:
            raise ValueError("DUPLICATE_LEARNING_EVENT_ID")
        if source_id in self.learning_event_link_index:
            raise ValueError("DUPLICATE_SOURCE_USAGE_LOG")
        self.events[event_id] = stored
        self.learning_event_link_index[source_id] = event_id

    def _hydrate_from_jsonl(self) -> None:
        assert self.jsonl_path is not None
        with self.jsonl_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                stored = json.loads(line)
                validate_learning_event(stored)
                assert_no_raw_or_secret_material(stored)
                self._index_stored_event(stored)

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            validate_learning_event(event)
            assert_no_raw_or_secret_material(event)
            stored = copy.deepcopy(event)
            self._index_stored_event(stored)
            if self.jsonl_path is not None:
                try:
                    self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.jsonl_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(stored, ensure_ascii=False, sort_keys=True) + "\n")
                except Exception:
                    self.events.pop(stored["learning_event_id"], None)
                    self.learning_event_link_index.pop(stored["source_usage_log_id"], None)
                    raise
            return copy.deepcopy(stored)

    def linked_event_id(self, source_usage_log_id: str) -> str | None:
        return self.learning_event_link_index.get(source_usage_log_id)

    def get(self, learning_event_id: str) -> dict[str, Any] | None:
        event = self.events.get(learning_event_id)
        return copy.deepcopy(event) if event is not None else None
