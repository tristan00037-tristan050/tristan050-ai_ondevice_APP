from __future__ import annotations

import json
from pathlib import Path

from butler_pc_core.cards.box3 import bundle_activation as ba


def test_helper35_safetensors_guard_blocks(tmp_path):
    model = tmp_path / ba.V9_2_R2B_MODEL_NAME
    model.write_bytes(b"not-real-model")
    (tmp_path / "helper3_format.safetensors").write_bytes(b"forbidden")
    result = ba._check_helper35_stack_zero(model, tmp_path)
    assert result.passed is False
    assert result.fail_class == "HELPER35_RUNTIME_STACK_BUNDLE_FORBIDDEN"


def test_fixed_eval_report_requires_result_not_cases(tmp_path):
    report = tmp_path / "fixed_eval_report_v1.json"
    report.write_text(json.dumps({"unsupported_count": 1, "degen_detected": False}), encoding="utf-8")
    result = ba._check_fixed_eval_report(report)
    assert result.passed is False
    assert result.fail_class == "FIXED_EVAL_UNSUPPORTED_NONZERO"


def test_fixed_eval_report_accepts_unsupported_zero_degen_false(tmp_path):
    report = tmp_path / "fixed_eval_report_v1.json"
    report.write_text(json.dumps({"unsupported_count": 0, "degen_detected": False}), encoding="utf-8")
    result = ba._check_fixed_eval_report(report)
    assert result.passed is True


def test_helper_sdk_paths_must_be_repo_internal(tmp_path):
    repo = tmp_path / "repo"
    internal = repo / "butler_pc_core" / "cards" / "box3" / "sdk" / "helper4_grounding"
    internal.mkdir(parents=True)
    assert ba._is_under_repo_internal_sdk(internal, repo) is True
    outside = tmp_path / "external_sdk"
    outside.mkdir()
    assert ba._is_under_repo_internal_sdk(outside, repo) is False


def test_verifier_report_is_not_pass_ready_without_assets(tmp_path):
    report = ba.verify_box3_bundle_activation(repo_root=tmp_path)
    assert report.pass_ready is False
    assert report.raw_text_logged is False
    assert report.external_send_zero is True


def test_model_sha_gate_checks_full_digest(tmp_path):
    model = tmp_path / ba.V9_2_R2B_MODEL_NAME
    model.write_bytes(b"small-test")
    result = ba._check_model(model)
    assert result.passed is False
    assert result.fail_class == "BOX3_V9_MODEL_SHA_MISMATCH"
    assert result.details["expected"] == ba.V9_2_R2B_Q4_SHA256_FULL
