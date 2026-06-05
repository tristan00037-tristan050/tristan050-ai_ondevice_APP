"""박스 3 v5 endpoint smoke 시나리오 점검 (PR #784, 2026-06-05).

PR #783 머지본 head `f399bdf1` 위에서 v5 endpoint smoke 의 unsupported_count=1 이
(a) 시나리오가 그룹A "환각 0 조건" 과 불일치 때문인지, (b) v5 한계인지 가른다.

[1단계] 현재 smoke 시나리오 (PR #783) 의 RAG 문서·질문·grounded prompt + helper4
        grounding verdict 를 출력 (digest-only · 최소 raw 요약).
[2단계] 그룹A 환각 0 조건 (충분한 RAG + 명시적 grounding system + 문서로 답 가능한
        질문 + 표 요청) 재현 — 동일 v5 runner 로 1회 추론 + grounding.
[3단계] 두 시나리오의 unsupported_count + 무엇이 unsupported 인지를 라벨 단위로
        비교 보고. 결과에 따라:
          - groupA → unsupported=0 ⇒ 시나리오 정렬 문제, smoke 표준화 권고.
          - groupA → unsupported>0 ⇒ v5 한계, 4B 이관 검토 권고.

정직 정책: raw draft/prompt 본문은 영구화 0 — digest + 최소 요약(라벨·snippet ≤ 80 chr)만.
grounding 임계 완화 0, degeneration gate 유지.
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
from butler_pc_core.cards.box3.actual_runner_assets import (
    BASE_MODEL_NAME,
    BASE_MODEL_PATH_ENV,
    BASE_MODEL_SHA256_FULL,
    ActualRunnerAssetConfig,
)
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.helper_sdk_bridge import HelperSdkBridge
from butler_pc_core.cards.box3.local_sealed_runner import build_local_sealed_real_runner
from butler_pc_core.cards.box3.rag_prompt_integration import build_rag_grounded_prompt_runtime
from butler_pc_core.cards.box3.v5_degeneration_gate import detect_v5_degeneration

V5_GGUF_PATH = Path(
    "/Users/kimsunghoon/Desktop/butler-data/8박스/butler-1.7b-v5/butler-1.7b-v5-q4_k_m.gguf"
)


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snip(text: str, max_chars: int = 80) -> str:
    """라벨용 최소 snippet — 본 라벨링은 보고용으로만 사용 (영구화 0).

    grouping 의도가 명확하도록 첫 max_chars 문자만 노출. 본 snippet 은 digest 가
    동봉되므로 그룹 식별이 가능하다.
    """
    flat = " ".join(text.split())
    return flat if len(flat) <= max_chars else flat[: max_chars - 1] + "…"


# ─── Scenario 1: PR #783 current smoke (kept verbatim) ──────────────────────
CURRENT_REFS = [
    "참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다. "
    "납품 책임자는 운영팀이며, 추가 비용은 명시되지 않았습니다."
]
CURRENT_REQUEST = "납품 일정을 반영해 보고서 초안을 작성하세요."


# ─── Scenario 2: 그룹A 환각 0 조건 ────────────────────────────────────────
# (i) 충분한 RAG (4 단락, 각 단락은 한 가지 사실만)
# (iv) 표 요청 — 답변이 표 형식으로 정렬 가능
GROUPA_REFS = [
    "납품 일정: 2026년 6월 10일 (목요일).",
    "납품 책임자: 운영팀 (담당 부서명만 문서에 기재).",
    "납품 장소: 본사 1층 자재 창고.",
    "추가 비용: 문서에 명시되지 않음.",
]
# (iii) 문서로 답이 가능한 질문 + (iv) 표 요청 명시
GROUPA_REQUEST = (
    "위 4 항목을 표로 정리해 1 문장씩 보고서에 인용하세요. "
    "참고문서에 없는 내용은 절대 추가하지 말고 [문서에 근거 없음] 으로 표시하세요."
)


def _build_envelope(refs: list[str], request: str, request_id: str) -> Box3ActualRuntimeEnvelope:
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=refs,
        drafting_request=request,
        format_hint="보고서",
        max_new_tokens=220,
        request_id=request_id,
    )


def _run_scenario(name: str, refs: list[str], request: str, runner) -> dict:
    bridge = HelperSdkBridge()
    env = _build_envelope(refs, request, f"v5-smoke-audit-{name}")
    evidence = bridge.parse_evidence(env.reference_text_runtime_only)
    rag = build_rag_grounded_prompt_runtime(env, evidence)
    # runtime-only — direct runner call to capture raw draft for verdict-level diagnosis.
    try:
        draft = runner(env) or ""
    except Exception as exc:
        draft = ""
        runner_err = str(exc)[:120]
    else:
        runner_err = None
    grounding = bridge.ground_claims(draft, evidence) if draft else None
    degen = detect_v5_degeneration(draft) if draft else None

    # Per-verdict report (digest + minimal label snippet + reason_code only).
    unsupported_verdicts = []
    if grounding is not None:
        for v in grounding.claim_verdicts:
            if v.support_level == "unsupported":
                # claim text is runtime-only — we only emit its digest + first 80 chars label.
                # For diagnosis we need a hint of WHAT was claimed. Snip is bounded.
                # claim_digest is on the verdict; we also stash a probe snippet.
                unsupported_verdicts.append({
                    "claim_id": v.claim_id,
                    "claim_digest": v.claim_digest,
                    "reason_code": v.reason_code,
                    "evidence_digests_attached": list(v.evidence_digests),
                })
    return {
        "scenario": name,
        "input_summary": {
            "reference_doc_count": len(refs),
            "reference_digests": [_digest(r) for r in refs],
            "reference_snippets": [_snip(r) for r in refs],
            "drafting_request_digest": _digest(request),
            "drafting_request_snippet": _snip(request, 120),
        },
        "evidence_bundle": {
            "parse_success": evidence.parse_success,
            "evidence_unit_count": len(evidence.evidence_units_runtime),
        },
        "rag_grounded_prompt": {
            "evidence_marker_count": rag.grounded_prompt.evidence_marker_count,
            "absent_slot_count": len(rag.grounded_prompt.absent_slots),
            "prompt_digest": rag.grounded_prompt.prompt_digest,
            "context_digest": rag.rag_context.context_digest,
        },
        "runner_output": {
            "draft_present": bool(draft),
            "draft_digest": _digest(draft) if draft else None,
            "draft_token_count_approx": len(draft.split()) if draft else 0,
            "draft_snippet_first_80": _snip(draft, 80) if draft else None,
            "runner_error": runner_err,
        },
        "helper4_grounding": {
            "fail_class": grounding.fail_class if grounding else None,
            "factual_claim_count": grounding.summary.factual_claim_count if grounding else 0,
            "supported_count": grounding.summary.supported_claim_count if grounding else 0,
            "unsupported_count": grounding.summary.unsupported_claim_count if grounding else 0,
            "no_evidence_count": grounding.summary.no_evidence_claim_count if grounding else 0,
            "embedder_provider": grounding.embedder_provider if grounding else None,
            "unsupported_verdicts": unsupported_verdicts,
        },
        "degeneration_probe": degen.to_dict() if degen else None,
    }


def _verdict_compare(s1: dict, s2: dict) -> dict:
    a = s1["helper4_grounding"]["unsupported_count"]
    b = s2["helper4_grounding"]["unsupported_count"]
    if b == 0 and a > 0:
        verdict = "SCENARIO_ALIGNMENT_ISSUE"
        action = "STANDARDIZE_SMOKE_TO_GROUPA_CONDITION"
        reason = (
            "그룹A 조건에서 unsupported_count=0 도달 → 기존 smoke 시나리오가 그룹A 환각 0 "
            "조건과 불일치. smoke 를 그룹A 조건으로 표준화하면 PASS 경로 개방."
        )
    elif b > 0:
        verdict = "V5_BASE_MODEL_LIMIT"
        action = "ESCALATE_TO_GROUPA_REREVIEW_OR_4B_MIGRATION"
        reason = (
            "그룹A 조건에서도 unsupported>0 → 시나리오 정렬 문제 아님. v5 base 모델 "
            "단독으로는 PASS 도달 불가 — 그룹A 재확인 또는 qwen3-4b 이관 검토 필요."
        )
    else:
        verdict = "BOTH_PASS"
        action = "STANDARDIZE_AND_REPORT_PASS"
        reason = "두 시나리오 모두 unsupported=0 — PASS 경로 이미 개방."
    return {
        "scenario_1_unsupported_count": a,
        "scenario_2_unsupported_count": b,
        "verdict": verdict,
        "recommended_action": action,
        "reason": reason,
    }


def main() -> int:
    # v5 runner 1회만 빌드 — 두 시나리오 모두 동일 runner 사용 (공정 비교).
    os.environ[BASE_MODEL_PATH_ENV] = str(V5_GGUF_PATH)
    os.environ.pop("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK", None)
    guard = build_example_component_use_guard(
        allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"
    )
    cfg = ActualRunnerAssetConfig(
        expected_base_sha256_full=BASE_MODEL_SHA256_FULL,
        readonly_required=False,
    )
    runner = build_local_sealed_real_runner(cfg, helper_guard=guard)

    s1 = _run_scenario("scenario_1_pr783_current_smoke", CURRENT_REFS, CURRENT_REQUEST, runner)
    s2 = _run_scenario("scenario_2_groupA_zero_hallucination", GROUPA_REFS, GROUPA_REQUEST, runner)
    comparison = _verdict_compare(s1, s2)

    report = {
        "schema_version": "box3.v5_endpoint_smoke_audit.v1",
        "v5_asset": {
            "model_choice": BASE_MODEL_NAME,
            "expected_sha256_full": BASE_MODEL_SHA256_FULL,
        },
        "scenario_1_current_smoke": s1,
        "scenario_2_groupA_condition": s2,
        "comparison": comparison,
        "constraints": {
            "grounding_threshold_relaxation_zero": True,
            "degeneration_gate_active": True,
            "raw_draft_persisted": False,
        },
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
