import json

from scripts.eval.eval_dataset_validator_v1 import validate_eval_dataset


def _row(i: int, domain: str, sensitive: bool = False):
    return {
        "prompt": f"{domain} prompt {i}",
        "completion": f"{domain} completion {i}",
        "domain": domain,
        "case_id": f"{domain}-{i}",
        "difficulty": "adversarial" if sensitive else "medium",
        "policy_sensitive": sensitive,
    }


def test_dataset_validator_pass(tmp_path):
    path = tmp_path / "eval.jsonl"
    rows = []
    idx = 0
    for domain in ["legal", "finance", "medical", "admin", "general"]:
        for _ in range(30):
            rows.append(_row(idx, domain, sensitive=(idx < 30)))
            idx += 1
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    result = validate_eval_dataset(str(path))
    assert result.ok is True
    assert result.total_rows == 150


def test_dataset_validator_duplicate_prompt_fail(tmp_path):
    path = tmp_path / "eval.jsonl"
    rows = []
    idx = 0
    for domain in ["legal", "finance", "medical", "admin", "general"]:
        for _ in range(30):
            row = _row(idx, domain, sensitive=(idx < 30))
            if idx == 149:
                row["prompt"] = "legal prompt 0"
            rows.append(row)
            idx += 1
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    result = validate_eval_dataset(str(path))
    assert result.ok is False
    assert any(reason.startswith("EVAL_DATASET_DUPLICATE_PROMPT") for reason in result.fail_reasons)


def test_dataset_validator_blank_completion_fail(tmp_path):
    path = tmp_path / "eval.jsonl"
    rows = []
    idx = 0
    for domain in ["legal", "finance", "medical", "admin", "general"]:
        for _ in range(30):
            row = _row(idx, domain, sensitive=(idx < 30))
            if idx == 10:
                row["completion"] = " "
            rows.append(row)
            idx += 1
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    result = validate_eval_dataset(str(path))
    assert result.ok is False
    assert any(reason.startswith("EVAL_DATASET_MALFORMED_RECORD") for reason in result.fail_reasons)
