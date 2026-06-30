from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material

from .candidate_gate import gate_candidate
from .contracts import sha256_text, validate_candidate_dict


class RulePatchQueueError(ValueError):
    pass


class RulePatchQueue:
    """Device-local digest-only queue for human-reviewed Box5 rule candidates."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, candidate: dict[str, Any]) -> dict[str, Any]:
        decision = gate_candidate(candidate)
        if not decision.accepted or decision.candidate is None:
            raise RulePatchQueueError(decision.drop_reason or "CANDIDATE_REJECTED")

        entry = copy.deepcopy(decision.candidate)
        try:
            assert_no_raw_or_secret_material(entry)
        except ValueError as exc:
            raise RulePatchQueueError("RAW_OR_SECRET_MATERIAL_FORBIDDEN") from exc

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
        return copy.deepcopy(entry)

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RulePatchQueueError(f"QUEUE_JSON_INVALID:{line_no}") from exc
            try:
                entries.append(validate_candidate_dict(entry))
            except ValueError as exc:
                raise RulePatchQueueError(f"QUEUE_ENTRY_INVALID:{line_no}") from exc
        return entries

    def digests(self) -> list[str]:
        return [sha256_text(json.dumps(entry, ensure_ascii=False, sort_keys=True)) for entry in self.load()]


def read_queue(path: str | Path) -> list[dict[str, Any]]:
    return RulePatchQueue(path).load()


def append_candidates(path: str | Path, candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = RulePatchQueue(path)
    return [queue.append(candidate) for candidate in candidates]
