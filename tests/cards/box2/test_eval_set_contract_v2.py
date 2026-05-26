import json
import re
from pathlib import Path

from butler_pc_core.cards.box2.evaluator import REQUIRED_FIELDS, RAW_FORBIDDEN_KEYS, inspect_eval_set


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _rows():
    root = Path(__file__).resolve().parents[3]
    path = root / "data/box2_helper3_eval/eval_cases.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_eval_set_option_a_has_minimum_20_cases():
    assert len(_rows()) >= 20


def test_eval_rows_are_digest_only_and_have_no_raw_text_keys():
    for row in _rows():
        assert RAW_FORBIDDEN_KEYS.isdisjoint(row.keys())
        for key in ("foreign_doc_digest", "our_format_digest", "semantic_checklist_digest", "format_marker_digest"):
            assert DIGEST_RE.match(row[key]), (row["case_id"], key)


def test_eval_rows_have_required_8_output_fields():
    for row in _rows():
        assert row["required_fields"] == REQUIRED_FIELDS


def test_eval_metrics_declares_no_mock_result_and_sample_count_20():
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "evidence/box2_helper3/eval_metrics.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "box2.helper3.eval.v2"
    assert payload["sample_count"] == 20
    assert payload["mock_result"] is False
    assert payload["raw_text_included"] is False


def test_eval_set_inspector_passes_contract():
    root = Path(__file__).resolve().parents[3]
    report = inspect_eval_set(root / "data/box2_helper3_eval/eval_cases.jsonl")
    assert report.status == "PASS_V2_EVAL_SET_CONTRACT"
    assert report.sample_count == 20
    assert report.raw_text_included is False
