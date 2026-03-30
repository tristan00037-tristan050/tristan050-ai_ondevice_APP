from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from pathlib import Path

from scripts.convert.convert_budget_v1 import check_budget, get_budget_spec
from scripts.convert.convert_manifest_v1 import create_manifest
from scripts.convert.convert_ort_mobile_v1 import convert_to_ort
from scripts.convert.convert_verify_mnn_v2 import verify_mnn
from scripts.convert.convert_verify_onnx_v2 import verify_onnx


REQUIRED_FILES = [
    "scripts/convert/__init__.py",
    "scripts/convert/convert_merge_v1.py",
    "scripts/convert/convert_onnx_v2.py",
    "scripts/convert/convert_verify_onnx_v2.py",
    "scripts/convert/convert_mnn_v2.py",
    "scripts/convert/convert_verify_mnn_v2.py",
    "scripts/convert/convert_package_v2.py",
    "scripts/convert/convert_manifest_v1.py",
    "scripts/convert/convert_runner_v2.py",
    "scripts/convert/convert_ort_mobile_v1.py",
    "scripts/convert/convert_budget_v1.py",
    "scripts/convert/convert_verify_v2.py",
    "scripts/convert/run_convert_v2.sh",
    "tests/convert/conftest.py",
    "tests/convert/test_convert_ort_mobile.py",
    "tests/convert/test_convert_budget.py",
    "README_CONVERT_KO.md",
]


MANIFEST_REQUIRED_FIELDS = [
    "tokenizer_file_digests",
    "onnx_export_method",
    "mnn_stdout_digest",
    "ort_runtime_verified",
    "external_data_file_digests",
]


def verify() -> dict:
    report = []
    for file_path in REQUIRED_FILES:
        ok = Path(file_path).exists()
        report.append({"file": file_path, "ok": ok})
        print(f"[{'PASS' if ok else 'FAIL'}] {file_path}")

    r1 = verify_onnx("", dry_run=True)
    report.append({"check": "onnx_dryrun", "ok": r1["all_pass"]})
    print(f"[{'PASS' if r1['all_pass'] else 'FAIL'}] ONNX dry-run")

    r2 = verify_mnn("", dry_run=True)
    report.append({"check": "mnn_dryrun", "ok": r2["all_pass"]})
    print(f"[{'PASS' if r2['all_pass'] else 'FAIL'}] MNN dry-run")

    budget_result = check_budget("", dry_run=True)
    budget_ok = budget_result.file_budget_passed and get_budget_spec()["mnn_size_mb_max"] > 0
    report.append({"check": "budget_dryrun", "ok": budget_ok})
    print(f"[{'PASS' if budget_ok else 'FAIL'}] budget dry-run")

    ort_module_ok = callable(convert_to_ort)
    report.append({"check": "ort_module", "ok": ort_module_ok})
    print(f"[{'PASS' if ort_module_ok else 'FAIL'}] ORT module import")

    manifest = create_manifest(
        "dry_run",
        "dummy",
        "dummy",
        "dummy",
        "test",
        {},
        0.0,
        config={"opset": 17, "quant_bits": 8, "ort_mobile_enabled": True},
    )
    manifest_ok = (
        manifest.get("run_mode") == "dry_run"
        and manifest.get("git_sha") is not None
        and all(field in manifest for field in MANIFEST_REQUIRED_FIELDS)
    )
    report.append({"check": "manifest_structure", "ok": manifest_ok})
    print(f"[{'PASS' if manifest_ok else 'FAIL'}] manifest 구조")

    all_pass = all(item.get("ok", False) for item in report)
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/convert_verify_result.json").write_text(
        json.dumps({"report": report, "all_pass": all_pass}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if all_pass:
        print("CONVERT_VERIFY_OK=1")
    return {"all_pass": all_pass}


def main() -> int:
    argparse.ArgumentParser().parse_args()
    result = verify()
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
