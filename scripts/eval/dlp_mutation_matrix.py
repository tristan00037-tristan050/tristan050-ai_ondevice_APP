#!/usr/bin/env python3
"""Strict digest-only evaluator for the GroupA DLP JSONL corpus.

The adapter intentionally supports no guessed aliases. Run dlp_corpus_schema_probe.py
first, then update EXACT_KEYS only after the corpus owner confirms its schema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from butler_pc_core.dlp import scan_runtime

SCHEMA_VERSION = "butler.dlp_mutation_matrix_result.v1"
CORPUS_SCHEMA_VERSION = "butler.dlp_mutation_case.v1"
EXACT_KEYS = frozenset({"schema_version", "case_id", "text", "expected_detected", "expected_category"})
ALLOWED_CATEGORIES = {"email", "phone", "korean_rrn", "card_or_account", "secret", "local_path", "none"}


class CorpusSchemaError(ValueError):
    pass


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _parse_row(line: bytes) -> dict[str, Any]:
    row = json.loads(line)
    if not isinstance(row, dict) or set(row) != EXACT_KEYS:
        raise CorpusSchemaError("CORPUS_SCHEMA_UNKNOWN")
    if row["schema_version"] != CORPUS_SCHEMA_VERSION:
        raise CorpusSchemaError("CORPUS_SCHEMA_VERSION_INVALID")
    if not isinstance(row["case_id"], str) or not row["case_id"]:
        raise CorpusSchemaError("CASE_ID_INVALID")
    if not isinstance(row["text"], str):
        raise CorpusSchemaError("TEXT_INVALID")
    if type(row["expected_detected"]) is not bool:
        raise CorpusSchemaError("EXPECTED_DETECTED_INVALID")
    if row["expected_category"] not in ALLOWED_CATEGORIES:
        raise CorpusSchemaError("EXPECTED_CATEGORY_INVALID")
    return row


def evaluate(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    total = misses = false_positives = category_mismatches = 0
    latencies_ns: list[int] = []
    category_counts: dict[str, int] = {}
    for line in data.splitlines():
        if not line.strip():
            continue
        row = _parse_row(line)
        started = time.perf_counter_ns()
        result = scan_runtime(row["text"])
        latencies_ns.append(time.perf_counter_ns() - started)
        detected = result.any_detected
        categories = {finding.category for finding in result.findings}
        total += 1
        if row["expected_detected"] and not detected:
            misses += 1
        if not row["expected_detected"] and detected:
            false_positives += 1
        expected_category = row["expected_category"]
        if expected_category != "none" and detected and expected_category not in categories:
            category_mismatches += 1
        for category in categories:
            category_counts[category] = category_counts.get(category, 0) + 1
    sorted_ms = sorted(value / 1_000_000 for value in latencies_ns)
    def percentile(p: float) -> float:
        if not sorted_ms:
            return 0.0
        index = max(0, min(len(sorted_ms) - 1, int(len(sorted_ms) * p) - 1))
        return sorted_ms[index]
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus_digest": _digest(data),
        "case_count": total,
        "miss_count": misses,
        "false_positive_count": false_positives,
        "category_mismatch_count": category_mismatches,
        "category_detection_counts": dict(sorted(category_counts.items())),
        "latency_p95_ms": round(percentile(0.95), 3),
        "latency_p99_ms": round(percentile(0.99), 3),
        "raw_text_logged": False,
        "external_send_zero": True,
        "ok": total > 0 and misses == 0 and false_positives == 0 and category_mismatches == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(args.corpus)
    except (json.JSONDecodeError, CorpusSchemaError) as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "corpus_digest": _digest(args.corpus.read_bytes()),
            "case_count": 0,
            "error_code": str(exc),
            "raw_text_logged": False,
            "external_send_zero": True,
            "ok": False,
        }
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
