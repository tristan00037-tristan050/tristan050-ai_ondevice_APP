from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGE_SPECS = {
    "stage_01": {
        "key": "ADAPTER_EXISTS",
        "patterns": ["adapter_model.safetensors"],
        "kind": "file_exists",
    },
    "stage_02": {
        "key": "TRAIN_RUN_PLAN_OK",
        "patterns": ["ai20_train_run_plan.json", "*train_run_plan*.json"],
        "kind": "text_key",
        "expected": "TRAIN_RUN_PLAN_OK=1",
    },
    "stage_03": {
        "key": "ADAPTER_CONFIG_OK",
        "patterns": ["adapter_config.json"],
        "kind": "json_field",
        "field": "base_model_name_or_path",
        "expected": "Qwen/Qwen3-4B",
    },
    "stage_04": {
        "key": "LOCAL_LOAD_SMOKE_OK",
        "patterns": [
            "*local_load*smoke*stdout*.txt",
            "*local_load*smoke*result*.json",
            "*ai26*local*load*stdout*.txt",
            "*ai26*local*result*.json",
        ],
        "kind": "text_key",
        "expected": "LOCAL_LOAD_SMOKE_OK=1",
        "search_root": "tmp",
    },
    "stage_05": {
        "key": "OUTPUT_FORMAT_OK",
        "patterns": [
            "*output_format*smoke*stdout*.txt",
            "*output_format*result*.json",
            "*ai26*output*format*stdout*.txt",
        ],
        "kind": "text_key",
        "expected": "OUTPUT_FORMAT_SMOKE_OK=1",
        "search_root": "tmp",
    },
    "stage_06": {
        "key": "EVAL_6FUNC_OK",
        "patterns": [
            "*eval_6func*result*.json",
            "*ai26*eval*6func*result*.json",
            "*eval*6func*stdout*.txt",
        ],
        "kind": "text_key",
        "expected": "EVAL_6FUNC_OK=1",
        "search_root": "tmp",
    },
    "stage_07": {
        "key": "BASE_VS_FT_OK",
        "patterns": [
            "*base_vs_ft*result*.json",
            "*compare*base*ft*result*.json",
            "*ai27*compare*result*.json",
        ],
        "kind": "text_key",
        "expected": "BASE_VS_FT_OK=1",
        "search_root": "tmp",
    },
    "stage_08": {
        "key": "JUDGE_HARDCASE_OK",
        "patterns": [
            "*judge*hardcase*result*.json",
            "*ai24*judge*result*.json",
            "*judge*hardcase*stdout*.txt",
        ],
        "kind": "text_key",
        "expected": "JUDGE_HARDCASE_OK=1",
        "search_root": "tmp",
    },
    "stage_09": {
        "key": "PHASE_C_OK",
        "patterns": [
            "*phase_c*result*.json",
            "*phase_c*verification*result*.json",
            "*phase_c*stdout*.txt",
        ],
        "kind": "text_key",
        "expected": "PHASE_C_VERIFICATION_OK=1",
        "search_root": "tmp",
    },
    "stage_10": {
        "key": "DUAL_MODEL_OK",
        "patterns": [
            "*dual_model*result*.json",
            "*dual_model*verify*result*.json",
            "*dual_model*stdout*.txt",
        ],
        "kind": "text_key",
        "expected": "DUAL_MODEL_VERIFY_OK=1",
        "search_root": "tmp",
    },
}

SELF_EXCLUDE_FILENAMES = {
    "final_verdict_pytest_output.txt",
    "final_verdict_stdout.txt",
    "butler_final_report.json",
    "butler_final_report_pass.json",
    "butler_final_report_fail.json",
}

FAIL_CODE_ORDER = [
    "stage_N_file_missing",
    "stage_N_key_not_found",
    "stage_N_value_mismatch",
    "stage_N_parse_error",
    "stage_N_scan_error",
    "stage_N_multiple_conflict",
    "report_schema_error",
    "stdout_contract_error",
]

RAW_TEXT_PATTERNS = ["prompt", "output", "completion", "messages"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_to_base(base_dir: Path, fp: Path) -> str:
    try:
        return str(fp.relative_to(base_dir))
    except Exception:
        return str(fp)


def _find_candidates(base_dir: Path, spec: dict[str, Any]) -> list[Path]:
    root = base_dir / spec.get("search_root", ".")
    if not root.exists():
        return []
    found: list[Path] = []
    for pattern in spec["patterns"]:
        candidates = sorted(root.rglob(pattern))
        candidates = [f for f in candidates if f.name not in SELF_EXCLUDE_FILENAMES]
        found.extend(candidates)
    # only files
    uniq: list[Path] = []
    seen = set()
    for fp in found:
        if fp.is_file() and fp not in seen:
            seen.add(fp)
            uniq.append(fp)
    return uniq


def _text_contains_expected(fp: Path, expected: str) -> tuple[bool, str]:
    text = fp.read_text(encoding="utf-8", errors="ignore")
    if expected in text:
        return True, text
    if fp.suffix.lower() == ".json" and "=" in expected:
        key, expected_val = expected.split("=", 1)
        try:
            data = json.loads(text)
            actual = data.get(key)
            if str(actual) == expected_val:
                return True, text
        except Exception:
            pass
    return False, text


def _json_matches_field(fp: Path, field: str, expected: Any) -> tuple[str, str]:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        return "parse_error", str(e)
    if field not in data:
        return "key_not_found", ""
    if data[field] != expected:
        return "value_mismatch", repr(data[field])
    return "pass", ""


def _sanitize_evidence(text: str) -> str:
    text = text.strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text[:200]


def collect_stage_results(base_dir: str | Path) -> dict[str, Any]:
    base = Path(base_dir)
    stages: dict[str, Any] = {}
    files_scanned = 0
    parse_errors = 0
    patterns_checked = len(STAGE_SPECS)

    for stage_name, spec in STAGE_SPECS.items():
        stage_num = stage_name.split("_")[-1]
        fail_prefix = f"stage_{stage_num}"
        try:
            candidates = _find_candidates(base, spec)
            files_scanned += len(candidates)
        except Exception as e:
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": _sanitize_evidence(str(e)),
                "source": None,
                "fail_code": f"{fail_prefix}_scan_error",
            }
            continue

        if not candidates:
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": "evidence file missing",
                "source": None,
                "fail_code": f"{fail_prefix}_file_missing",
            }
            continue

        passes = []
        mismatches = []
        parse_errs = []
        key_misses = []
        for fp in candidates:
            if spec["kind"] == "file_exists":
                passes.append((fp, "file exists"))
                continue
            if spec["kind"] == "text_key":
                ok, text = _text_contains_expected(fp, spec["expected"])
                if ok:
                    passes.append((fp, spec["expected"]))
                else:
                    mismatches.append((fp, text[:120]))
                continue
            if spec["kind"] == "json_field":
                status, payload = _json_matches_field(fp, spec["field"], spec["expected"])
                if status == "pass":
                    passes.append((fp, f"{spec['field']}={spec['expected']}"))
                elif status == "key_not_found":
                    key_misses.append((fp, spec["field"]))
                elif status == "value_mismatch":
                    mismatches.append((fp, payload))
                else:
                    parse_errs.append((fp, payload))

        if len(passes) == 1:
            fp, ev = passes[0]
            stages[stage_name] = {
                "key": spec["key"],
                "status": "pass",
                "evidence": _sanitize_evidence(ev),
                "source": _relative_to_base(base, fp),
                "fail_code": None,
            }
        elif len(passes) > 1:
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": "multiple conflicting evidence files",
                "source": [_relative_to_base(base, fp) for fp, _ in passes[:5]],
                "fail_code": f"{fail_prefix}_multiple_conflict",
            }
        elif key_misses:
            fp, missing = key_misses[0]
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": _sanitize_evidence(f"missing key: {missing}"),
                "source": _relative_to_base(base, fp),
                "fail_code": f"{fail_prefix}_key_not_found",
            }
        elif parse_errs:
            parse_errors += len(parse_errs)
            fp, err = parse_errs[0]
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": _sanitize_evidence(f"parse error: {err}"),
                "source": _relative_to_base(base, fp),
                "fail_code": f"{fail_prefix}_parse_error",
            }
        elif mismatches:
            fp, got = mismatches[0]
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": _sanitize_evidence(f"value mismatch: {got}"),
                "source": _relative_to_base(base, fp),
                "fail_code": f"{fail_prefix}_value_mismatch",
            }
        else:
            stages[stage_name] = {
                "key": spec["key"],
                "status": "fail",
                "evidence": "unknown scan error",
                "source": None,
                "fail_code": f"{fail_prefix}_scan_error",
            }

    return {
        "schema_version": "2.0",
        "generated_at": _utc_now_iso(),
        "base_dir": str(base_dir),
        "scanner_summary": {
            "files_scanned": files_scanned,
            "patterns_checked": patterns_checked,
            "parse_errors": parse_errors,
        },
        "stages": stages,
    }


def evaluate_final_verdict(stage_results: dict[str, Any], strict: bool) -> dict[str, Any]:
    stages = stage_results["stages"]
    fail_codes = [v["fail_code"] for v in stages.values() if v.get("fail_code")]
    pass_count = sum(1 for v in stages.values() if v["status"] == "pass")
    fail_count = len(stages) - pass_count
    verdict = "pass" if (pass_count == 10 if strict else pass_count >= 1 and fail_count == 0) else "fail"
    report = {
        "schema_version": stage_results["schema_version"],
        "generated_at": stage_results["generated_at"],
        "base_dir": stage_results["base_dir"],
        "execution_mode": "dry_run",
        "evidence_kind": "structure_only",
        "scanner_summary": stage_results["scanner_summary"],
        "stages": stages,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "fail_codes": fail_codes,
        "butler_final_verdict": verdict,
    }
    return report


def write_final_report(report: dict[str, Any], json_out: str | Path) -> None:
    required_top = {
        "schema_version", "generated_at", "base_dir", "execution_mode", "evidence_kind",
        "scanner_summary", "stages", "pass_count", "fail_count", "fail_codes", "butler_final_verdict"
    }
    if not required_top.issubset(report.keys()):
        report.setdefault("fail_codes", []).append("report_schema_error")
        report["butler_final_verdict"] = "fail"
    Path(json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def run_final_verdict(base_dir: str | Path, json_out: str | Path, dry_run: bool, strict: bool) -> int:
    stage_results = collect_stage_results(base_dir)
    report = evaluate_final_verdict(stage_results, strict)
    report["execution_mode"] = "dry_run" if dry_run else "real"
    report["evidence_kind"] = "structure_only" if dry_run else "collected_real_evidence"
    write_final_report(report, json_out)

    stages = report["stages"]
    for idx in range(1, 11):
        stage_name = f"stage_{idx:02d}"
        print(f"FINAL_VERDICT_STAGE_{idx:02d}={stages[stage_name]['status']}")
    print(f"FINAL_VERDICT_PASS_COUNT={report['pass_count']}")
    print(f"FINAL_VERDICT_FAIL_COUNT={report['fail_count']}")
    if report["butler_final_verdict"] not in {"pass", "fail"}:
        print("BUTLER_FINAL_VERDICT=fail")
        return 1
    print(f"BUTLER_FINAL_VERDICT={report['butler_final_verdict']}")
    return 0 if report["butler_final_verdict"] == "pass" else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default=".")
    ap.add_argument("--json-out", default="tmp/butler_final_report.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_final_verdict(args.base_dir, args.json_out, args.dry_run, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
