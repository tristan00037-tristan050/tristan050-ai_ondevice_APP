from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_option_d_scope_seal_v5():
    manifest = json.loads(
        (ROOT / "evidence/card5_lora_v3_3/option_d_manifest_v5.json").read_text(encoding="utf-8")
    )
    assert manifest["adapter_sha"] == "5b7806bdfece1b4cee61486998a0396194562da459e23aaa2094d55474d72135"
    assert manifest["retraining"] is False
    assert manifest["adapter_changed"] is False
    assert manifest["model_weight_changed"] is False
    assert manifest["evaluation_dataset_changed"] is False
    assert manifest["alias_semantics_changed"] is False
    assert sha256(ROOT / "evidence/accounting27/real_transactions_v2.jsonl") == "949b1e0072345ae73dd31ff89a3b4b4945184942ac26ac77403d66b3f96b3b57"
    assert sha256(ROOT / "src/butler/card5/canonical_alias_map.json") == "4a8c2b38999968a83515e6f80cc12c660d767801ea72e012254de1a0d24ad615"


def test_train_valid_files_not_packaged():
    forbidden = [
        ROOT / "data/train_v3_3.jsonl",
        ROOT / "data/valid_v3_3.jsonl",
        ROOT / "data/train.jsonl",
        ROOT / "data/valid.jsonl",
    ]
    assert [str(path) for path in forbidden if path.exists()] == []

