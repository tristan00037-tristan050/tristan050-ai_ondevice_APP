#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

VALID_SPLITS = {"train", "validation", "test"}
VALID_FUNCTIONS = {"dialogue", "summarize", "rewrite", "tool_call", "policy_sensitive", "retrieval_transform"}
VALID_LANGS = {"ko", "en", "mixed"}
TYPE_MAP = {"string": str, "number": (int, float), "integer": int, "boolean": bool}


def approx_token_len(text: str) -> int:
    return max(len(text.split()), len(text) // 4)


def load_schema(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    schema = json.loads(p.read_text(encoding="utf-8"))
    tool_map = {}
    for tool in schema.get("tools", []):
        name = tool.get("name")
        if not name:
            continue
        arg_schema = tool.get("arguments", {})
        tool_map[name] = {"required": set(tool.get("required", [])), "allowed_keys": set(arg_schema.keys()), "arg_schema": arg_schema}
    schema["_tool_map"] = tool_map
    return schema


def load_rows(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["_lineno"] = lineno
            rows.append(row)
    return rows


def validate_tool_call_record(completion: str, schema: dict[str, Any] | None) -> bool:
    try:
        obj = json.loads(completion)
    except Exception:
        return False
    if schema is None:
        return True
    tool_name = obj.get("tool_name")
    registered = set(schema.get("registered_actions", []))
    tool_def = schema.get("_tool_map", {}).get(tool_name)
    if tool_name not in registered or tool_def is None:
        return False
    args = obj.get("arguments", {})
    if not isinstance(args, dict):
        return False
    required = tool_def["required"]
    allowed_keys = tool_def["allowed_keys"]
    arg_schema = tool_def["arg_schema"]
    if not required.issubset(set(args.keys())):
        return False
    if not set(args.keys()).issubset(allowed_keys):
        return False
    for key, val in args.items():
        field = arg_schema.get(key, {})
        expected_type = field.get("type")
        if expected_type in TYPE_MAP:
            if expected_type == "integer" and isinstance(val, bool):
                return False
            if not isinstance(val, TYPE_MAP[expected_type]):
                return False
        if isinstance(val, str) and val.strip() == "":
            return False
        allowed_enum = field.get("enum")
        if allowed_enum and val not in allowed_enum:
            return False
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in field and val < field["minimum"]:
                return False
            if "maximum" in field and val > field["maximum"]:
                return False
    return True


def check_split(path: str, split_name: str, max_seq_length: int, schema: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    stats: dict[str, Any] = {
        "split": split_name,
        "total": 0,
        "empty_prompt": 0,
        "empty_completion": 0,
        "wrong_split": 0,
        "duplicate_prompt_digest": 0,
        "tool_call_parse_fail": 0,
        "tool_call_schema_fail": 0,
        "over_max_seq_length": 0,
        "over_max_seq_ratio": 0.0,
        "function_dist": {},
        "lang_dist": {},
    }
    rows = load_rows(path)
    seen = set()
    digests = set()
    fn_counter = Counter()
    lang_counter = Counter()
    for row in rows:
        stats["total"] += 1
        prompt = str(row.get("prompt", "")).strip()
        completion = str(row.get("completion", "")).strip()
        if not prompt:
            stats["empty_prompt"] += 1
        if not completion:
            stats["empty_completion"] += 1
        if row.get("split") != split_name:
            stats["wrong_split"] += 1
        pd = row.get("prompt_digest_sha256", "")
        if pd:
            if pd in seen:
                stats["duplicate_prompt_digest"] += 1
            seen.add(pd)
            digests.add(pd)
        if row.get("function") == "tool_call":
            try:
                json.loads(completion)
            except Exception:
                stats["tool_call_parse_fail"] += 1
            else:
                if not validate_tool_call_record(completion, schema):
                    stats["tool_call_schema_fail"] += 1
        if approx_token_len(prompt + "\n" + completion) > max_seq_length:
            stats["over_max_seq_length"] += 1
        fn_counter[row.get("function", "unknown")] += 1
        lang_counter[row.get("lang", "unknown")] += 1
    stats["function_dist"] = dict(sorted(fn_counter.items()))
    stats["lang_dist"] = dict(sorted(lang_counter.items()))
    stats["over_max_seq_ratio"] = round(stats["over_max_seq_length"] / stats["total"], 4) if stats["total"] else 0.0
    return stats, rows, digests


def leakage_ok(digest_sets: dict[str, set[str]]) -> bool:
    train = digest_sets.get("train", set())
    validation = digest_sets.get("validation", set())
    test = digest_sets.get("test", set())
    return len((train & validation) | (train & test) | (validation & test)) == 0


def compute_global_stats(all_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    all_prompts: list[str] = []
    fn_prompts: dict[str, list[str]] = {}
    lang_prompts: dict[str, list[str]] = {}
    tc_completions: list[str] = []
    fn_counts = Counter()
    lang_counts = Counter()
    for rows in all_rows.values():
        for r in rows:
            pd = r.get("prompt_digest_sha256", "")
            if pd:
                all_prompts.append(pd)
                fn_prompts.setdefault(r.get("function", "unknown"), []).append(pd)
                lang_prompts.setdefault(r.get("lang", "unknown"), []).append(pd)
            fn_counts[r.get("function", "unknown")] += 1
            lang_counts[r.get("lang", "unknown")] += 1
            if r.get("function") == "tool_call":
                od = r.get("output_digest_sha256", "")
                if od:
                    tc_completions.append(od)
    total = len(all_prompts)
    unique = len(set(all_prompts))
    global_dup = round(1 - unique / total, 4) if total else 0.0
    fn_dup = {fn: round(1 - len(set(digests)) / len(digests), 4) if digests else 0.0 for fn, digests in fn_prompts.items()}
    lang_dup = {lang: round(1 - len(set(digests)) / len(digests), 4) if digests else 0.0 for lang, digests in lang_prompts.items()}
    tc_dup = round(1 - len(set(tc_completions)) / len(tc_completions), 4) if tc_completions else 0.0
    return {
        "GLOBAL_DUPLICATE_PROMPT_RATE": global_dup,
        "FUNCTION_DUPLICATE_RATE": dict(sorted(fn_dup.items())),
        "LANG_DUPLICATE_RATE": dict(sorted(lang_dup.items())),
        "TOOL_CALL_COMPLETION_DUP_RATE": tc_dup,
        "function_counts": dict(sorted(fn_counts.items())),
        "lang_counts": dict(sorted(lang_counts.items())),
        "FUNCTION_COVERAGE_OK": int(VALID_FUNCTIONS.issubset(set(fn_counts.keys()))),
        "LANG_COVERAGE_OK": int(VALID_LANGS.issubset(set(lang_counts.keys()))),
        "total_records": total,
        "unique_prompts": unique,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="AI-20 train input sanity verifier")
    ap.add_argument("--train", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--max-seq-length", type=int, default=2048)
    ap.add_argument("--schema", default="schemas/tool_call_schema_v3.json")
    ap.add_argument("--over-max-seq-threshold", type=float, default=0.05)
    ap.add_argument("--min-total-records", type=int, default=1000)
    ap.add_argument("--out", default="tmp/ai20_train_input_sanity_result.json")
    args = ap.parse_args()

    schema = load_schema(args.schema)
    split_stats = {}
    all_rows = {}
    digest_sets = {}
    integrity_ok = True
    for split_name, path in [("train", args.train), ("validation", args.validation), ("test", args.test)]:
        stats, rows, digests = check_split(path, split_name, args.max_seq_length, schema)
        split_stats[split_name] = stats
        all_rows[split_name] = rows
        digest_sets[split_name] = digests
        split_ok = (
            stats["empty_prompt"] == 0
            and stats["empty_completion"] == 0
            and stats["wrong_split"] == 0
            and stats["duplicate_prompt_digest"] == 0
            and stats["tool_call_parse_fail"] == 0
            and stats["tool_call_schema_fail"] == 0
        )
        print(f"[{split_name}] {'OK' if split_ok else 'FAIL'} total={stats['total']} empty_prompt={stats['empty_prompt']} empty_completion={stats['empty_completion']} dup={stats['duplicate_prompt_digest']} wrong_split={stats['wrong_split']} tool_call_parse_fail={stats['tool_call_parse_fail']} tool_call_schema_fail={stats['tool_call_schema_fail']} over_max_seq_ratio={stats['over_max_seq_ratio']}")
        integrity_ok = integrity_ok and split_ok

    leak_free = leakage_ok(digest_sets)
    print(f"[leakage] {'OK' if leak_free else 'FAIL'}")
    global_stats = compute_global_stats(all_rows)
    over_max_ratio = max((s["over_max_seq_ratio"] for s in split_stats.values()), default=0.0)
    over_max_ok = int(over_max_ratio <= args.over_max_seq_threshold)
    tool_call_strict_ok = int(all(s["tool_call_parse_fail"] == 0 and s["tool_call_schema_fail"] == 0 for s in split_stats.values()))
    scale_ready = int(global_stats["total_records"] >= args.min_total_records)
    print("[global_stats]")
    print(f"  GLOBAL_DUPLICATE_PROMPT_RATE : {global_stats['GLOBAL_DUPLICATE_PROMPT_RATE']}")
    print(f"  FUNCTION_DUPLICATE_RATE      : {global_stats['FUNCTION_DUPLICATE_RATE']}")
    print(f"  LANG_DUPLICATE_RATE          : {global_stats['LANG_DUPLICATE_RATE']}")
    print(f"  TOOL_CALL_COMPLETION_DUP_RATE: {global_stats['TOOL_CALL_COMPLETION_DUP_RATE']}")

    result = {
        "AI20_TRAIN_INPUT_SANITY_OK": int(integrity_ok and leak_free and over_max_ok and tool_call_strict_ok and global_stats["FUNCTION_COVERAGE_OK"] == 1 and global_stats["LANG_COVERAGE_OK"] == 1),
        "AI20_TRAIN_INPUT_SCALE_READY_OK": scale_ready,
        "DATASET_SPLIT_NO_LEAKAGE_OK": int(leak_free),
        "TRAIN_EVAL_JSONL_INTEGRITY_OK": int(integrity_ok),
        "TOOL_CALL_SCHEMA_STRICT_OK": tool_call_strict_ok,
        "FUNCTION_COVERAGE_OK": global_stats["FUNCTION_COVERAGE_OK"],
        "LANG_COVERAGE_OK": global_stats["LANG_COVERAGE_OK"],
        "OVER_MAX_SEQ_RATIO_OK": over_max_ok,
        "max_seq_length": args.max_seq_length,
        "over_max_seq_threshold": args.over_max_seq_threshold,
        "min_total_records": args.min_total_records,
        "split_stats": split_stats,
        **global_stats,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT_JSON={out_path}")
    if result["AI20_TRAIN_INPUT_SANITY_OK"] == 1:
        print("AI20_TRAIN_INPUT_SANITY_OK=1")
        print(f"AI20_TRAIN_INPUT_SCALE_READY_OK={scale_ready}")
        print("DATASET_SPLIT_NO_LEAKAGE_OK=1")
        print("TRAIN_EVAL_JSONL_INTEGRITY_OK=1")
        print("TOOL_CALL_SCHEMA_STRICT_OK=1")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
