from __future__ import annotations

import json
from pathlib import Path

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope, sha256_text
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerConfig


def main() -> int:
    tmp_model = Path("/tmp/butler_box3_self_check_model.gguf")
    tmp_model.write_text("self-check-model", encoding="utf-8")
    import os
    os.environ["BUTLER_BOX3_BASE_MODEL_PATH"] = str(tmp_model)
    cfg = Box3RealRunnerConfig(
        runner_id="self-check-test-runner",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=sha256_text("self-check-model").split(":", 1)[1],
        loader_name="test_in_memory",
        allow_test_runner=True,
        readonly_required=False,
    )
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_docs=["참고 문서에는 납품 일정이 2026-06-10으로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="report",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(),
    )
    report = {
        "SELF_CHECK_PASS": verdict.status == "REAL_CANDIDATE" and verdict.real_claim_allowed is False,
        "status": verdict.status,
        "fail_class": verdict.fail_class,
        "real_claim_allowed": verdict.real_claim_allowed,
        "unsupported_claim_rate": verdict.metrics.unsupported_claim_rate,
        "citation_accuracy": verdict.metrics.citation_accuracy,
        "audit_digest_only": True,
        "external_send_zero": verdict.external_send_zero,
        "raw_saved_zero": verdict.raw_saved_zero,
        "note": "test runner is explicitly test-only; local real runner smoke requires actual base model path and SHA on target machine.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["SELF_CHECK_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
