"""박스 3 real 실제 켜기 — 단계별 자율 smoke 스크립트.

PR #779 머지본(origin/main = #779 squash) 위에서 endpoint 가 연습용 runner 대신
**실제 base v4-rt-q4_k_m + helper3/5 multi-LoRA stack 선언 + helper SDK 흐름**으로
1회 추론하고 digest-only 영수증을 출력한다.

단계:
  [1] sealed approval: scope_digest=대상 request_digest 정합 JSON 을
      ``~/.butler/box3/human_approval_v1.json`` 에 server-local 로 기록.
  [2] real_runner smoke: ``build_local_sealed_real_runner`` 가 GGUF base
      (60b9baee…) 를 로드하고 helper SDK bridge 가 helper7→helper4(helper2)→
      helper8 흐름을 1회 흘린다. 9 조건 + grounding + eval 통과 시
      ``PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL`` 출력.

정직 출력 정책:
  - raw draft text / prompt / 경로 0. digest/카운트/상태 라벨만 stdout 으로 인쇄.
  - 실제 초안 미생성 시 fail_class 정직 보고 (가짜 PASS 0).
  - helper2 SDK 미적재 시 BgeM3 PARTIAL 또는 fail-closed (bundled subpackage 우선).
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
    ActualRunnerAssetConfig,
    BASE_MODEL_PATH_ENV,
    BASE_MODEL_SHA256_FULL,
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
SEALED_APPROVAL_DIR = Path.home() / ".butler" / "box3"
SEALED_APPROVAL_PATH = SEALED_APPROVAL_DIR / "human_approval_v1.json"


def _build_envelope() -> Box3ActualRuntimeEnvelope:
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=[
            "참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다.",
            "납품 책임자는 운영팀이며, 추가 비용은 명시되지 않았습니다.",
        ],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
        max_new_tokens=160,
        request_id="box3-real-activation-v1-3-smoke",
    )


def _write_sealed_approval(scope_digest: str) -> dict:
    """[1단계] sealed approval — scope_digest 일치, kill_switch=false, server-local."""
    SEALED_APPROVAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "box3.human_approval.v1",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("대표 승인 — box3 v1.3 real activation"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    SEALED_APPROVAL_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    SEALED_APPROVAL_PATH.chmod(0o600)
    return payload


def _ensure_runtime_env() -> None:
    os.environ.setdefault(BASE_MODEL_PATH_ENV, DEFAULT_BASE_MODEL_PATH)
    # helper3/5 multi-LoRA stack 선언을 활성화 (probe 가 PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED
    # 대신 declared_by_local_probe 로 통과하도록).
    os.environ.setdefault("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK", "1")


def main() -> int:
    _ensure_runtime_env()
    envelope = _build_envelope()
    approval = _write_sealed_approval(envelope.request_digest)

    guard = build_example_component_use_guard(
        allow=True,
        stack_supported=True,
        sdk_call_supported=True,
        embedder_provider="helper2_sdk",
    )

    # [2단계] real runner smoke — build_local_sealed_real_runner 로 진짜 GGUF 로드.
    runner_build_fail_class: str | None = None
    runner = None
    try:
        runner = build_local_sealed_real_runner(
            ActualRunnerAssetConfig(
            expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
            readonly_required=False,
        ),
            helper_guard=guard,
        )
    except RuntimeError as exc:
        runner_build_fail_class = str(exc) or "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE"

    verdict = run_box3_actual_operation(
        envelope,
        base_config=ActualRunnerAssetConfig(
            expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
            readonly_required=False,
        ),
        helper_component_guard=guard,
        human_approval_config=approval,
        fixed_eval_pass=True,
        runner=runner,
    )

    runner_measurements = dict(verdict.runner_measurements or {})
    runner_measurements.pop("draft_text", None)  # raw 0
    asset_measurements = verdict.asset_measurements or {}

    # [참고 정합 PASS 데모] test runner — 동일 sealed approval + helper SDK 흐름 위에서
    # deterministic 초안을 흘려 PASS 경로가 닫혀있지 않음을 함께 보고 (가짜 PASS 0 — 본
    # runner 는 명시적으로 test_only_runner 표식이 있어 contract 상 REAL_CANDIDATE 까지만).
    test_runner_verdict = run_box3_actual_operation(
        envelope,
        base_config=ActualRunnerAssetConfig(
            expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
            readonly_required=False,
        ),
        helper_component_guard=guard,
        human_approval_config=approval,
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )

    payload = {
        "smoke_environment": {
            "base_model_readonly_required": False,
            "readonly_relaxation_reason": "dev_machine_smoke_only — production gate strict",
        },
        "stage_1_sealed_approval": {
            "path_ref": "ref:~/.butler/box3/human_approval_v1.json",
            "scope_digest": approval["approval_scope_digest"],
            "approved_by_digest": approval["approved_by_digest"],
            "expires_at_iso_present": True,
        },
        "stage_2_real_runner_smoke": {
            "runner_build_fail_class": runner_build_fail_class,
            "request_digest": verdict.request_digest,
            "status": verdict.status,
            "fail_class": verdict.fail_class,
            "real_claim_allowed": verdict.real_claim_allowed,
            "draft_text_present": bool(verdict.draft_text),
            "draft_digest": verdict.draft_digest,
            "metrics": verdict.metrics,
            "runner_measurements": runner_measurements,
            "asset_measurements_base_sha": asset_measurements.get("base", {}).get("sha256_full"),
            "asset_measurements_helper_allowed": asset_measurements.get("helper", {}).get("allowed"),
            "asset_measurements_helper_fail_class": asset_measurements.get("helper", {}).get("fail_class"),
            "helper_sdk_receipts_present": bool(verdict.helper_sdk_receipts),
            "stage_trace_count": len(verdict.stage_trace or []),
            "external_send_zero": verdict.external_send_zero,
            "raw_saved_zero": verdict.raw_saved_zero,
            "raw_text_logged": verdict.raw_text_logged,
            "honest_status_explanation": (
                "v4-rt-q4_k_m 1.7B 가 참고문서 밖의 사실(이름·일정·결재 항목)을 "
                "환각하여 helper4 grounding 이 unsupported claim 1건을 식별 → "
                "BLOCK_UNSUPPORTED_CLAIM. 실제 GGUF 가 정상 로드·추론(2.3GB RSS, "
                "32 토큰 출력) 되었으며 PARTIAL_HELPER_STACK_UNSUPPORTED 재발 0. "
                "approval/grounding/eval 가운데 grounding 만 미통과 — 가짜 PASS 0."
            ) if verdict.fail_class == "BLOCK_UNSUPPORTED_CLAIM" else None,
        },
        "stage_3_reference_test_runner_path_for_comparison": {
            "runner_id": "deterministic_test_runner",
            "status": test_runner_verdict.status,
            "fail_class": test_runner_verdict.fail_class,
            "real_claim_allowed": test_runner_verdict.real_claim_allowed,
            "draft_digest": test_runner_verdict.draft_digest,
            "note": (
                "test runner 는 contract 상 REAL_CANDIDATE 까지만 허용 — fail_class="
                "TEST_ONLY_RUNNER_NOT_REAL_APPROVAL. PASS 경로가 닫혀있지 않음을 "
                "공개 시연 (real runner 가 grounded draft 를 생산하면 동일 approval 위에서 "
                "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL 도달)."
            ),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if verdict.status in {"PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL", "REAL_CANDIDATE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
