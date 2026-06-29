"""수정2 — 학습 자동연결기 (learning auto connector).

usage_log 저장 직후, `learning_candidate_gate` 를 **안전하게 래핑**해서 학습 후보를
learning_event 로 연결한다. 핵심 원칙(절대 준수):

- 게이트 우회 0: event 생성은 반드시 `create_learning_event_result()` 를 통과한다.
  DLP/expires/label-drift/스키마 가드는 그대로 적용된다(여기서 재구현·완화하지 않는다).
- event 위조 0: ApprovedRefBundle 또는 policy_task_envelope 가 없으면 event 를 만들지
  않고 drop_reason(APPROVED_REF_OR_POLICY_ENVELOPE_MISSING) 만 남긴다.
- usage_log 자체는 학습 데이터가 아니다. 후보 8조건(`select_learning_candidates`)을
  통과하지 못하면 SOURCE_USAGE_LOG_NOT_ELIGIBLE 로 drop 하고 게이트를 호출하지 않는다.

이 모듈은 모델을 학습시키지 않으며, 원문/external 전송을 만들지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .learning_candidate_gate import (
    ApprovedRefBundle,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
)
from .learning_event_store import LearningEventStore

# 승인 컨텍스트(approved_ref/policy envelope) 부재 시의 안전 drop 사유.
DROP_NOT_ELIGIBLE = "SOURCE_USAGE_LOG_NOT_ELIGIBLE"
DROP_APPROVED_REF_OR_ENVELOPE_MISSING = "APPROVED_REF_OR_POLICY_ENVELOPE_MISSING"


@dataclass(frozen=True)
class ConnectorResult:
    """학습 자동연결 1회의 결과(원문 없음, 감사 가능한 요약)."""

    event: dict[str, Any] | None
    drop_reason: str | None
    learning_event_created: bool


def run_learning_auto_connection(
    usage_log: dict[str, Any],
    *,
    approved_ref_bundle: ApprovedRefBundle | None = None,
    policy_task_envelope: dict[str, Any] | None = None,
    policy_approval: dict[str, str] | None = None,
    dlp_result: dict[str, bool] | None = None,
    event_store: LearningEventStore | None = None,
    now: datetime | None = None,
) -> ConnectorResult:
    """usage_log 1건을 학습 게이트로 안전 연결한다.

    절차:
      1) `select_learning_candidates([usage_log])` 로 후보 8조건 + 스키마 검증.
         후보가 아니면 게이트를 호출하지 않고 DROP_NOT_ELIGIBLE.
      2) approved_ref_bundle 또는 policy_task_envelope 가 없으면 위조하지 않고
         DROP_APPROVED_REF_OR_ENVELOPE_MISSING.
      3) 둘 다 있으면 `build_learning_gate_input` → `create_learning_event_result`.
         게이트가 event 를 만들면(모든 DLP/expires/drift 통과) 그대로 반환하고,
         event_store 가 주어졌으면 영속한다. 게이트가 drop 하면 그 drop_reason 전달.
    """
    candidates = select_learning_candidates([usage_log])
    if not candidates:
        return ConnectorResult(event=None, drop_reason=DROP_NOT_ELIGIBLE, learning_event_created=False)

    if approved_ref_bundle is None or policy_task_envelope is None:
        return ConnectorResult(
            event=None,
            drop_reason=DROP_APPROVED_REF_OR_ENVELOPE_MISSING,
            learning_event_created=False,
        )

    gate_input = build_learning_gate_input(
        candidates[0],
        approved_ref_bundle,
        policy_task_envelope,
        policy_approval=policy_approval,
        dlp_result=dlp_result,
    )
    result = create_learning_event_result(gate_input, now=now)
    if result.event is None:
        return ConnectorResult(event=None, drop_reason=result.drop_reason, learning_event_created=False)

    if event_store is not None:
        event_store.append(result.event)
    return ConnectorResult(event=result.event, drop_reason=None, learning_event_created=True)
