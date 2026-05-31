"""Digest-only learning_event store and source link index for PR-E."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .dlp_guard import assert_no_raw_or_secret_material
from .learning_event_schema import validate_learning_event


class LearningEventStore:
    def __init__(self, jsonl_path: Path | None = None) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.learning_event_link_index: dict[str, str] = {}
        self.jsonl_path = jsonl_path

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        validate_learning_event(event)
        assert_no_raw_or_secret_material(event)
        stored = copy.deepcopy(event)
        event_id = stored["learning_event_id"]
        source_id = stored["source_usage_log_id"]
        self.events[event_id] = stored
        self.learning_event_link_index[source_id] = event_id
        if self.jsonl_path is not None:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(stored, ensure_ascii=False, sort_keys=True) + "\n")
        return copy.deepcopy(stored)

    def linked_event_id(self, source_usage_log_id: str) -> str | None:
        return self.learning_event_link_index.get(source_usage_log_id)

    def get(self, learning_event_id: str) -> dict[str, Any] | None:
        event = self.events.get(learning_event_id)
        return copy.deepcopy(event) if event is not None else None
