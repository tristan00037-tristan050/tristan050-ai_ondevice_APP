#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_REF = "origin/main"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True)


def _changed_paths() -> set[str]:
    paths: set[str] = set()
    try:
        base = _git("merge-base", BASE_REF, "HEAD").strip()
        paths.update(line.strip() for line in _git("diff", "--name-only", base, "HEAD").splitlines() if line.strip())
    except Exception:
        pass
    for args in (("diff", "--name-only"), ("diff", "--cached", "--name-only"), ("ls-files", "--others", "--exclude-standard")):
        try:
            paths.update(line.strip() for line in _git(*args).splitlines() if line.strip())
        except Exception:
            pass
    return paths


def main() -> int:
    errors: list[str] = []
    changed = _changed_paths()

    actual_fail = _read("butler_pc_core/cards/box3/actual_fail_class.py")
    grounding = _read("butler_pc_core/cards/box3/real_grounding.py")
    prompt = _read("butler_pc_core/cards/box3/grounded_prompt.py")
    pipeline = _read("butler_pc_core/cards/box3/actual_operation_pipeline.py")
    endpoint = _read("butler_pc_core/cards/box3/endpoint_wiring.py")

    if 'NEEDS_REVIEW_UNSUPPORTED_CLAIM = "NEEDS_REVIEW_UNSUPPORTED_CLAIM"' not in actual_fail:
        errors.append("B3_LABEL_ENUM_MISSING")
    if '"BLOCK_UNSUPPORTED_CLAIM"' not in actual_fail:
        errors.append("B3_LEGACY_ENUM_REMOVED")
    if "FAIL_CLASS_SEVERITY" not in actual_fail or "is_blocking_actual_fail_class" not in actual_fail:
        errors.append("B3_SEVERITY_HELPER_MISSING")
    if 'fail_class = "NEEDS_REVIEW_UNSUPPORTED_CLAIM"' not in grounding:
        errors.append("B3_GROUNDING_ISSUANCE_NOT_DEMOTED")
    if 'UsefulnessGateResult("PARTIAL", "NEEDS_REVIEW_UNSUPPORTED_CLAIM"' not in prompt:
        errors.append("B3_USEFULNESS_ISSUANCE_NOT_DEMOTED")
    if "is_blocking_actual_fail_class" not in pipeline:
        errors.append("B3_PIPELINE_SEVERITY_HELPER_UNUSED")
    if "annotate_unsupported_lines" not in pipeline or "[근거 확인 필요]" not in pipeline:
        errors.append("B3_RUNTIME_LABELING_MISSING")
    if "scan_runtime_security_risk" not in pipeline or "BLOCK_DLP_OUTBOUND_DRAFT" not in pipeline:
        errors.append("B3_DLP_PRE_OUTPUT_GUARD_MISSING")
    if "unsupported_claim_count" not in endpoint or "label_coverage_ok" not in endpoint:
        errors.append("B3_ENDPOINT_LABEL_CONTRACT_MISSING")

    sdk_changes = [path for path in changed if path.startswith("butler_pc_core/cards/box3/sdk/")]
    if sdk_changes:
        errors.append("B3_SDK_DIFF_NOT_ZERO")

    sealed_eval_paths = {
        "butler_pc_core/cards/box3/real_pipeline_enablement.py",
        "butler_pc_core/cards/box3/real_pipeline.py",
        "butler_pc_core/cards/box3/final_gate.py",
        "butler_pc_core/cards/box3/real_eval.py",
        "butler_pc_core/cards/box3/real_metrics.py",
    }
    if changed & sealed_eval_paths:
        errors.append("B3_EVAL_PATH_DIFF_NOT_ZERO")

    forbidden_label_paths = [
        path for path in changed
        if "[근거 확인 필요]" in (ROOT / path).read_text(encoding="utf-8", errors="ignore")
        and not (
            path == "butler_pc_core/cards/box3/actual_operation_pipeline.py"
            or path.startswith("butler-desktop/src/")
            or path.startswith("tests/")
            or path == "scripts/verify_box3_unsupported_claim_labeling.py"
        )
    ]
    if forbidden_label_paths:
        errors.append("B3_LABEL_STRING_OUTSIDE_RUNTIME_UI")

    print(f"BOX3_UNSUPPORTED_LABELING_VERIFY_OK={0 if errors else 1}")
    print(f"BOX3_UNSUPPORTED_LABELING_ERROR_COUNT={len(errors)}")
    for code in errors:
        print(f"ERROR_CODE={code}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
