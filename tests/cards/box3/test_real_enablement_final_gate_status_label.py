"""Codex HOLD 정정 회귀 (2026-06-03, PR #775) — final_gate 상태 라벨 SSOT 정합.

evaluate_final_real_gate 가 9조건 + human approval 모두 통과 시 Box3RealStatus Literal SSOT
라벨 `PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL` 를 반환하는지 회귀 잠금. 이전 임시 라벨이
Literal 에 부재하던 상태 드리프트 결함을 차단한다.
"""
from __future__ import annotations

from butler_pc_core.cards.box3.final_gate import evaluate_final_real_gate
from butler_pc_core.cards.box3.human_approval import HumanApprovalVerdict
from butler_pc_core.cards.box3.real_contracts import Box3RealMetrics
from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerAssetVerdict


def _passing_metrics() -> Box3RealMetrics:
    return Box3RealMetrics(
        unsupported_claim_rate=0.0,
        no_evidence_claim_rate=0.0,
        citation_accuracy=1.0,
        format_compliance=0.95,
        style_compliance=0.85,
        table_figure_coverage=0.90,
        factual_claim_count=3,
        unsupported_count=0,
        no_evidence_count=0,
        supported_count=3,
    )


def _passing_asset_verdict() -> Box3RealRunnerAssetVerdict:
    return Box3RealRunnerAssetVerdict(
        allowed=True,
        fail_class=None,
        runner_asset_digest="sha256:" + "a" * 64,
        asset_manifest_digest="sha256:" + "b" * 64,
        rows=[],
        measured={},
    )


def _passing_human_approval() -> HumanApprovalVerdict:
    return HumanApprovalVerdict(
        allowed=True,
        fail_class=None,
        config_digest="sha256:" + "c" * 64,
        approval_scope_digest="sha256:" + "d" * 64,
        kill_switch_enabled=False,
    )


def test_all_conditions_pass_returns_pass_box3_real_local_after_human_approval_label():
    """9 조건 + approval allow + kill_switch=false 모두 통과 시 SSOT 라벨 반환."""
    decision = evaluate_final_real_gate(
        asset_verdict=_passing_asset_verdict(),
        policy_allowed=True,
        runner_generated=True,
        runner_fail_class=None,
        evidence_count=3,
        claim_count=3,
        metrics=_passing_metrics(),
        fixed_eval_pass=True,
        human_approval=_passing_human_approval(),
    )

    assert decision.status == "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL"
    assert decision.real_claim_allowed is True
    assert decision.human_approval_required is False
    assert decision.fail_class is None
    assert all(c.passed for c in decision.conditions)


def test_returned_status_is_inside_box3_real_status_literal_set():
    """drift 회귀 차단 — final_gate 가 반환할 수 있는 status 라벨이 Box3RealStatus Literal
    SSOT 라벨 집합 안에 있어야 한다 (typing.get_args 로 정합 검증)."""
    from typing import get_args

    from butler_pc_core.cards.box3.real_contracts import Box3RealStatus

    decision = evaluate_final_real_gate(
        asset_verdict=_passing_asset_verdict(),
        policy_allowed=True,
        runner_generated=True,
        runner_fail_class=None,
        evidence_count=3,
        claim_count=3,
        metrics=_passing_metrics(),
        fixed_eval_pass=True,
        human_approval=_passing_human_approval(),
    )

    allowed_labels = set(get_args(Box3RealStatus))
    assert decision.status in allowed_labels, (
        f"status {decision.status!r} not in Box3RealStatus Literal {allowed_labels!r}"
    )


def test_human_approval_missing_returns_real_candidate_not_pass_label():
    """approval 미충족 시 SSOT 라벨 반환 안 함 (REAL_CANDIDATE 정직)."""
    decision = evaluate_final_real_gate(
        asset_verdict=_passing_asset_verdict(),
        policy_allowed=True,
        runner_generated=True,
        runner_fail_class=None,
        evidence_count=3,
        claim_count=3,
        metrics=_passing_metrics(),
        fixed_eval_pass=True,
        human_approval=HumanApprovalVerdict(
            allowed=False,
            fail_class="BLOCK_HUMAN_APPROVAL_MISSING",
            config_digest=None,
            approval_scope_digest=None,
            kill_switch_enabled=False,
        ),
    )

    assert decision.status == "REAL_CANDIDATE"
    assert decision.real_claim_allowed is False
    assert decision.human_approval_required is True
