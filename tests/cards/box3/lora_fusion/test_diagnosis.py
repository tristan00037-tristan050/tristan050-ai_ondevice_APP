from __future__ import annotations

import pytest

from butler_pc_core.cards.box3.lora_fusion.diagnosis import FusionEvidenceAxis, diagnose_helper35_fusion
from butler_pc_core.cards.box3.lora_fusion.security import sha256_text


def _axis(axis, verdict, confidence=0.9):
    return FusionEvidenceAxis(axis, verdict, sha256_text(axis + verdict), confidence)


def test_diagnosis_already_fused_blocks_extra_fusion():
    verdict = diagnose_helper35_fusion([
        _axis("lineage_build", "already_fused"),
        _axis("gguf_metadata", "already_fused"),
        _axis("runner_code", "already_fused"),
        _axis("behavior_probe", "inconclusive", 0.5),
    ])
    assert verdict.diagnosis_status == "ALREADY_FUSED_CONFIRMED"
    assert verdict.fusion_allowed is False
    assert verdict.action == "DO_NOT_FUSE_REPORT_MODEL_LIMIT"


def test_diagnosis_not_fused_allows_one_fusion_path():
    verdict = diagnose_helper35_fusion([
        _axis("lineage_build", "not_fused"),
        _axis("gguf_metadata", "not_fused"),
        _axis("runner_code", "not_fused"),
        _axis("behavior_probe", "inconclusive", 0.5),
    ])
    assert verdict.diagnosis_status == "NOT_FUSED_CONFIRMED"
    assert verdict.fusion_allowed is True


def test_block_inconclusive_on_conflict():
    verdict = diagnose_helper35_fusion([
        _axis("lineage_build", "already_fused"),
        _axis("gguf_metadata", "already_fused"),
        _axis("runner_code", "not_fused"),
        _axis("behavior_probe", "inconclusive", 0.5),
    ])
    assert verdict.diagnosis_status == "INCONCLUSIVE"
    assert verdict.fusion_allowed is False


def test_block_double_fusion():
    verdict = diagnose_helper35_fusion([_axis("lineage_build", "not_fused")], previous_fusion_manifest_digest="sha256:" + "0"*64)
    assert verdict.diagnosis_status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_DOUBLE_FUSION"


def test_block_sdk_helpers_in_stack():
    verdict = diagnose_helper35_fusion([_axis("lineage_build", "not_fused")], attempted_stack_helpers=["helper4_grounding"])
    assert verdict.diagnosis_status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_SDK_HELPER_STACK_ATTEMPT"


def test_raw_evidence_zero_guard():
    with pytest.raises(ValueError):
        FusionEvidenceAxis("lineage_build", "not_fused", sha256_text("x"), 0.9, raw_saved_zero=False)
