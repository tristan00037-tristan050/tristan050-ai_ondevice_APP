from __future__ import annotations

import os
from pathlib import Path

from butler_pc_core.cards.box3.final_gate import evaluate_final_real_gate
from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig, evaluate_human_approval
from butler_pc_core.cards.box3.real_contracts import Box3RealMetrics, sha256_text
from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerConfig, verify_box3_real_runner_assets


def _metrics() -> Box3RealMetrics:
    return Box3RealMetrics(
        unsupported_claim_rate=0.0,
        no_evidence_claim_rate=0.0,
        citation_accuracy=1.0,
        format_compliance=1.0,
        style_compliance=0.75,
        table_figure_coverage=1.0,
        factual_claim_count=1,
        unsupported_count=0,
        no_evidence_count=0,
        supported_count=1,
    )


def test_runner_asset_requires_base_full_sha(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_text("model", encoding="utf-8")
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    cfg = Box3RealRunnerConfig(runner_id="r", model_choice="qwen3-1.7b-v4-rt", model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH")
    verdict = verify_box3_real_runner_assets(cfg)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_ASSET_INVENTORY_NOT_PASS"


def test_runner_asset_cannot_bypass_central_inventory_with_matching_sha(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_text("model", encoding="utf-8")
    expected = sha256_text("model").split(":", 1)[1]
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    cfg = Box3RealRunnerConfig(
        runner_id="r",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=expected,
        readonly_required=False,
    )
    verdict = verify_box3_real_runner_assets(cfg)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_ASSET_INVENTORY_NOT_PASS"


def test_final_gate_blocks_when_central_inventory_is_missing(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_text("model", encoding="utf-8")
    expected = sha256_text("model").split(":", 1)[1]
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    cfg = Box3RealRunnerConfig(
        runner_id="r",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=expected,
        readonly_required=False,
    )
    asset = verify_box3_real_runner_assets(cfg)
    human = evaluate_human_approval(HumanApprovalConfig(kill_switch_enabled=False))
    decision = evaluate_final_real_gate(
        asset_verdict=asset,
        policy_allowed=True,
        runner_generated=True,
        runner_fail_class=None,
        evidence_count=1,
        claim_count=1,
        metrics=_metrics(),
        fixed_eval_pass=True,
        human_approval=human,
    )
    assert decision.status == "BLOCKED"
    assert decision.real_claim_allowed is False
    assert decision.fail_class == "BLOCK_ASSET_INVENTORY_NOT_PASS"
