from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    model_size_mb: float
    reload_cost_ms: float
    last_used_at: datetime
    active_session_count: int = 0
    pinned_until: Optional[datetime] = None
    memory_pressure_level: int = 0
    thermal_pressure_level: int = 0


class WeightedLRU:
    def __init__(self, entries: list[ModelEntry] | None = None) -> None:
        self.entries = list(entries or [])
        self.recency_weight = 1.0
        self.size_weight = 0.5
        self.reload_weight = 0.001
        self.active_weight = 100
        self.pinned_weight = 1

    def evict_score(self, entry: ModelEntry, now: datetime) -> float:
        age_minutes = (now - entry.last_used_at).total_seconds() / 60
        pressure_multiplier = 1 + ((entry.memory_pressure_level + entry.thermal_pressure_level) / 20)
        return (
            self.recency_weight * age_minutes
            + self.size_weight * entry.model_size_mb * pressure_multiplier
            - self.reload_weight * entry.reload_cost_ms
            - self.active_weight * entry.active_session_count * 1000
            - self.pinned_weight * (1000 if entry.pinned_until and entry.pinned_until > now else 0)
        )

    def choose_evict_candidate(self, now: datetime, force: bool = False) -> Optional[ModelEntry]:
        if force:
            candidates = self.entries
        else:
            candidates = []
            for entry in self.entries:
                pinned = entry.pinned_until is not None and entry.pinned_until > now
                if entry.active_session_count == 0 and not pinned:
                    candidates.append(entry)
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda entry: (
                -self.evict_score(entry, now),
                entry.last_used_at,
                -entry.model_size_mb,
                entry.model_id,
            ),
        )[0]
