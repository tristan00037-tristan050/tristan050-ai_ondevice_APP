from __future__ import annotations

from typing import Any

from .actual_contracts import Box3ActualOperationVerdict, Box3ActualRuntimeEnvelope, sha256_text
from .real_contracts import scan_runtime_security_risk
from .actual_fail_class import (
    APPROVED_MODEL_RUNTIME_MISMATCH,
    ASSET_INVENTORY_PASS,
    BLOCKED,
    BLOCK_DLP_OUTBOUND_DRAFT,
    BLOCK_NO_FACTUAL_CLAIMS,
    BLOCK_POLICY_GATE,
    Box3SecurityError,
    FIXED_EVAL_PENDING,
    NEEDS_REVIEW_OUTPUT_SKELETON_ECHO,
    NEEDS_REVIEW_UNSUPPORTED_CLAIM,
    NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL,
    PARTIAL_BGE_M3_FALLBACK_USED,
    PARTIAL_EMBEDDER_UNAVAILABLE,
    PARTIAL_HELPER_SDK_UNAVAILABLE,
    PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED,
    PARTIAL_REAL_ASSET_VOLUME_MISSING,
    PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
    PASS_STATUS,
    REAL_CANDIDATE,
    is_blocking_actual_fail_class,
)
from .actual_runner_assets import ActualRunnerAssetConfig, verify_base_model_asset
from .grounded_prompt import OUTPUT_SKELETON_ECHO_MARKERS, evaluate_usefulness_gate
from .helper_component_guard import verify_helper_component_use_guard
from .helper_sdk_bridge import HelperSdkBridge, _normalize_claim_line_for_helper4
from .human_approval_sealed import evaluate_human_approval_sealed
from .local_sealed_runner import RealRunner, run_actual_runner_smoke
from .model_identity import Box3ModelIdentity, assert_runtime_model_identity_matches_approval
from .rag_prompt_integration import build_rag_grounded_prompt_runtime
from .real_grounding import extract_claims
from .real_metrics import compute_claim_metrics, estimate_format_compliance, estimate_style_compliance, metric_fail_class

UNSUPPORTED_CLAIM_LABEL = "[근거 확인 필요]"
UNSUPPORTED_CLAIM_LABEL_FAILSAFE_BANNER = (
    "[전체 검토 필요] 근거 확인 라벨 매칭이 일부 실패하여 모든 사실 문장을 사람이 검토해야 합니다."
)


def normalize_draft_claim_line(line: str) -> str:
    value = str(line or "").strip()
    if not value:
        return ""
    return _normalize_claim_line_for_helper4(value)


def _helper4_digest_candidates(claim_text: str) -> set[str]:
    normalized = normalize_draft_claim_line(claim_text)
    if not normalized:
        return set()
    value_only = normalized.split(":", 1)[-1].strip() if ":" in normalized else normalized
    return {
        sha256_text(claim_text.strip()),
        sha256_text(normalized),
        sha256_text(value_only),
    }


def _line_claim_digest_candidates(line: str) -> tuple[set[str], bool]:
    claims = extract_claims(line)
    candidates: set[str] = set()
    factual_seen = False
    for claim in claims:
        if not claim.is_factual or not claim.claim_text_runtime_only.strip():
            continue
        factual_seen = True
        candidates.update(_helper4_digest_candidates(claim.claim_text_runtime_only))
    return candidates, factual_seen


def annotate_unsupported_lines(draft_text: str, unsupported_digests: set[str]) -> tuple[str, dict[str, Any]]:
    unsupported = {str(item) for item in unsupported_digests if str(item).strip()}
    if not draft_text or not unsupported:
        return draft_text, {
            "unsupported_claim_count": len(unsupported),
            "annotated_claim_count": 0,
            "label_coverage_ok": True,
            "review_reason_code": None,
        }

    lines = draft_text.splitlines()
    annotated_lines: list[str] = []
    matched: set[str] = set()
    factual_line_indexes: list[int] = []
    matched_line_indexes: set[int] = set()
    for idx, line in enumerate(lines):
        candidates, factual_seen = _line_claim_digest_candidates(line)
        if factual_seen:
            factual_line_indexes.append(idx)
        matched_here = candidates & unsupported
        if matched_here:
            matched.update(matched_here)
            matched_line_indexes.add(idx)
        annotated_lines.append(line)

    label_coverage_ok = matched == unsupported
    if not label_coverage_ok:
        target_indexes = set(factual_line_indexes)
        reason = NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL
    else:
        target_indexes = matched_line_indexes
        reason = NEEDS_REVIEW_UNSUPPORTED_CLAIM

    annotated_count = 0
    for idx, line in enumerate(annotated_lines):
        if idx not in target_indexes:
            continue
        stripped = line.lstrip()
        if stripped.startswith(UNSUPPORTED_CLAIM_LABEL):
            continue
        prefix_ws = line[: len(line) - len(stripped)]
        annotated_lines[idx] = f"{prefix_ws}{UNSUPPORTED_CLAIM_LABEL} {stripped}"
        annotated_count += 1

    annotated = "\n".join(annotated_lines)
    if not label_coverage_ok:
        annotated = f"{UNSUPPORTED_CLAIM_LABEL_FAILSAFE_BANNER}\n{annotated}"

    return annotated, {
        "unsupported_claim_count": len(unsupported),
        "annotated_claim_count": annotated_count,
        "label_coverage_ok": label_coverage_ok,
        "review_reason_code": reason,
    }


def _is_output_skeleton_echo(draft_text: str, evidence_bundle: Any) -> bool:
    """모델이 V9_1_OUTPUT_SKELETON 플레이스홀더 문구를 실제 내용으로 에코했는지 감지.

    few-shot 리터럴 가드(#849)와 같은 계열 — 이번엔 골격 문구가 새는 경우. 골격 마커가
    draft 에 그대로 등장하면서 실제 근거 텍스트(evidence)에는 없으면 에코로 본다.
    """
    if not draft_text:
        return False
    evidence_text = "\n".join(
        getattr(unit, "text_runtime_only", "") for unit in getattr(evidence_bundle, "evidence_units_runtime", [])
    )
    return any(
        marker in draft_text and marker not in evidence_text
        for marker in OUTPUT_SKELETON_ECHO_MARKERS
    )


def _status_from_gate(
    *,
    base_status: str,
    helper_fail: str | None,
    parse_fail: str | None,
    runner_ok: bool,
    runner_fail: str | None,
    bridge_fail: str | None,
    metrics,
    fixed_eval_pass: bool,
    approval_allowed: bool,
    approval_fail: str | None,
    test_only_runner: bool,
) -> tuple[str, bool, str | None, bool]:
    if base_status in {PARTIAL_REAL_ASSET_VOLUME_MISSING, PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE} and not test_only_runner:
        return base_status, False, base_status, True
    if helper_fail:
        # 원래 의도: PARTIAL_ 계열만 soft(그 status 로 통과), 그 외는 하드블록. severity map 등가
        # 검증(모든 helper fail 값에서 is_blocking ≡ not PARTIAL_) 후 helper 경유로 통일 — 미등록/
        # 새 fail_class 는 보수적으로 BLOCKED.
        return (BLOCKED if is_blocking_actual_fail_class(helper_fail) else helper_fail), False, helper_fail, True
    if parse_fail:
        return (BLOCKED if is_blocking_actual_fail_class(parse_fail) else parse_fail), False, parse_fail, True
    if not runner_ok:
        if runner_fail in {PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE, PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED}:
            return runner_fail, False, runner_fail, True
        return (BLOCKED if is_blocking_actual_fail_class(runner_fail) else ASSET_INVENTORY_PASS), False, runner_fail, True
    if test_only_runner:
        return REAL_CANDIDATE, False, "TEST_ONLY_RUNNER_NOT_REAL_APPROVAL", True
    if not approval_allowed and approval_fail != "BLOCK_HUMAN_APPROVAL_MISSING":
        return BLOCKED, False, approval_fail, True
    if bridge_fail:
        if bridge_fail in {PARTIAL_HELPER_SDK_UNAVAILABLE, PARTIAL_EMBEDDER_UNAVAILABLE, PARTIAL_BGE_M3_FALLBACK_USED}:
            return REAL_CANDIDATE, False, bridge_fail, True
        return (BLOCKED if is_blocking_actual_fail_class(bridge_fail) else REAL_CANDIDATE), False, bridge_fail, True
    metric_fail = metric_fail_class(metrics)
    if metric_fail:
        return (BLOCKED if is_blocking_actual_fail_class(metric_fail) else REAL_CANDIDATE), False, metric_fail, True
    if not fixed_eval_pass:
        return REAL_CANDIDATE, False, FIXED_EVAL_PENDING, True
    if not approval_allowed:
        return REAL_CANDIDATE if approval_fail == "BLOCK_HUMAN_APPROVAL_MISSING" else BLOCKED, False, approval_fail, True
    return PASS_STATUS, True, None, False

def run_box3_actual_operation(
    envelope: Box3ActualRuntimeEnvelope,
    *,
    base_config: ActualRunnerAssetConfig | None = None,
    helper_component_guard: dict[str, Any] | None = None,
    human_approval_config: dict[str, Any] | None = None,
    fixed_eval_pass: bool = False,
    runner: RealRunner | None = None,
    sdk_bridge: HelperSdkBridge | None = None,
    approval_expected_scope_digest: str | None = None,
    approval_mode: str | None = None,
    approval_context: str | None = None,
    approved_model_identity: Box3ModelIdentity | None = None,
) -> Box3ActualOperationVerdict:
    # v1.2 §3.4: desktop 경로에서 endpoint 가 넘긴 승인 identity 를 생성 직전 재대조한다.
    # 미전달(eval/test 직접 호출)이면 재대조를 건너뛴다 — 기존 request_scope 경로 diff 0.
    expected_scope_digest = approval_expected_scope_digest or envelope.request_digest
    stage_trace: list[dict[str, Any]] = []
    if not envelope.policy_gate_allowed:
        return Box3ActualOperationVerdict(
            schema_version="box3.actual_operation.v1_2",
            request_id=envelope.request_id,
            request_digest=envelope.request_digest,
            status=BLOCKED,
            draft_text=None,
            draft_digest=None,
            metrics={},
            citations=[],
            stage_trace=[{"stage": "policy_gate", "passed": False, "fail_class": BLOCK_POLICY_GATE}],
            fail_class=BLOCK_POLICY_GATE,
            real_claim_allowed=False,
            human_approval_required=True,
            runner_measurements={},
            asset_measurements={},
            helper_sdk_receipts={},
        )

    base = verify_base_model_asset(base_config)
    stage_trace.append({"stage": "base_model_asset", "passed": base.allowed, "status": base.status, "fail_class": base.fail_class})

    helper = verify_helper_component_use_guard(helper_component_guard)
    stage_trace.append({"stage": "role_wiring", "passed": helper.allowed, "fail_class": helper.fail_class, "sdk_call_supported": helper.sdk_call_supported, "helper_stack_supported": helper.helper_stack_supported})

    bridge = sdk_bridge or HelperSdkBridge.from_env()
    evidence_bundle = bridge.parse_evidence(envelope.reference_text_runtime_only)
    envelope_evidence_count = len(evidence_bundle.evidence_units_runtime)
    stage_trace.append({
        "stage": "helper7_parse_evidence",
        "passed": evidence_bundle.parse_success,
        "fail_class": evidence_bundle.fail_class,
        "evidence_count": envelope_evidence_count,
    })

    # Box3 RAG·Prompt activation v1.2 (2026-06-04): helper7 parse 직후 runner 전에
    # build_rag_context_packet + build_grounded_prompt_packet 을 1회 삽입하여
    # grounded_prompt_runtime_only 를 envelope 에 부착한다. helper4 grounding
    # 임계는 완화 0 (본 단계는 입력 프롬프트만 강화).
    rag_prompt = build_rag_grounded_prompt_runtime(envelope, evidence_bundle)
    stage_trace.append(rag_prompt.to_stage_trace_entry())

    # v1.2 §3.4: 실제 생성 직전, 승인된 model identity 와 런타임 모델을 재대조한다(TOCTOU 결속).
    if approved_model_identity is not None:
        try:
            assert_runtime_model_identity_matches_approval(approved_model_identity, runtime=runner)
            stage_trace.append({"stage": "approved_model_runtime_recheck", "passed": True, "fail_class": None})
        except Box3SecurityError as exc:
            reason = str(exc) or APPROVED_MODEL_RUNTIME_MISMATCH
            stage_trace.append({"stage": "approved_model_runtime_recheck", "passed": False, "fail_class": reason})
            return Box3ActualOperationVerdict(
                schema_version="box3.actual_operation.v1_2",
                request_id=envelope.request_id,
                request_digest=envelope.request_digest,
                status=BLOCKED,
                draft_text=None,
                draft_digest=None,
                metrics={},
                citations=[],
                stage_trace=stage_trace,
                fail_class=reason,
                real_claim_allowed=False,
                human_approval_required=True,
                runner_measurements={},
                asset_measurements={"base": base.to_dict(), "helper": helper.to_dict()},
                helper_sdk_receipts={},
            )

    if base.allowed and helper.allowed and evidence_bundle.parse_success:
        smoke = run_actual_runner_smoke(envelope, runner=runner, config=base_config, helper_guard=helper_component_guard)
    else:
        smoke = run_actual_runner_smoke(envelope, runner=runner, config=base_config, helper_guard=helper_component_guard) if runner is not None else None
    if smoke is None:
        runner_ok = False
        runner_fail = base.fail_class or helper.fail_class or evidence_bundle.fail_class
        runner_measurements = {}
        draft = ""
        test_only = False
    else:
        runner_ok = smoke.ok
        runner_fail = smoke.fail_class
        runner_measurements = smoke.to_dict()
        draft = smoke.draft_text or ""
        test_only = smoke.test_only_runner
    stage_trace.append({"stage": "draft_runner_helper3_helper5_stack", "passed": runner_ok, "fail_class": runner_fail, **runner_measurements})

    # #852 작업2: runner 초안 생성 직후·grounding 이전에 골격 문구 에코를 감지한다(원본 draft 기준).
    skeleton_echo = _is_output_skeleton_echo(draft, evidence_bundle)
    stage_trace.append({"stage": "output_skeleton_echo_scan", "passed": not skeleton_echo, "fail_class": NEEDS_REVIEW_OUTPUT_SKELETON_ECHO if skeleton_echo else None})

    grounding_bundle = bridge.ground_claims(draft, evidence_bundle) if draft else None
    if grounding_bundle is None:
        verdicts = []
        bridge_fail = runner_fail or evidence_bundle.fail_class
        citations = []
        metrics = compute_claim_metrics([], format_compliance=0.0, style_compliance=0.0, evidence_units=evidence_bundle.evidence_units_runtime)
        grounding_receipt = None
    else:
        verdicts = grounding_bundle.claim_verdicts
        bridge_fail = grounding_bundle.fail_class
        # #852 작업2: 골격 에코가 원인인 vacuous BLOCK_NO_FACTUAL_CLAIMS 는 하드블록 대신
        # needs_review(NEEDS_REVIEW_OUTPUT_SKELETON_ECHO)로 강등해 라벨 붙여 전달한다.
        if skeleton_echo and bridge_fail in (None, BLOCK_NO_FACTUAL_CLAIMS):
            bridge_fail = NEEDS_REVIEW_OUTPUT_SKELETON_ECHO
        citations = [unit.citation() for unit in evidence_bundle.evidence_units_runtime]
        styled = bridge.apply_company_style(draft)
        if styled.style_applied:
            draft = styled.draft_text_runtime
        if styled.fail_class and bridge_fail is None:
            bridge_fail = styled.fail_class
        format_score = estimate_format_compliance(draft)
        style_score = estimate_style_compliance(draft)
        metrics = compute_claim_metrics(verdicts, format_compliance=format_score, style_compliance=style_score, evidence_units=evidence_bundle.evidence_units_runtime)
        usefulness = evaluate_usefulness_gate(draft, verdicts)
        if usefulness.status != "PASS" and bridge_fail is None:
            bridge_fail = usefulness.fail_class
        unsupported_digests = {
            verdict.claim_digest
            for verdict in verdicts
            if getattr(verdict, "support_level", None) == "unsupported"
        }
        draft, label_meta = annotate_unsupported_lines(draft, unsupported_digests)
        if label_meta["review_reason_code"] == NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL:
            bridge_fail = NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL
        grounding_receipt = grounding_bundle.persistable_dict()
        stage_trace.append({"stage": "helper4_grounding", "passed": grounding_bundle.summary.unsupported_claim_count == 0, "fail_class": grounding_bundle.fail_class, "embedder_provider": grounding_bundle.embedder_provider})
        stage_trace.append({"stage": "usefulness_gate", **usefulness.to_dict()})
        stage_trace.append({
            "stage": "unsupported_claim_labeling",
            "passed": label_meta["label_coverage_ok"],
            "fail_class": None if label_meta["label_coverage_ok"] else NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL,
            "unsupported_claim_count": label_meta["unsupported_claim_count"],
            "annotated_claim_count": label_meta["annotated_claim_count"],
            "label_coverage_ok": label_meta["label_coverage_ok"],
        })
        stage_trace.append({"stage": "helper8_company_style", "passed": styled.style_applied, "fail_class": styled.fail_class})
    if grounding_bundle is None:
        label_meta = {
            "unsupported_claim_count": 0,
            "annotated_claim_count": 0,
            "label_coverage_ok": True,
            "review_reason_code": None,
        }

    approval = evaluate_human_approval_sealed(
        human_approval_config,
        expected_scope_digest=expected_scope_digest,
        approval_mode=approval_mode,
        approval_context=approval_context,
    )
    stage_trace.append({"stage": "human_approval", "passed": approval.allowed, "fail_class": approval.fail_class, "config_digest": approval.config_digest, "approval_mode": approval.approval_mode, "approval_context": approval.approval_context})

    status, real_allowed, fail_class, approval_required = _status_from_gate(
        base_status=base.status,
        helper_fail=helper.fail_class,
        parse_fail=evidence_bundle.fail_class,
        runner_ok=runner_ok,
        runner_fail=runner_fail,
        bridge_fail=bridge_fail,
        metrics=metrics,
        fixed_eval_pass=fixed_eval_pass,
        approval_allowed=approval.allowed,
        approval_fail=approval.fail_class,
        test_only_runner=test_only,
    )
    draft_text = draft if status in {REAL_CANDIDATE, PASS_STATUS} else None
    if draft_text:
        dlp_reason = scan_runtime_security_risk(draft_text)
        if dlp_reason:
            stage_trace.append({"stage": "dlp_pre_output_guard", "passed": False, "fail_class": BLOCK_DLP_OUTBOUND_DRAFT, "reason_code": dlp_reason})
            return Box3ActualOperationVerdict(
                schema_version="box3.actual_operation.v1_2",
                request_id=envelope.request_id,
                request_digest=envelope.request_digest,
                status=BLOCKED,
                draft_text=None,
                draft_digest=None,
                metrics=metrics.to_dict(),
                citations=citations,
                stage_trace=stage_trace + [{"stage": "final_gate", "status": BLOCKED, "real_claim_allowed": False, "fail_class": BLOCK_DLP_OUTBOUND_DRAFT}],
                fail_class=BLOCK_DLP_OUTBOUND_DRAFT,
                real_claim_allowed=False,
                human_approval_required=True,
                runner_measurements=runner_measurements,
                asset_measurements={"base": base.to_dict(), "helper": helper.to_dict()},
                helper_sdk_receipts={"evidence": evidence_bundle.persistable_dict(), "grounding": grounding_receipt},
                needs_review=True,
                review_reason_code=BLOCK_DLP_OUTBOUND_DRAFT,
                unsupported_claim_count=label_meta["unsupported_claim_count"],
                annotated_claim_count=label_meta["annotated_claim_count"],
                label_coverage_ok=label_meta["label_coverage_ok"],
            )
        stage_trace.append({"stage": "dlp_pre_output_guard", "passed": True, "fail_class": None})
    helper_receipts = {
        "evidence": evidence_bundle.persistable_dict(),
        "grounding": grounding_receipt,
    }
    return Box3ActualOperationVerdict(
        schema_version="box3.actual_operation.v1_2",
        request_id=envelope.request_id,
        request_digest=envelope.request_digest,
        status=status,  # type: ignore[arg-type]
        draft_text=draft_text,
        draft_digest=sha256_text(draft) if draft_text else None,
        metrics=metrics.to_dict(),
        citations=citations,
        stage_trace=stage_trace + [{"stage": "final_gate", "status": status, "real_claim_allowed": real_allowed, "fail_class": fail_class}],
        fail_class=fail_class,
        real_claim_allowed=real_allowed,
        human_approval_required=approval_required,
        runner_measurements=runner_measurements,
        asset_measurements={"base": base.to_dict(), "helper": helper.to_dict()},
        helper_sdk_receipts=helper_receipts,
        needs_review=bool(fail_class) or real_allowed is not True,
        review_reason_code=label_meta["review_reason_code"] or fail_class,
        unsupported_claim_count=label_meta["unsupported_claim_count"],
        annotated_claim_count=label_meta["annotated_claim_count"],
        label_coverage_ok=label_meta["label_coverage_ok"],
    )
