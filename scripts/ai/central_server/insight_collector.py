from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict
from typing import Optional
from .central_contracts import TeamInsight, CollectResult

class InsightCollector:
    def __init__(self, learner=None, threshold: int = 5000):
        self.learner = learner
        self.threshold = threshold
        if self.learner is not None:
            self.learner.threshold = threshold
        self.by_team = defaultdict(int)
        self.last_ts = {}
        self.total_count = 0

    def receive(self, insight: TeamInsight) -> CollectResult:
        if getattr(insight, "raw_text", None):
            return CollectResult(ok=False, team_id=insight.team_id, count=self.by_team[insight.team_id], data_digest16=insight.data_digest16, error_code="RAW_BLOCKED")
        self.by_team[insight.team_id] += insight.record_count
        self.total_count += insight.record_count
        self.last_ts[insight.team_id] = insight.timestamp
        if self.learner and self.total_count >= self.threshold:
            self.learner.check_and_trigger(list(self.by_team.keys()), self.total_count)
        return CollectResult(ok=True, team_id=insight.team_id, count=self.by_team[insight.team_id], data_digest16=insight.data_digest16)

    def get_stats(self):
        return {"team_counts": dict(self.by_team), "last_ts": dict(self.last_ts), "total_count": self.total_count}
