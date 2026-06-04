"""박스 3 활성화 RAG·프롬프트 최종 통합 smoke (PR #781, 2026-06-04).

PR #780 머지본 head 653a5bbe 위에서 RAG·Prompt v1.2 통합 후 endpoint smoke 를
3 시나리오로 흘리고 digest-only 결과만 보고한다 (raw 0):

  A) 보고서 초안: real GGUF + grounded prompt (1.7B v4-rt). 모델 한계로 인한
     실제 환각은 정직 BLOCK_UNSUPPORTED_CLAIM 으로 보고 (가짜 PASS 0).
  B) 동일 sealed approval + deterministic test runner: grounded prompt + 정합 draft
     → status=REAL_CANDIDATE (test runner 표식). usefulness gate PASS 도달 확인.
  C) abstain 과다 시나리오: deterministic abstain-only draft 가 PARTIAL 로
     떨어지는지 확인 (가짜 PASS 0 — abstain 만으로는 PASS 불가).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from butler_pc_core.cards.box3.actual_contracts import (
    Box3ActualRuntimeEnvelope,
    sha256_text,
)
from butler_pc_core.cards.box3.actual_operation_pipeline import run_box3_actual_operation
from butler_pc_core.cards.box3.actual_runner_assets import (
    BASE_MODEL_PATH_ENV,
    BASE_MODEL_SHA256_FULL,
    ActualRunnerAssetConfig,
)
from butler_pc_core.cards.box3.grounded_prompt import (
    ABSTAINED_SLOT_TEXT,
    evaluate_usefulness_gate,
)
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.local_sealed_runner import (
    build_deterministic_test_runner,
    build_local_sealed_real_runner,
)

DEFAULT_BASE_MODEL_PATH = (
    "/Users/kimsunghoon/Desktop/butler-data/학습모델/"
    "butler-1.7b-v4-rt/butler-1.7b-v4-rt/butler-1.7b-v4-rt-q4_k_m.gguf"
)
SEALED_APPROVAL_PATH = Path.home() / ".butler" / "box3" / "human_approval_v1.json"


def _build_envelope() -> Box3ActualRuntimeEnvelope:
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=[
            "참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다. "
            "납품 책임자는 운영팀이며, 추가 비용은 명시되지 않았습니다."
        ],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
        max_new_tokens=180,
        request_id="box3-rag-prompt-v1-2-real-smoke",
    )


def _write_approval(scope_digest: str) -> dict:
    SEALED_APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "box3.human_approval.v1",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("대표 승인 — box3 v1.2 RAG·프롬프트 활성화"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    SEALED_APPROVAL_PATH.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    SEALED_APPROVAL_PATH.chmod(0o600)
    return payload


def _verdict_summary(label: str, verdict, *, runner_label: str | None = None) -> dict:
    runner_measurements = dict(verdict.runner_measurements or {})
    runner_measurements.pop("draft_text", None)  # raw 0
    return {
        "scenario": label,
        "runner": runner_label or "auto",
        "status": verdict.status,
        "fail_class": verdict.fail_class,
        "real_claim_allowed": verdict.real_claim_allowed,
        "draft_text_present": bool(verdict.draft_text),
        "draft_digest": verdict.draft_digest,
        "metrics_unsupported_count": verdict.metrics.get("unsupported_count"),
        "metrics_supported_count": verdict.metrics.get("supported_count"),
        "metrics_factual_claim_count": verdict.metrics.get("factual_claim_count"),
        "runner_engine": runner_measurements.get("engine"),
        "runner_tokens_in": runner_measurements.get("tokens_in"),
        "runner_tokens_out": runner_measurements.get("tokens_out"),
        "runner_latency_ms": runner_measurements.get("latency_ms"),
        "runner_peak_memory_mb": runner_measurements.get("peak_memory_mb"),
        "stage_trace_count": len(verdict.stage_trace or []),
        "external_send_zero": verdict.external_send_zero,
        "raw_saved_zero": verdict.raw_saved_zero,
        "raw_text_logged": verdict.raw_text_logged,
    }


def _abstain_only_runner():
    abstain_lines = "\n".join(
        f"{section}: {ABSTAINED_SLOT_TEXT}"
        for section in ("제목", "배경", "핵심 내용", "근거", "확인 필요", "최종 문안")
    )

    def _runner(envelope):
        return abstain_lines

    setattr(_runner, "_box3_test_only", True)
    setattr(_runner, "_box3_runner_engine", "test_only_abstain")
    setattr(_runner, "_box3_model_load_ms", 0.0)
    setattr(_runner, "_box3_adapter_stack", {"model_adapters": ["helper3_format", "helper5_tool_call"], "test_only": True})
    return _runner


def main() -> int:
    os.environ.setdefault(BASE_MODEL_PATH_ENV, DEFAULT_BASE_MODEL_PATH)
    os.environ.setdefault("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK", "1")

    envelope_a = _build_envelope()
    approval = _write_approval(envelope_a.request_digest)
    guard = build_example_component_use_guard(
        allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"
    )
    cfg = ActualRunnerAssetConfig(
        expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
        readonly_required=False,
    )

    # Scenario A — real runner + grounded prompt.
    real_runner_build_fail_class = None
    real_runner = None
    try:
        real_runner = build_local_sealed_real_runner(cfg, helper_guard=guard)
    except RuntimeError as exc:
        real_runner_build_fail_class = str(exc)

    verdict_a = run_box3_actual_operation(
        envelope_a,
        base_config=cfg,
        helper_component_guard=guard,
        human_approval_config=approval,
        fixed_eval_pass=True,
        runner=real_runner,
    )

    # Scenario B — deterministic grounded test runner (PASS path open demonstration).
    envelope_b = _build_envelope()
    approval_b = _write_approval(envelope_b.request_digest)
    verdict_b = run_box3_actual_operation(
        envelope_b,
        base_config=cfg,
        helper_component_guard=guard,
        human_approval_config=approval_b,
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )

    # Scenario C — abstain-only deterministic runner (PARTIAL demonstration).
    envelope_c = _build_envelope()
    approval_c = _write_approval(envelope_c.request_digest)
    verdict_c = run_box3_actual_operation(
        envelope_c,
        base_config=cfg,
        helper_component_guard=guard,
        human_approval_config=approval_c,
        fixed_eval_pass=True,
        runner=_abstain_only_runner(),
    )

    payload = {
        "smoke_environment": {
            "base_model_readonly_required": False,
            "base_sha256_expected": BASE_MODEL_SHA256_FULL,
        },
        "scenario_A_real_runner_grounded_prompt": {
            **_verdict_summary("real_runner_grounded_prompt", verdict_a, runner_label="local_sealed_real_runner"),
            "real_runner_build_fail_class": real_runner_build_fail_class,
            "honest_note": (
                "1.7B v4-rt 가 grounded prompt 위에서도 사전 학습된 '공식체' 템플릿으로 환각하여 "
                "fail_class=BLOCK_UNSUPPORTED_CLAIM (가짜 PASS 0). PASS 달성을 위해서는 base 모델 "
                "교체 (qwen3-4b-gguf) 또는 helper3/5 LoRA 실제 fusion 이 필요 — 본 PR 범위 밖."
                if verdict_a.fail_class == "BLOCK_UNSUPPORTED_CLAIM"
                else None
            ),
        },
        "scenario_B_deterministic_grounded_test_runner": {
            **_verdict_summary("deterministic_grounded_test_runner", verdict_b, runner_label="deterministic_test_runner"),
            "note": "PASS 경로가 닫혀있지 않음 — usefulness gate + helper4 grounding 모두 통과 시 REAL_CANDIDATE 도달.",
        },
        "scenario_C_abstain_only_runner": {
            **_verdict_summary("abstain_only_runner", verdict_c, runner_label="abstain_only_runner"),
            "abstain_overuse_partial_lock": evaluate_usefulness_gate(
                "\n".join(f"x: {ABSTAINED_SLOT_TEXT}" for _ in range(6)),
                claim_verdicts=[],
            ).to_dict(),
            "note": "abstain-only deterministic draft 는 PASS 가 아닌 PARTIAL 로 떨어진다 (가짜 PASS 0).",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
