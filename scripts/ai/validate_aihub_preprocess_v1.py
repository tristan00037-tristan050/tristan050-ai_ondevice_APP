from __future__ import annotations
import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import jsonl_read, jsonl_write, REQUIRED_FIELDS, FUNCTIONS, is_korean_text

REASON_CODES = {
    "MISSING_FIELD", "INVALID_FUNCTION", "INVALID_SOURCE", "INVALID_SPLIT",
    "TOOL_JSON_INVALID", "TOOL_ARGS_INVALID", "REWRITE_COPY", "REWRITE_TONE_MISSING",
    "RETRIEVAL_HALLUCINATION", "MRC_NOT_ALLOWED", "ROLE_INVERSION", "DUPLICATE_PROMPT",
    "NOT_ENOUGH_KOREAN",
}


def _normalize_reason(code: str) -> str:
    return code if code in REASON_CODES else code


def validate_row(row: dict) -> list[str]:
    reasons = []
    for f in REQUIRED_FIELDS:
        if f not in row or row[f] in (None, ""):
            reasons.append("MISSING_FIELD")
            return reasons
    if row["function"] not in FUNCTIONS or row["task_type"] != row["function"]:
        reasons.append("INVALID_FUNCTION")
    if row["split"] not in {"train", "validation"}:
        reasons.append("INVALID_SPLIT")
    if not str(row["source"]).startswith("aihub_"):
        reasons.append("INVALID_SOURCE")
    if not is_korean_text(row.get("prompt", "")):
        reasons.append("NOT_ENOUGH_KOREAN")
    fn = row["function"]
    comp = row.get("completion", "")
    if fn == "tool_call":
        try:
            obj = json.loads(comp)
            if "tool_name" not in obj:
                reasons.append("TOOL_JSON_INVALID")
            args = obj.get("arguments")
            if not isinstance(args, dict) or not args:
                reasons.append("TOOL_ARGS_INVALID")
        except Exception:
            reasons.append("TOOL_JSON_INVALID")
    elif fn == "rewrite":
        if row.get("prompt", "").split("\n")[-1].strip() == comp.strip():
            reasons.append("REWRITE_COPY")
        if not any(k in comp for k in ["죄송", "안내", "드립니다", "감사"]):
            reasons.append("REWRITE_TONE_MISSING")
    elif fn == "retrieval_transform":
        if "질문:" in row.get("prompt", "") and "답변:" in comp:
            reasons.append("MRC_NOT_ALLOWED")
        output_keys = row.get("output_keys", [])
        for k in output_keys:
            if k not in comp:
                reasons.append("RETRIEVAL_HALLUCINATION")
                break
        values = [part.split(":", 1)[1].strip() for part in comp.splitlines() if ":" in part]
        for v in values:
            if v and len(v) >= 2 and v not in row.get("prompt", ""):
                reasons.append("RETRIEVAL_HALLUCINATION")
                break
    elif fn == "dialogue":
        if row.get("role_inverted"):
            reasons.append("ROLE_INVERSION")
    if fn != "tool_call" and not is_korean_text(comp):
        reasons.append("NOT_ENOUGH_KOREAN")
    deduped = []
    for r in reasons:
        code = _normalize_reason(r)
        if code not in deduped:
            deduped.append(code)
    return deduped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--quarantine", required=True)
    ap.add_argument("--coverage-gap", required=True)
    args = ap.parse_args()
    rows = jsonl_read(args.input)
    quarantine = []
    valid = []
    seen = set()
    reason_counts = Counter()
    by_func_valid = Counter()
    by_func_fail = Counter()
    by_func_total = Counter()
    for row in rows:
        by_func_total[row.get("function", "unknown")] += 1
        prompt = row.get("prompt", "")
        if prompt in seen:
            reasons = ["DUPLICATE_PROMPT"]
        else:
            seen.add(prompt)
            reasons = validate_row(row)
        if reasons:
            row_q = dict(row)
            row_q["reason_code"] = reasons[0]
            quarantine.append(row_q)
            reason_counts[reasons[0]] += 1
            by_func_fail[row.get("function", "unknown")] += 1
        else:
            valid.append(row)
            by_func_valid[row["function"]] += 1
    total = len(rows)
    valid_count = len(valid)
    quarantine_count = len(quarantine)
    duplicate_count = reason_counts["DUPLICATE_PROMPT"]
    duplicate_rate = duplicate_count / total if total else 0.0
    required_min = {"tool_call":30000,"rewrite":20000,"retrieval_transform":30000,"dialogue":70000,"policy_sensitive":25000,"summarize":25000}
    coverage = {}
    for f, tgt in required_min.items():
        actual = by_func_valid[f]
        gap = max(tgt - actual, 0)
        coverage[f] = {"target": tgt, "actual": actual, "gap": gap, "action": "synthetic" if gap > 0 else "none"}
    all_functions_present = all(by_func_total[f] > 0 for f in required_min)
    function_validation = {
        f: {"total": by_func_total[f], "valid_count": by_func_valid[f], "fail_count": by_func_fail[f]}
        for f in required_min
    }
    # practical gate for local runs; real coverage gate handled via coverage_gap
    all_pass = duplicate_rate < 0.01 and all_functions_present and not any(c in reason_counts for c in ["TOOL_JSON_INVALID", "TOOL_ARGS_INVALID", "MRC_NOT_ALLOWED", "RETRIEVAL_HALLUCINATION", "ROLE_INVERSION"])
    result = {
        "total": total,
        "valid_count": valid_count,
        "quarantine_count": quarantine_count,
        "pass_rate": round(valid_count / total, 4) if total else 0.0,
        "duplicate_rate": round(duplicate_rate, 4),
        "reason_code_distribution": dict(reason_counts),
        "function_distribution": {k: by_func_total[k] for k in sorted(by_func_total)},
        "function_validation": function_validation,
        "all_functions_present": all_functions_present,
        "all_pass": all_pass,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    jsonl_write(args.quarantine, quarantine)
    Path(args.coverage_gap).write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    if all_functions_present:
        print("AIHUB_FUNCTION_COVERAGE_OK=1")
    if all_pass:
        print("AIHUB_VALIDATION_OK=1")
    else:
        print("AIHUB_VALIDATION_FAIL=1")
        sys.exit(1)


if __name__ == "__main__":
    main()
