"""PR #716 사전 점검 — predictions.jsonl record 스키마 검증."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREDICTIONS = ROOT / "evidence/day11/mode_d/predictions.jsonl"

REQUIRED_TOP_FIELDS = ["sample_id", "pred", "verifier_error_count"]
REQUIRED_PRED_FIELDS = ["intent_type", "deadline_type", "action_required",
                        "auto_apply_allowed", "actions", "schema_valid"]


def test_predictions_record_schema():
    """predictions.jsonl 각 record 가 필수 필드 보유 (PR #715 P1 정정 영역)."""
    assert PREDICTIONS.exists(), f"predictions missing: {PREDICTIONS}"
    seen = 0
    for line in PREDICTIONS.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        for f in REQUIRED_TOP_FIELDS:
            assert f in rec, f"missing top-level field {f} in record {seen}"
        for f in REQUIRED_PRED_FIELDS:
            assert f in rec["pred"], f"missing pred.{f} in record {seen}"
        seen += 1
    assert seen == 500, f"predictions count {seen} != 500"
