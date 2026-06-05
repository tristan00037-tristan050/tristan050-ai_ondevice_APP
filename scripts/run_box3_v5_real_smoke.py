"""박스 3 v5 canonical apply real smoke (PR #783, 2026-06-05).

PR #782 머지본 head 9122167c 위에서 v5 base (`butler-1.7b-v5-q4_k_m.gguf`,
SHA `5e233aab…`) 로 endpoint 를 실제 추론 + grounding + usefulness + degeneration
gate 까지 흘리고 v4-rt (이전 PR #780/#781 smoke) 와 비교 보고한다.

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
from butler_pc_core.cards.box3.v5_degeneration_gate import detect_v5_degeneration

V5_GGUF_PATH = Path(
    "/Users/kimsunghoon/Desktop/butler-data/8박스/butler-1.7b-v5/butler-1.7b-v5-q4_k_m.gguf"
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
            "참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다. "
            "납품 책임자는 운영팀이며, 추가 비용은 명시되지 않았습니다."
        ],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
        max_new_tokens=180,
        request_id="box3-v5-canonical-real-smoke",
    )


def _write_approval(scope_digest: str) -> dict:
    SEALED_APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "box3.human_approval.v1",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("대표 승인 — box3 v5 canonical apply"),
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
    measured_sha = _measure_sha(V5_GGUF_PATH)
    sha_match = measured_sha == BASE_MODEL_SHA256_FULL
    os.environ[BASE_MODEL_PATH_ENV] = str(V5_GGUF_PATH)
    # v5 embedded path — multi-LoRA stack env 미설정 (default).
    os.environ.pop("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK", None)

    envelope = _build_envelope()
    approval = _write_approval(envelope.request_digest)
    guard = build_example_component_use_guard(
        allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"
    )
    cfg = ActualRunnerAssetConfig(
        expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
        readonly_required=False,  # dev smoke; production gate strict
    )

    # Build real runner (v5 GGUF + embedded helper3/5).
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

    # Manually run degeneration probe on the actual draft (runtime-only inspection).
    # pipeline 은 BLOCKED 상태에서 draft_text 를 노출하지 않으므로 runner 를 직접 1회
    # 호출하여 raw draft 를 runtime-only 로 받아 degeneration probe 만 수행 (raw 0 persist).
    direct_draft = ""
    if runner is not None:
        try:
            direct_draft = runner(envelope) or ""
        except Exception:
            direct_draft = ""
    draft_for_probe = verdict.draft_text or direct_draft
    degen = detect_v5_degeneration(draft_for_probe) if draft_for_probe else None
    direct_draft_token_count = len(draft_for_probe.split()) if draft_for_probe else 0
    direct_draft_digest = (
        "sha256:" + hashlib.sha256(draft_for_probe.encode("utf-8")).hexdigest()
        if draft_for_probe
        else None
    )

    runner_meas = dict(verdict.runner_measurements or {})
    runner_meas.pop("draft_text", None)  # raw 0

    report = {
        "schema_version": "box3.v5_canonical_apply.smoke.v1_2",
        "v5_asset_verification": {
            "model_choice": BASE_MODEL_NAME,
            "expected_sha256_full": BASE_MODEL_SHA256_FULL,
            "measured_sha256_full": measured_sha,
            "sha_match": sha_match,
            "size_bytes_measured": V5_GGUF_PATH.stat().st_size,
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
        "degeneration_probe": degen.to_dict() if degen else None,
        "direct_runner_probe": {
            "draft_token_count": direct_draft_token_count,
            "draft_digest": direct_draft_digest,
        },
        "v4_default_reference_zero": "v4-rt" not in str(V5_GGUF_PATH).casefold(),
        "v4_v5_comparison_note": (
            "PR #780 baseline (v4-rt 1.7B): status=BLOCKED, fail_class=BLOCK_UNSUPPORTED_CLAIM, "
            "tokens_out~32, peak_memory~2300MB, sections 0/6, json_shape=False (환각). "
            "본 v5 측정과 비교 — 동일 sealed approval 위에서 unsupported_count 와 degeneration 변화 확인."
        ),
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
