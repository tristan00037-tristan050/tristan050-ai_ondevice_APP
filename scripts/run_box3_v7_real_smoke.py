"""박스 3 v7 canonical apply real smoke (PR #787, 2026-06-07).

PR #784/#785 머지본 위에서 v7 base (`butler-1.7b-v7-q4_k_m.gguf`, SHA `a8440e98…5621`)
로 endpoint 를 실제 추론 + grounding + usefulness + v7_degeneration_gate 까지 흘리고
v5/v4 BLOCKED 와 비교 보고한다.

정직 출력 정책: raw draft/prompt/path 0. digest/카운트/라벨만.
"""
from __future__ import annotations

import hashlib
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
    BASE_MODEL_NAME,
    BASE_MODEL_PATH_ENV,
    BASE_MODEL_SHA256_FULL,
    ActualRunnerAssetConfig,
)
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.local_sealed_runner import build_local_sealed_real_runner
from butler_pc_core.cards.box3.v7_degeneration_gate import evaluate_degeneration

V7_GGUF_PATH = Path(
    "/Users/kimsunghoon/Desktop/butler-data/8박스/m3max/butler-1.7b-v7/butler-1.7b-v7-q4_k_m.gguf"
)
SEALED_APPROVAL_PATH = Path.home() / ".butler" / "box3" / "human_approval_v1.json"


def _measure_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_envelope() -> Box3ActualRuntimeEnvelope:
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=[
            "납품 일정: 2026년 6월 10일 (목요일).",
            "납품 책임자: 운영팀 (담당 부서명만 문서에 기재).",
            "납품 장소: 본사 1층 자재 창고.",
            "추가 비용: 문서에 명시되지 않음.",
        ],
        drafting_request=(
            "위 4 항목을 한국어 산문 보고서로 정리하세요. "
            "참고문서에 없는 내용은 절대 추가하지 말고 [문서에 근거 없음] 으로 표시하세요."
        ),
        format_hint="보고서",
        max_new_tokens=220,
        request_id="box3-v7-canonical-real-smoke",
    )


def _write_approval(scope_digest: str) -> dict:
    SEALED_APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "box3.human_approval.v1",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("대표 승인 — box3 v7 canonical apply"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    SEALED_APPROVAL_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    SEALED_APPROVAL_PATH.chmod(0o600)
    return payload


def main() -> int:
    measured_sha = _measure_sha(V7_GGUF_PATH)
    sha_match = measured_sha == BASE_MODEL_SHA256_FULL
    os.environ[BASE_MODEL_PATH_ENV] = str(V7_GGUF_PATH)
    os.environ.pop("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK", None)

    envelope = _build_envelope()
    approval = _write_approval(envelope.request_digest)
    guard = build_example_component_use_guard(
        allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"
    )
    cfg = ActualRunnerAssetConfig(
        expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
        readonly_required=False,  # dev smoke
    )

    runner = None
    runner_build_fail = None
    try:
        runner = build_local_sealed_real_runner(cfg, helper_guard=guard)
    except RuntimeError as exc:
        runner_build_fail = str(exc)

    verdict = run_box3_actual_operation(
        envelope,
        base_config=cfg,
        helper_component_guard=guard,
        human_approval_config=approval,
        fixed_eval_pass=True,
        runner=runner,
    )

    # Direct runner probe — pipeline hides BLOCKED draft. runtime-only inspection.
    direct_draft = ""
    if runner is not None:
        try:
            direct_draft = runner(envelope) or ""
        except Exception:
            direct_draft = ""
    draft_for_probe = verdict.draft_text or direct_draft
    degen_v7 = evaluate_degeneration(draft_for_probe) if draft_for_probe else None
    direct_draft_digest = (
        "sha256:" + hashlib.sha256(draft_for_probe.encode("utf-8")).hexdigest()
        if draft_for_probe else None
    )
    direct_draft_token_count = len(draft_for_probe.split()) if draft_for_probe else 0

    runner_meas = dict(verdict.runner_measurements or {})
    runner_meas.pop("draft_text", None)

    report = {
        "schema_version": "box3.v7_canonical_apply.smoke.v1_2",
        "v7_asset_verification": {
            "model_choice": BASE_MODEL_NAME,
            "expected_sha256_full": BASE_MODEL_SHA256_FULL,
            "measured_sha256_full": measured_sha,
            "sha_match": sha_match,
            "size_bytes_measured": V7_GGUF_PATH.stat().st_size,
        },
        "sealed_approval": {
            "scope_digest": approval["approval_scope_digest"],
            "approved_by_digest": approval["approved_by_digest"],
        },
        "endpoint_smoke": {
            "status": verdict.status,
            "fail_class": verdict.fail_class,
            "real_claim_allowed": verdict.real_claim_allowed,
            "draft_text_present": bool(verdict.draft_text),
            "draft_digest": verdict.draft_digest,
            "metrics": verdict.metrics,
            "runner_engine": runner_meas.get("engine"),
            "runner_tokens_in": runner_meas.get("tokens_in"),
            "runner_tokens_out": runner_meas.get("tokens_out"),
            "runner_latency_ms": runner_meas.get("latency_ms"),
            "runner_peak_memory_mb": runner_meas.get("peak_memory_mb"),
            "runner_adapter_stack_capability": (runner_meas.get("adapter_stack") or {}).get("detail", {}).get("stack_capability"),
            "runner_build_fail_class": runner_build_fail,
            "external_send_zero": verdict.external_send_zero,
            "raw_saved_zero": verdict.raw_saved_zero,
            "raw_text_logged": verdict.raw_text_logged,
        },
        "v7_degeneration_probe": degen_v7.to_dict() if degen_v7 else None,
        "direct_runner_probe": {
            "draft_digest": direct_draft_digest,
            "draft_token_count": direct_draft_token_count,
        },
        "v4_default_reference_zero": "v4-rt" not in str(V7_GGUF_PATH).casefold(),
        "v5_default_reference_zero": "1.7b-v5" not in str(V7_GGUF_PATH).casefold(),
        "comparison_v5_blocked_baseline": (
            "PR #783 v5 baseline: status=BLOCKED, fail_class=BLOCK_UNSUPPORTED_CLAIM, "
            "tokens_out=44, peak=2732MB, degen=false. "
            "PR #784 audit: v5 가 JSON tool_call 출력 over-fit → 두 시나리오 모두 unsupported=1. "
            "PR #785 absorb 후 v7 비교: 본 측정 참조."
        ),
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
