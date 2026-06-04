from __future__ import annotations

import json

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope
from butler_pc_core.cards.box3.real_eval import evaluate_fixed_eval_cases
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerConfig


def main() -> int:
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="report",
    )
    cfg = Box3RealRunnerConfig(base_model_sha256_full="a" * 64, allow_test_runner=True, readonly_required=False)
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(),
    )
    eval_result = evaluate_fixed_eval_cases()
    audit = verdict.build_audit_record().to_dict()
    result = {
        "SELF_CHECK_PASS": verdict.status == "REAL_CANDIDATE" and eval_result.passed and "draft_text" not in audit,
        "status": verdict.status,
        "real_claim_allowed": verdict.real_claim_allowed,
        "fail_class": verdict.fail_class,
        "fixed_eval_case_count": eval_result.case_count,
        "fixed_eval_failed_count": eval_result.failed_count,
        "audit_digest_only": "draft_text" not in audit,
        "external_send_zero": verdict.external_send_zero,
        "raw_saved_zero": verdict.raw_saved_zero,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["SELF_CHECK_PASS"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
