#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, math
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.butler.card5.alias_map import apply_canonical_alias_map, validate_tax_relevance

ADAPTER_SHA = "5b7806bdfece1b4cee61486998a0396194562da459e23aaa2094d55474d72135"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def nearest_rank(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if percentile == 50:
        n = len(ordered)
        mid = n // 2
        if n % 2:
            return float(ordered[mid])
        return float((ordered[mid - 1] + ordered[mid]) / 2)
    rank = math.ceil(percentile / 100 * len(ordered))
    idx = max(0, rank - 1)
    return float(ordered[idx])


def canonical_pairs(allowlist_path: Path) -> set[tuple[str, str]]:
    data = json.loads(allowlist_path.read_text(encoding="utf-8"))
    return {(item["name"], item["code"]) for rows in data["categories"].values() for item in rows}


def normalize_prediction(raw: dict[str, Any]) -> dict[str, Any]:
    pred = dict(raw)
    if "predicted" in pred and isinstance(pred["predicted"], dict):
        pred = dict(pred["predicted"])
    # Accept both title/code and account_title/account_code field names.
    if "title" in pred and "account_title" not in pred:
        pred["account_title"] = pred["title"]
    if "code" in pred and "account_code" not in pred:
        pred["account_code"] = pred["code"]
    pred["tax_relevance"] = validate_tax_relevance(pred.get("tax_relevance", "unknown"))
    return pred


def score(transactions: list[dict[str, Any]], predictions: dict[str, dict[str, Any]], pairs: set[tuple[str, str]], *, postprocess: bool) -> dict[str, Any]:
    total = len(transactions)
    correct = 0
    hallucinated = 0
    invalid_code = 0
    token_collapse = 0
    confidence_values: set[float] = set()
    rows = []
    corrected = []
    for tx in transactions:
        tx_id = tx["transaction_id"]
        if tx_id not in predictions:
            raise SystemExit(f"BLOCK: MISSING_PREDICTION {tx_id}")
        raw = normalize_prediction(predictions[tx_id])
        pred = apply_canonical_alias_map(tx.get("description", ""), raw) if postprocess else raw
        pair = (str(pred.get("account_title")), str(pred.get("account_code")))
        expected = (tx["expected_account_title"], tx["expected_account_code"])
        is_pair_valid = pair in pairs
        if not is_pair_valid:
            hallucinated += 1
            if str(pred.get("account_code")) not in {code for _, code in pairs}:
                invalid_code += 1
        if pair == expected:
            correct += 1
        if str(pred.get("account_title")) in {"외화차손", "외화차익", "임대매출"}:
            token_collapse += 1
        if pred.get("alias_map_applied"):
            corrected.append(tx_id)
        try:
            confidence_values.add(float(pred.get("confidence")))
        except Exception:
            pass
        rows.append({
            "transaction_id": tx_id,
            "expected": {"account_title": expected[0], "account_code": expected[1]},
            "predicted": {"account_title": pred.get("account_title"), "account_code": pred.get("account_code"), "confidence": pred.get("confidence")},
            "match": pair == expected,
            "canonical_pair_valid": is_pair_valid,
            "alias_map_applied": bool(pred.get("alias_map_applied", False)),
        })
    return {
        "accuracy": round(correct / total, 6) if total else 0.0,
        "correct": correct,
        "total": total,
        "hallucinated": hallucinated,
        "canonical_invalid_code": invalid_code,
        "confidence_unique": len(confidence_values),
        "token_collapse": token_collapse,
        "corrected_transactions": corrected,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transactions", default="evidence/accounting27/real_transactions_v2.jsonl")
    ap.add_argument("--predictions", required=True, help="JSONL with transaction_id and predicted account fields")
    ap.add_argument("--allowlist", default="src/butler/card5/account_title_allowlist_47.json")
    ap.add_argument("--alias-map", default="src/butler/card5/canonical_alias_map.json")
    ap.add_argument("--raw-out", default="evidence/accounting27/corrected_eval_raw_metrics.json")
    ap.add_argument("--post-out", default="evidence/accounting27/corrected_eval_postprocess_metrics.json")
    args = ap.parse_args()
    tx_path = Path(args.transactions)
    pred_path = Path(args.predictions)
    allow_path = Path(args.allowlist)
    alias_path = Path(args.alias_map)
    transactions = load_jsonl(tx_path)
    predictions = {str(row["transaction_id"]): row for row in load_jsonl(pred_path)}
    pairs = canonical_pairs(allow_path)
    raw = score(transactions, predictions, pairs, postprocess=False)
    post = score(transactions, predictions, pairs, postprocess=True)
    base_common = {
        "adapter_sha": ADAPTER_SHA,
        "retraining": False,
        "dataset_sha256": sha256_file(tx_path),
    }
    raw_doc = {
        "schema_version": "card5.corrected_eval_raw_metrics.v1",
        **base_common,
        "alias_map_applied": False,
        **{k: raw[k] for k in ["accuracy", "correct", "total", "hallucinated", "canonical_invalid_code", "confidence_unique", "token_collapse"]},
    }
    post_doc = {
        "schema_version": "card5.corrected_eval_postprocess_metrics.v1",
        **base_common,
        "alias_map_applied": True,
        "alias_map_sha256": sha256_file(alias_path),
        **{k: post[k] for k in ["accuracy", "correct", "total", "hallucinated", "canonical_invalid_code", "confidence_unique", "token_collapse", "corrected_transactions"]},
    }
    Path(args.raw_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.post_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.raw_out).write_text(json.dumps(raw_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.post_out).write_text(json.dumps(post_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"raw": raw_doc, "postprocess": post_doc}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
