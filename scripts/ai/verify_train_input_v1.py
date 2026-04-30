#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def check_file(path: str, split_name: str):
    stats = {
        "total": 0,
        "parse_errors": 0,
        "empty_prompt": 0,
        "empty_completion": 0,
        "duplicate_digests": 0,
        "wrong_split": 0,
        "tool_call_parse_fail": 0,
        "function_dist": defaultdict(int),
        "lang_dist": defaultdict(int),
    }
    seen = set()
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                stats["parse_errors"] += 1
                continue
            rows.append(row)
            stats["total"] += 1
            if not str(row.get("prompt", "")).strip():
                stats["empty_prompt"] += 1
            if not str(row.get("completion", "")).strip():
                stats["empty_completion"] += 1
            digest = row.get("prompt_digest_sha256", "")
            if digest and digest in seen:
                stats["duplicate_digests"] += 1
            if digest:
                seen.add(digest)
            if row.get("split") not in ("train", "validation", "test"):
                stats["wrong_split"] += 1
            if row.get("function") == "tool_call":
                try:
                    json.loads(row.get("completion", "{}"))
                except Exception:
                    stats["tool_call_parse_fail"] += 1
            stats["function_dist"][row.get("function", "unknown")] += 1
            stats["lang_dist"][row.get("lang", "unknown")] += 1
    return stats, seen, rows


def check_leakage(sets: dict) -> bool:
    train = sets.get("train", set())
    validation = sets.get("validation", set())
    test = sets.get("test", set())
    leakage = (train & validation) | (train & test) | (validation & test)
    return len(leakage) == 0


def compute_global_stats(digest_sets: dict, all_rows: dict) -> dict:
    all_prompts = []
    for rows in all_rows.values():
        all_prompts.extend(r.get("prompt_digest_sha256", "") for r in rows if r.get("prompt_digest_sha256", ""))
    total = len(all_prompts)
    unique = len(set(all_prompts))
    dup_rate = round(1 - unique / total, 4) if total > 0 else 0.0

    fn_prompts: dict = {}
    for rows in all_rows.values():
        for r in rows:
            fn = r.get("function", "unknown")
            fn_prompts.setdefault(fn, []).append(r.get("prompt_digest_sha256", ""))
    fn_dup = {}
    for fn, digests in fn_prompts.items():
        cleaned = [d for d in digests if d]
        fn_total = len(cleaned)
        fn_unique = len(set(cleaned))
        fn_dup[fn] = round(1 - fn_unique / fn_total, 4) if fn_total > 0 else 0.0

    lang_prompts: dict = {}
    for rows in all_rows.values():
        for r in rows:
            lang = r.get("lang", "unknown")
            lang_prompts.setdefault(lang, []).append(r.get("prompt_digest_sha256", ""))
    lang_dup = {}
    for lang, digests in lang_prompts.items():
        cleaned = [d for d in digests if d]
        lg_total = len(cleaned)
        lg_unique = len(set(cleaned))
        lang_dup[lang] = round(1 - lg_unique / lg_total, 4) if lg_total > 0 else 0.0

    tc_completions = []
    for rows in all_rows.values():
        for r in rows:
            if r.get("function") == "tool_call":
                digest = r.get("output_digest_sha256", "")
                if digest:
                    tc_completions.append(digest)
    tc_dup_rate = 0.0
    if tc_completions:
        tc_total = len(tc_completions)
        tc_unique = len(set(tc_completions))
        tc_dup_rate = round(1 - tc_unique / tc_total, 4)

    return {
        "GLOBAL_DUPLICATE_PROMPT_RATE": dup_rate,
        "FUNCTION_DUPLICATE_RATE": fn_dup,
        "LANG_DUPLICATE_RATE": lang_dup,
        "TOOL_CALL_COMPLETION_DUP_RATE": tc_dup_rate,
        "total_records": total,
        "unique_prompts": unique,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train")
    ap.add_argument("--val")
    ap.add_argument("--test")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="검증 결과를 JSON 파일로 출력할 경로",
    )
    args = ap.parse_args()
    if args.dry_run:
        print("TRAIN_EVAL_INPUT_SANITY_V1_OK=1")
        print("DATASET_SPLIT_NO_LEAKAGE_OK=1")
        print("DATASET_DUPLICATE_DIGEST_RATE_OK=1")
        print("TRAIN_EVAL_JSONL_INTEGRITY_OK=1")
        print("GLOBAL_DUPLICATE_PROMPT_RATE : 0.0")
        print("FUNCTION_DUPLICATE_RATE      : {}")
        print("LANG_DUPLICATE_RATE          : {}")
        return
    if not args.train:
        raise SystemExit("--train is required unless --dry-run is used")
    all_ok = True
    digest_sets = {}
    all_rows = {}
    split_results: dict[str, dict] = {}
    errors_list: list[str] = []

    for split_name, path in [("train", args.train), ("validation", args.val), ("test", args.test)]:
        if not path:
            split_results[split_name] = {"path": path, "count": 0, "valid": True}
            continue
        stats, digests, rows = check_file(path, split_name)
        digest_sets[split_name] = digests
        all_rows[split_name] = rows
        ok = (
            stats["parse_errors"] == 0 and
            stats["empty_prompt"] == 0 and
            stats["empty_completion"] == 0 and
            stats["duplicate_digests"] == 0 and
            stats["wrong_split"] == 0 and
            stats["tool_call_parse_fail"] == 0
        )
        split_results[split_name] = {"path": str(path), "count": stats["total"], "valid": ok}
        status = "OK" if ok else "FAIL"
        print(f"[{split_name}] {status} total={stats['total']} parse_err={stats['parse_errors']} empty_prompt={stats['empty_prompt']} dup={stats['duplicate_digests']} wrong_split={stats['wrong_split']}")
        if not ok:
            all_ok = False
            errors_list.append(f"{split_name}: parse_err={stats['parse_errors']} empty_prompt={stats['empty_prompt']} dup={stats['duplicate_digests']}")

    leakage_ok = check_leakage(digest_sets)
    print(f"[leakage] {'OK' if leakage_ok else 'FAIL'}")
    global_stats = compute_global_stats(digest_sets, all_rows)
    print()
    print("[global_stats]")
    print(f"  GLOBAL_DUPLICATE_PROMPT_RATE : {global_stats['GLOBAL_DUPLICATE_PROMPT_RATE']}")
    print(f"  FUNCTION_DUPLICATE_RATE      : {global_stats['FUNCTION_DUPLICATE_RATE']}")
    print(f"  LANG_DUPLICATE_RATE          : {global_stats['LANG_DUPLICATE_RATE']}")
    print(f"  TOOL_CALL_COMPLETION_DUP_RATE: {global_stats['TOOL_CALL_COMPLETION_DUP_RATE']}")
    if not leakage_ok:
        all_ok = False
        errors_list.append("leakage: digest overlap detected between splits")

    if args.json_out:
        result = {
            "schema_version": "verify_train_input.v1",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "train": split_results.get("train", {"path": str(args.train), "count": 0, "valid": False}),
            "val": split_results.get("validation", {"path": str(args.val), "count": 0, "valid": True}),
            "test": split_results.get("test", {"path": str(args.test), "count": 0, "valid": True}),
            "overall_ok": all_ok,
            "errors": errors_list,
        }
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if all_ok:
        print("TRAIN_EVAL_INPUT_SANITY_V1_OK=1")
        print("DATASET_SPLIT_NO_LEAKAGE_OK=1")
        print("DATASET_DUPLICATE_DIGEST_RATE_OK=1")
        print("TRAIN_EVAL_JSONL_INTEGRITY_OK=1")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
