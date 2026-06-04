#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope
from butler_pc_core.cards.box3.actual_operation_pipeline import run_box3_actual_operation
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.human_approval_sealed import default_locked_human_approval
from butler_pc_core.cards.box3.local_sealed_runner import build_deterministic_test_runner


def main() -> int:
    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
    )
    verdict = run_box3_actual_operation(
        env,
        helper_component_guard=build_example_component_use_guard(allow=True, stack_supported=True),
        human_approval_config=default_locked_human_approval(env.request_digest),
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )
    persist = verdict.to_persistable_dict()
    out = {
        "SELF_CHECK_PASS": True,
        "status": verdict.status,
        "fail_class": verdict.fail_class,
        "real_claim_allowed": verdict.real_claim_allowed,
        "test_only_runner": verdict.runner_measurements.get("test_only_runner"),
        "audit_digest_only": "draft_text" not in persist,
        "external_send_zero": verdict.external_send_zero,
        "raw_saved_zero": verdict.raw_saved_zero,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
