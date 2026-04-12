from __future__ import annotations
import argparse, json, sys
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, summarize_fields, detect_text_candidates


def inspect_dataset(dataset_dir: str, output_dir: str, sample_count: int = 3) -> dict:
    dpath = Path(dataset_dir)
    files = find_sample_files(dpath, limit=sample_count)
    all_files = []
    for ext in ("*.json", "*.jsonl", "*.csv"):
        all_files.extend(sorted(dpath.rglob(ext)))
    report = {
        "dataset_name": dpath.name,
        "dataset_dir": str(dpath),
        "file_count": len(all_files),
        "sample_files": [str(p) for p in files],
        "sampled_files": len(files),
        "root_format": None,
        "main_fields": [],
        "sample_3": [],
        "text_candidate_fields": [],
        "label_annotation_fields": [],
        "turn_structure": None,
        "event_structure": None,
        "sql_field": False,
        "unusable_reason": None,
    }
    if not files:
        report["unusable_reason"] = "NO_SUPPORTED_FILES"
    else:
        all_fields = set()
        samples = []
        fmt = None
        unusable = []
        for fp in files:
            try:
                fmt, recs = sniff_records(fp, sample_count=sample_count)
                all_fields.update(summarize_fields(recs))
                samples.extend(recs[:1])
            except Exception as e:
                unusable.append(f"{fp.name}:{e}")
        report["root_format"] = fmt
        report["main_fields"] = sorted(all_fields)
        report["sample_3"] = samples[:3]
        report["text_candidate_fields"] = detect_text_candidates(report["main_fields"])
        report["label_annotation_fields"] = [
            f for f in report["main_fields"]
            if any(tok in f.lower() for tok in ["label", "intent", "emotion", "tag", "category", "slot"])
        ]
        lowers = [f.lower() for f in report["main_fields"]]
        report["turn_structure"] = "multi_turn" if any(tok in lowers for tok in ["speaker", "role", "utterance", "dialogue", "turns"]) else None
        report["event_structure"] = "event_like" if any(tok in lowers for tok in ["event", "participants", "location", "date", "time"]) else None
        report["sql_field"] = any("sql" in f.lower() for f in report["main_fields"])
        if unusable:
            report["unusable_reason"] = " | ".join(unusable)
    out = Path(output_dir) / f"{dpath.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _inventory_from_report(report: dict) -> dict:
    name = report["dataset_name"]
    mapping = {
        "NL2SQL": {"expected_functions": ["tool_call"], "recommended_target": 30000},
        "오피스문서생성": {"expected_functions": ["rewrite"], "recommended_target": 20000},
        "다중이벤트추출": {"expected_functions": ["retrieval_transform"], "recommended_target": 30000},
        "감성대화": {"expected_functions": ["dialogue"], "recommended_target": 30000},
        "공감형대화": {"expected_functions": ["dialogue"], "recommended_target": 20000},
        "멀티세션": {"expected_functions": ["dialogue"], "recommended_target": 20000},
        "전문분야": {"expected_functions": ["policy_sensitive", "summarize"], "recommended_target": 20000},
        "금융": {"expected_functions": ["policy_sensitive"], "recommended_target": 10000},
        "웹데이터": {"expected_functions": ["summarize", "retrieval_transform"], "recommended_target": 20000},
    }
    meta = mapping.get(name, {"expected_functions": [], "recommended_target": 0})
    risk_notes = []
    if report.get("unusable_reason"):
        risk_notes.append(report["unusable_reason"])
    if not report.get("text_candidate_fields"):
        risk_notes.append("NO_TEXT_CANDIDATES")
    if not report.get("sample_3"):
        usable_estimate = 0.0
    else:
        usable_estimate = 0.8 if not risk_notes else 0.4
    return {
        "dataset_name": name,
        "root_format": report.get("root_format"),
        "file_count": report.get("file_count", 0),
        "sampled_files": report.get("sampled_files", 0),
        "parser_candidate": report.get("text_candidate_fields", [])[:5],
        "usable_estimate": usable_estimate,
        "risk_notes": risk_notes,
        "expected_functions": meta["expected_functions"],
        "recommended_target": meta["recommended_target"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-dirs", nargs="+", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--sample-count", type=int, default=3)
    args = ap.parse_args()

    reports = [inspect_dataset(dd, args.output_dir, args.sample_count) for dd in args.dataset_dirs]
    inventory = [_inventory_from_report(r) for r in reports]
    inv_path = Path(args.output_dir).parent / "inventory_report.json"
    inv_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = len(reports) == len(args.dataset_dirs) and all((Path(args.output_dir) / f"{Path(dd).name}.json").exists() for dd in args.dataset_dirs)
    if ok:
        print("SCHEMA_SCOUTING_OK=1")
    else:
        print("SCHEMA_SCOUTING_FAIL=1")
        sys.exit(1)


if __name__ == "__main__":
    main()
