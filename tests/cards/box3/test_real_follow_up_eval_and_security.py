from __future__ import annotations

import json
from pathlib import Path

from butler_pc_core.cards.box3.eval.evaluate_box3_real_follow_up import evaluate_cases


def test_eval_40_verdict_only_passes():
    path = Path(__file__).resolve().parents[3] / "butler_pc_core/cards/box3/eval/box3_real_follow_up_cases_v1_1.jsonl"
    result = evaluate_cases(path)
    assert result["pass"] is True
    assert result["sample_count"] == 40
    assert result["table_or_figure_count"] >= 8
    assert result["raw_key_hits"] == []


def test_no_real_enablement_subpackage_parallel_path():
    root = Path(__file__).resolve().parents[3] / "butler_pc_core/cards/box3"
    assert not (root / "real_enablement").exists(), "ALG subpackage parallel path is forbidden"


def test_package_no_training_or_model_binary_references():
    """박스 3 본진이 학습 코드 호출(Trainer/save_pretrained)을 0건 보유함을 검증.

    `.gguf` · `.safetensors` 단어는 asset_manifest.py 의 자산 메타 표기 (PR #774 helper3
    sealed LoRA safetensors) 로만 등장 — 코드 호출 0, ref 메타. forbidden 검사 대상에서
    제외(self-doc).
    """
    root = Path(__file__).resolve().parents[3] / "butler_pc_core/cards/box3"
    joined = "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*.py"))
    for forbidden in ["Trainer(", "save_pretrained"]:
        assert forbidden not in joined


def test_evidence_digest_only_no_raw_path_secret():
    root = Path(__file__).resolve().parents[3] / "evidence/box3_real_follow_up_v1_1"
    joined = "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file())
    forbidden = ["/Users/", "/home/", "/Volumes/", "sk-proj-", "Bearer ", "raw_text", "reference_text", "draft_text"]
    assert not any(item in joined for item in forbidden)
