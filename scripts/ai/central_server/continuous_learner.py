from __future__ import annotations
from datetime import datetime
from typing import List
from .central_contracts import LearningJob, ModelVersion, ModelStatus

class ContinuousLearner:
    def __init__(self, registry=None, threshold: int = 5000):
        self.registry = registry
        self.threshold = threshold
        self.jobs: list[LearningJob] = []

    def check_and_trigger(self, team_ids: List[str], total_count: int):
        if total_count < self.threshold:
            return None
        job = LearningJob(
            job_id=f"job-{len(self.jobs)+1}",
            trigger_reason="THRESHOLD_REACHED",
            team_ids=team_ids,
            data_digest16=f"digest-{total_count}",
            created_at=datetime.utcnow().isoformat(),
            status="CREATED",
            base_model_version="base-v1",
            eval_score=0.0,
        )
        self.jobs.append(job)
        return job

    def complete_job(self, job_id: str, eval_score: float = 0.91):
        job = next(j for j in self.jobs if j.job_id == job_id)
        job.status = "COMPLETED"
        job.eval_score = eval_score
        mv = ModelVersion(
            version_id=f"model-{len(self.jobs)}",
            model_path_digest=f"path-{job.job_id}",
            trained_at=datetime.utcnow().isoformat(),
            status=ModelStatus.PENDING.value,
            eval_score=eval_score,
            deploy_approved=0,
            source_job_id=job.job_id,
        )
        if eval_score >= 0.9:
            mv.status = ModelStatus.VALIDATED.value
        if self.registry:
            self.registry.register(mv)
        return mv

    def get_job_history(self):
        return self.jobs
