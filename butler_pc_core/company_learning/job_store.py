from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from butler_pc_core.retrieval.chunkers import Chunk
from butler_pc_core.retrieval.pipeline import PersonalPackIndex

from .folder_ingest import IngestResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class CompanyLearningJob:
    job_id: str
    status: str
    folder_digest: str
    ingest_digest: str
    counters: dict[str, Any]
    started_at: datetime
    updated_at: datetime
    expires_at: datetime
    chunks: list[Chunk] = field(repr=False)
    index: PersonalPackIndex = field(repr=False)
    understanding: dict[str, Any] | None = None
    error_code: str | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def public_status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "schema_version": "company_learning.status.v1",
                "job_id": self.job_id,
                "status": self.status,
                "folder_digest": self.folder_digest,
                "ingest_digest": self.ingest_digest,
                "progress": 100 if self.status == "COMPLETED" else 0,
                "counters": copy.deepcopy(self.counters),
                "started_at": _rfc3339(self.started_at),
                "updated_at": _rfc3339(self.updated_at),
                "error_code": self.error_code,
                "raw_text_logged": False,
                "external_send_zero": True,
            }


class CompanyLearningJobStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._jobs: dict[str, CompanyLearningJob] = {}
        self._folder_to_job: dict[str, str] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.RLock()

    def create_completed(self, result: IngestResult) -> CompanyLearningJob:
        current = _now()
        with self._lock:
            self.prune_expired(now=current)
            existing_id = self._folder_to_job.get(result.folder_digest)
            if existing_id:
                existing = self._jobs.get(existing_id)
                if existing is not None and existing.ingest_digest == result.ingest_digest:
                    return existing
                self._jobs.pop(existing_id, None)

            job = CompanyLearningJob(
                job_id="clj-" + uuid.uuid4().hex,
                status="COMPLETED",
                folder_digest=result.folder_digest,
                ingest_digest=result.ingest_digest,
                counters=result.counters.to_dict(),
                started_at=current,
                updated_at=current,
                expires_at=current + self._ttl,
                chunks=list(result.chunks),
                index=result.index,
            )
            self._jobs[job.job_id] = job
            self._folder_to_job[job.folder_digest] = job.job_id
            return job

    def get(self, job_id: str) -> CompanyLearningJob | None:
        with self._lock:
            self.prune_expired()
            return self._jobs.get(job_id)

    def prune_expired(self, *, now: datetime | None = None) -> None:
        current = now or _now()
        expired = [job_id for job_id, job in self._jobs.items() if job.expires_at <= current]
        for job_id in expired:
            job = self._jobs.pop(job_id)
            self._folder_to_job.pop(job.folder_digest, None)
