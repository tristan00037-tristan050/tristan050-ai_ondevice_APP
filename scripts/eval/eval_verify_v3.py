from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.eval.eval_basic_v3 import compute_bleu4, run_basic_eval
from scripts.eval.eval_dataset_validator_v1 import validate_eval_dataset
from scripts.eval.eval_domain_v3 import DOMAIN_EVAL_SETS, run_domain_eval
from scripts.eval.eval_judge_rule_v1 import judge
from scripts.eval.eval_judge_v3 import load_hardcase_records, run_hardcase_eval
from scripts.eval.eval_safety_v3 import run_safety_eval


def _sample_row(i: int, domain: str, sensitive: bool = False) -> dict:
    return {
        "prompt": f"{domain} prompt {i}",
        "completion": f"{domain} completion {i}",
        "domain": domain,
        "case_id": f"{domain}-{i}",
        "difficulty": "adversarial" if sensitive else "medium",
        "policy_sensitive": sensitive,
    }


def verify() -> dict:
    report = []

    required = [
        "scripts/eval/__init__.py",
        "scripts/eval/eval_basic_v3.py",
        "scripts/eval/eval_domain_v3.py",
        "scripts/eval/eval_safety_v3.py",
        "scripts/eval/eval_regression_v3.py",
        "scripts/eval/eval_dataset_validator_v1.py",
        "scripts/eval/eval_judge_rule_v1.py",
        "scripts/eval/eval_judge_v3.py",
        "scripts/eval/eval_runner_v3.py",
        "scripts/eval/eval_report_v3.py",
        "scripts/eval/eval_verify_v3.py",
        "scripts/eval/run_eval_v3.sh",
        "README_EVAL_KO.md",
        "data/eval/butler_eval_v3.jsonl",
        "data/eval/butler_hardcase_v1.jsonl",
    ]
    for rel in required:
        ok = Path(rel).exists()
        report.append({"check": f"exists:{rel}", "ok": ok})
        print(f"[{'PASS' if ok else 'FAIL'}] {rel}")

    bleu_identity = compute_bleu4("버틀러는 기업용 AI입니다", "버틀러는 기업용 AI입니다")
    bleu_ok = bleu_identity >= 0.9
    report.append({"check": "bleu_identity", "bleu": bleu_identity, "ok": bleu_ok})
    print(f"[{'PASS' if bleu_ok else 'FAIL'}] BLEU identity: {bleu_identity:.3f}")

    domain_counts_ok = all(len(scenarios) >= 10 for scenarios in DOMAIN_EVAL_SETS.values())
    report.append({"check": "domain_scenarios>=10", "counts": {d: len(v) for d, v in DOMAIN_EVAL_SETS.items()}, "ok": domain_counts_ok})
    print(f"[{'PASS' if domain_counts_ok else 'FAIL'}] 도메인 시나리오 10개 이상")

    basic = run_basic_eval(None, None, [], dry_run=True)
    report.append({"check": "basic_dry_run", "ok": basic.passed})
    print(f"[{'PASS' if basic.passed else 'FAIL'}] basic dry-run")

    domain = run_domain_eval(None, None, dry_run=True)
    report.append({"check": "domain_dry_run", "ok": domain.all_passed})
    print(f"[{'PASS' if domain.all_passed else 'FAIL'}] domain dry-run")

    sample_row = domain.scenario_results["legal"][0]
    judge_fields_ok = {"judge_score", "judge_source", "judge_confidence", "final_score"}.issubset(sample_row.keys())
    rule_source_ok = sample_row.get("judge_source") == "rule_v1" and sample_row.get("judge_score") is not None
    report.append({"check": "domain_judge_fields", "ok": judge_fields_ok})
    report.append({"check": "domain_rule_source", "ok": rule_source_ok})
    print(f"[{'PASS' if judge_fields_ok else 'FAIL'}] domain judge fields")
    print(f"[{'PASS' if rule_source_ok else 'FAIL'}] domain rule source actual")

    safety = run_safety_eval(None, None, [], dry_run=True)
    report.append({"check": "safety_dry_run", "ok": safety.passed})
    print(f"[{'PASS' if safety.passed else 'FAIL'}] safety dry-run")

    rule_result = judge("근로기준법에 따라 1년 이상 근무 시 15일 연차가 발생합니다.", "legal")
    rule_ok = rule_result.source == "rule_v1" and rule_result.score > 0.3 and rule_result.passed
    report.append({"check": "rule_judge_dry_run", "ok": rule_ok, "score": rule_result.score, "source": rule_result.source})
    print(f"[{'PASS' if rule_ok else 'FAIL'}] rule judge: {rule_result.score:.3f}")

    validator = validate_eval_dataset("data/eval/butler_eval_v3.jsonl")
    report.append({"check": "dataset_validator_real", "ok": validator.ok, "rows": validator.total_rows})
    print(f"[{'PASS' if validator.ok else 'FAIL'}] dataset validator(real): {validator.total_rows} rows")

    hardcase_rows = load_hardcase_records("data/eval/butler_hardcase_v1.jsonl")
    hardcase_total = len(hardcase_rows)
    hardcase_refusal = sum(1 for row in hardcase_rows if row.get("must_refuse"))
    hardcase_shape_ok = hardcase_total >= 50 and hardcase_refusal >= 15
    report.append({"check": "hardcase_dataset_constraints", "ok": hardcase_shape_ok, "total": hardcase_total, "must_refuse": hardcase_refusal})
    print(f"[{'PASS' if hardcase_shape_ok else 'FAIL'}] hardcase dataset: total={hardcase_total}, must_refuse={hardcase_refusal}")

    hardcase_dry = run_hardcase_eval(None, None, hardcase_rows, dry_run=True)
    hardcase_dry_ok = hardcase_dry.passed and hardcase_dry.total_cases >= 50 and hardcase_dry.adversarial_total >= 15
    report.append({"check": "hardcase_dry_run", "ok": hardcase_dry_ok, "passed_ratio": hardcase_dry.passed_ratio})
    print(f"[{'PASS' if hardcase_dry_ok else 'FAIL'}] hardcase dry-run")

    with tempfile.TemporaryDirectory() as td:
        sample_path = Path(td) / "sample_eval.jsonl"
        rows = []
        idx = 0
        for domain_name in ["legal", "finance", "medical", "admin", "general"]:
            for _ in range(30):
                rows.append(_sample_row(idx, domain_name, sensitive=(idx < 30)))
                idx += 1
        sample_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        sample_validator = validate_eval_dataset(str(sample_path))
    sample_validator_ok = sample_validator.ok and sample_validator.total_rows == 150
    report.append({"check": "dataset_validator_sample", "ok": sample_validator_ok, "rows": sample_validator.total_rows})
    print(f"[{'PASS' if sample_validator_ok else 'FAIL'}] dataset validator(sample): {sample_validator.total_rows} rows")

    all_pass = all(item.get("ok", False) for item in report)
    Path("tmp").mkdir(exist_ok=True)
    out = {
        "report": report,
        "all_pass": all_pass,
        "dataset_rows": validator.total_rows,
        "dataset_digest": validator.dataset_digest,
        "dataset_per_domain": validator.per_domain,
        "hardcase_rows": hardcase_total,
        "hardcase_refusal_rows": hardcase_refusal,
        "hardcase_bucket_counts": hardcase_dry.bucket_counts,
        "sample_validator_rows": sample_validator.total_rows,
        "rule_judge_score": rule_result.score,
    }
    Path("tmp/eval_verify_result.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    if all_pass:
        print("EVAL_VERIFY_OK=1")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="호환용 플래그")
    ap.parse_args()
    result = verify()
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
