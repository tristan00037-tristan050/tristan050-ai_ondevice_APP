from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from .team_contracts import FinetuneJob, digest16, safe_jsonable, utcnow_iso
from .team_persistence import TeamPersistence


class FinetuneTrigger:
    def __init__(self, threshold: int = 1000, persistence: TeamPersistence | None = None) -> None:
        self.threshold = threshold
        self.persistence = persistence
        self.team_counts: Dict[str, int] = {}
        self.jobs_by_team: Dict[str, List[FinetuneJob]] = {}
        self.current_versions: Dict[str, str] = {}
        self.central_dispatches: List[Dict[str, Any]] = []
        if persistence is not None:
            self._restore(persistence.load_state().get("finetune_jobs", {}))

    def _restore(self, raw: Dict[str, Any]) -> None:
        self.team_counts = raw.get("team_counts", {}) or {}
        self.current_versions = raw.get("current_versions", {}) or {}
        self.central_dispatches = raw.get("central_dispatches", []) or []
        self.jobs_by_team = {
            team_id: [FinetuneJob(**job) for job in jobs]
            for team_id, jobs in (raw.get("jobs_by_team", {}) or {}).items()
        }

    def _persist(self) -> None:
        if self.persistence is None:
            return
        state = self.persistence.load_state()
        snapshot = {
            "team_counts": self.team_counts,
            "current_versions": self.current_versions,
            "jobs_by_team": {team: [safe_jsonable(job) for job in jobs] for team, jobs in self.jobs_by_team.items()},
            "central_dispatches": self.central_dispatches,
        }
        self.persistence.save_state(
            kb_snapshot=state.get("kb_snapshot", {}),
            finetune_jobs=snapshot,
            coverage_stats=state.get("coverage_stats", {}),
            server_state=state.get("server_state", {}),
        )

    def record_data(self, team_id: str, count: int = 1) -> int:
        self.team_counts[team_id] = self.team_counts.get(team_id, 0) + count
        self._persist()
        return self.team_counts[team_id]

    def check_and_trigger(self, team_id: str, coverage_delta: int = 0) -> FinetuneJob | None:
        count = self.team_counts.get(team_id, 0)
        if count < self.threshold:
            return None
        # 이미 트리거된 팀은 threshold 배수 단위로만 재트리거
        triggered = len(self.jobs_by_team.get(team_id, []))
        if triggered > 0 and count < self.threshold * (triggered + 1):
            return None
        next_version = f"team-model-v{len(self.jobs_by_team.get(team_id, [])) + 1}"
        job = FinetuneJob(
            job_id=digest16({"team": team_id, "count": count, "version": next_version, "ts": utcnow_iso()}),
            team_id=team_id,
            trigger_reason="DATA_THRESHOLD_REACHED",
            data_count=count,
            created_at=utcnow_iso(),
            status="QUEUED",
            model_version=next_version,
        )
        self.jobs_by_team.setdefault(team_id, []).append(job)
        self.central_dispatches.append({
            "team_id": team_id,
            "data_count": count,
            "trigger_reason": job.trigger_reason,
            "model_version": job.model_version,
            "coverage_delta": coverage_delta,
            "meta_only": True,
        })
        self._persist()
        return job

    def complete_job(self, job_id: str) -> bool:
        for team_id, jobs in self.jobs_by_team.items():
            for idx, job in enumerate(jobs):
                if job.job_id == job_id:
                    jobs[idx] = FinetuneJob(**{**asdict(job), "status": "COMPLETED"})
                    self.current_versions[team_id] = job.model_version
                    self._persist()
                    return True
        return False

    def current_model_version(self, team_id: str) -> str:
        return self.current_versions.get(team_id, "team-model-v0")

    def get_job_history(self, team_id: str | None = None) -> List[Dict[str, Any]]:
        if team_id is None:
            return [asdict(job) for jobs in self.jobs_by_team.values() for job in jobs]
        return [asdict(job) for job in self.jobs_by_team.get(team_id, [])]

    def get_central_dispatches(self) -> List[Dict[str, Any]]:
        return list(self.central_dispatches)

    def no_raw_in_queue(self) -> bool:
        return all(dispatch.get("meta_only") is True for dispatch in self.central_dispatches)
