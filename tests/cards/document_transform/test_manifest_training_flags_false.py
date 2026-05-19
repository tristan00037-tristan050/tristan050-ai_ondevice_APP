"""test_manifest_training_flags_false.py — manifest 학습 플래그 전부 false (M-60)."""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[3] / "evaluation/card2/derived_artifact_manifest.json"


def test_training_flags_false():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["raw_text_retained"] is False
    assert m["is_training_artifact"] is False
    assert m["is_retrieval_or_eval_only"] is True


def test_global_assertions_eight():
    g = json.loads(MANIFEST.read_text(encoding="utf-8"))["global_assertions"]
    assert g["ip4_auto_finetune_trigger"] == "absent"
    assert g["ip6_training_directory_diff"] == "zero"
    assert g["raw_text_external_send"] == "zero"
    assert g["openai_anthropic_gemini_calls"] == "zero"
    assert g["model_weight_changed"] is False
    assert g["tokenizer_changed"] is False
    assert g["prompt_training_changed"] is False
    assert g["rag_index_generated_in_d4_main_pr"] is False
