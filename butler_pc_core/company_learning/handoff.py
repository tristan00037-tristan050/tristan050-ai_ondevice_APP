from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jsonschema.exceptions import ValidationError

from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
from butler_pc_core.connect_loop.learning_candidate_gate import APPROVED_REF_RE
from butler_pc_core.connect_loop.learning_event_schema import validate_learning_event
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore

from .job_store import CompanyLearningJob
from .understanding import build_understanding


@dataclass(frozen=True)
class CompanyLearningHandoffResult:
    event: dict[str, Any] | None
    fail_class: str | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_dlp_result(result: dict[str, Any]) -> dict[str, bool]:
    return {
        "passed": result.get("passed") is True,
        "pii_detected": result.get("pii_detected") is True,
        "secret_detected": result.get("secret_detected") is True,
        "policy_violation": result.get("policy_violation") is True,
    }


def create_company_learning_candidate(
    job: CompanyLearningJob,
    *,
    store: LearningEventStore,
    llm_status: str = "not_used",
    now: datetime | None = None,
) -> CompanyLearningHandoffResult:
    current = now or _now()
    understanding = build_understanding(job, llm_status=llm_status)
    if understanding.get("needs_review") is True:
        return CompanyLearningHandoffResult(event=None, fail_class="UNDERSTANDING_NEEDS_REVIEW")

    summary = str(understanding.get("summary_runtime_text") or "")
    dlp_result = _normalize_dlp_result(scan_runtime_text(summary))
    if not (
        dlp_result["passed"] is True
        and dlp_result["pii_detected"] is False
        and dlp_result["secret_detected"] is False
        and dlp_result["policy_violation"] is False
    ):
        return CompanyLearningHandoffResult(event=None, fail_class="HANDOFF_DLP_FAILED")

    suffix = job.ingest_digest.split(":", 1)[1][:32]
    approved_text_ref = f"vault://company-learning/{suffix}"
    if not APPROVED_REF_RE.fullmatch(approved_text_ref):
        return CompanyLearningHandoffResult(event=None, fail_class="APPROVED_TEXT_REF_FORBIDDEN")

    event = {
        "learning_event_id": "lev-" + uuid.uuid4().hex,
        "source_usage_log_id": "folder-ingest-" + job.ingest_digest.split(":", 1)[1][:24],
        "created_at": _rfc3339(current),
        "status": "CANDIDATE",
        "tenant_scope": "device",
        "learning_type": "memory_search",
        "raw_input_saved": False,
        "raw_output_saved": False,
        "approved_text_ref": approved_text_ref,
        "approved_text_digest": sha256_text(summary),
        "sanitized_summary_digest": sha256_text(summary),
        "sanitized_summary_saved": False,
        "label": {"intent_label": "memory_search", "target_box_id": "helper1", "quality": "fair"},
        "policy_approval": {
            "decision": "needs_review",
            "approver_role": "manager",
            "reason_code": "FOLDER_UNDERSTANDING_CANDIDATE",
        },
        "dlp_result": dlp_result,
        "retention_days": 30,
        "expires_at": _rfc3339(current + timedelta(days=30)),
        "verified_for_training": False,
        "schema_version": "learning_event.v1",
    }

    try:
        validate_learning_event(event)
        stored = store.append(event)
    except ValidationError:
        return CompanyLearningHandoffResult(event=None, fail_class="LEARNING_EVENT_SCHEMA_INVALID")
    except ValueError as exc:
        if str(exc) == "DUPLICATE_SOURCE_USAGE_LOG":
            return CompanyLearningHandoffResult(event=None, fail_class="LEARNING_EVENT_ALREADY_EXISTS")
        return CompanyLearningHandoffResult(event=None, fail_class="LEARNING_EVENT_STORE_FAILED")
    except Exception:
        return CompanyLearningHandoffResult(event=None, fail_class="LEARNING_EVENT_STORE_FAILED")

    return CompanyLearningHandoffResult(event=copy.deepcopy(stored), fail_class=None)
