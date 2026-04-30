#!/usr/bin/env python3
"""card05_accuracy.py — card_05 통장 분류 정확도 평가 스크립트.

분류 방식: default_v2.json 키워드 매칭 (LLM 없이 오프라인 측정).
게이트 기준:
  - overall_accuracy >= 0.90
  - 카테고리별 accuracy >= 0.80
  - 절대 금지 오분류 0건
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CODES_PATH = _REPO_ROOT / "butler_pc_core/data/accounting_codes/default_v2.json"
_SAMPLES_PATH = _REPO_ROOT / "tests/fixtures/card05_bank_samples/synthetic_100.jsonl"
_OUT_DIR = _REPO_ROOT / "tmp/card05_eval"

# 절대 금지 오분류: (expected, predicted) 쌍
CRITICAL_MISCLASSIFICATIONS = {
    ("매출", "잡비"),
    ("매출", "소모품비"),
    ("매출", "비품"),
    ("급여", "접대비"),
    ("급여", "광고선전비"),
}

GATE_OVERALL = 0.90
GATE_PER_CATEGORY = 0.80


def load_codes(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def classify(description: str, amount: int, codes: dict) -> str:
    """키워드 매칭 기반 분류 (LLM 없는 오프라인 classifier).

    매칭 전략:
    1. 설명 문자열과 키워드 둘 다 공백 제거 후 비교 (한국어 복합어 대응)
    2. 최장 매칭 키워드 길이를 2차 정렬 기준으로 사용 (더 구체적인 분류 우선)
    3. 무득점 시 금액 부호로 폴백
    """
    desc_lower = description.lower()
    desc_nospace = desc_lower.replace(" ", "")
    best_match = None
    best_score = 0
    best_longest_kw = 0

    for cat_name, info in codes.items():
        if cat_name == "미분류":
            continue
        keywords: list[str] = info.get("keywords", [])
        matched_lengths = []
        for kw in keywords:
            kw_lower = kw.lower()
            kw_nospace = kw_lower.replace(" ", "")
            if kw_lower in desc_lower or kw_nospace in desc_nospace:
                matched_lengths.append(len(kw))
        score = len(matched_lengths)
        longest_kw = max(matched_lengths, default=0)
        # 1차: 매칭 개수, 2차: 최장 키워드 길이 (구체성)
        if (score, longest_kw) > (best_score, best_longest_kw):
            best_score = score
            best_longest_kw = longest_kw
            best_match = cat_name

    if best_match is None or best_score == 0:
        if amount > 0:
            return "이자수익" if "이자" in desc_lower and "수익" in desc_lower else "매출"
        return "잡비"

    return best_match


def run(
    samples_path: Path = _SAMPLES_PATH,
    codes_path: Path = _CODES_PATH,
    out_dir: Path = _OUT_DIR,
) -> dict:
    codes = load_codes(codes_path)
    rows = [json.loads(l) for l in samples_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    correct = 0
    failed_cases = []
    per_cat: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})

    for row in rows:
        expected = row["expected_category"]
        predicted = classify(row["description"], row["amount"], codes)
        per_cat[expected]["total"] += 1
        if predicted == expected:
            correct += 1
            per_cat[expected]["correct"] += 1
        else:
            failed_cases.append({
                "id": row["id"],
                "description": row["description"],
                "amount": row["amount"],
                "expected": expected,
                "predicted": predicted,
                "reason": row["ground_truth_reason"],
            })

    total = len(rows)
    overall = correct / total if total else 0.0

    per_category_accuracy = {
        cat: round(v["correct"] / v["total"], 4) if v["total"] else 0.0
        for cat, v in per_cat.items()
    }

    critical_violations = [
        fc for fc in failed_cases
        if (fc["expected"], fc["predicted"]) in CRITICAL_MISCLASSIFICATIONS
    ]

    out_dir.mkdir(parents=True, exist_ok=True)

    # per_category_accuracy.json
    (out_dir / "per_category_accuracy.json").write_text(
        json.dumps(per_category_accuracy, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # failed_cases.jsonl
    (out_dir / "failed_cases.jsonl").write_text(
        "\n".join(json.dumps(fc, ensure_ascii=False) for fc in failed_cases),
        encoding="utf-8",
    )

    # confusion_matrix.csv
    categories = sorted(per_cat.keys())
    confusion: dict[str, dict[str, int]] = {c: defaultdict(int) for c in categories}
    for row in rows:
        expected = row["expected_category"]
        predicted = classify(row["description"], row["amount"], codes)
        confusion[expected][predicted] += 1

    with open(out_dir / "confusion_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        all_preds = sorted({p for v in confusion.values() for p in v.keys()})
        writer.writerow(["expected\\predicted"] + all_preds)
        for cat in categories:
            writer.writerow([cat] + [confusion[cat].get(p, 0) for p in all_preds])

    result = {
        "total": total,
        "correct": correct,
        "overall_accuracy": round(overall, 4),
        "per_category_accuracy": per_category_accuracy,
        "failed_count": len(failed_cases),
        "critical_violations": len(critical_violations),
        "gate_overall_pass": overall >= GATE_OVERALL,
        "gate_per_category_pass": all(v >= GATE_PER_CATEGORY for v in per_category_accuracy.values()),
        "gate_critical_pass": len(critical_violations) == 0,
    }
    result["gate_all_pass"] = (
        result["gate_overall_pass"]
        and result["gate_per_category_pass"]
        and result["gate_critical_pass"]
    )

    (out_dir / "result_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="card_05 accuracy gate")
    parser.add_argument("--samples", type=Path, default=_SAMPLES_PATH)
    parser.add_argument("--codes", type=Path, default=_CODES_PATH)
    parser.add_argument("--out-dir", type=Path, default=_OUT_DIR)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    result = run(args.samples, args.codes, args.out_dir)

    print(f"overall_accuracy : {result['overall_accuracy']:.1%}  "
          f"({'PASS' if result['gate_overall_pass'] else 'FAIL'})")
    print(f"per_category min : "
          f"{min(result['per_category_accuracy'].values()):.1%}  "
          f"({'PASS' if result['gate_per_category_pass'] else 'FAIL'})")
    print(f"critical_violations: {result['critical_violations']}  "
          f"({'PASS' if result['gate_critical_pass'] else 'FAIL'})")
    print(f"gate_all_pass    : {result['gate_all_pass']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if result["gate_all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
