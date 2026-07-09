#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_REF = "origin/main"


def _read(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True)


def _git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def _split_nul_paths(data: bytes) -> set[str]:
    return {path.decode("utf-8", errors="surrogateescape") for path in data.split(b"\0") if path}


def _changed_paths() -> set[str]:
    paths: set[str] = set()
    try:
        base = _git("merge-base", BASE_REF, "HEAD").strip()
        paths.update(_split_nul_paths(_git_bytes("diff", "--name-only", "-z", base, "HEAD")))
    except Exception:
        pass
    for args in (("diff", "--name-only", "-z"), ("diff", "--cached", "--name-only", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
        try:
            paths.update(_split_nul_paths(_git_bytes(*args)))
        except Exception:
            pass
    return paths


def _read_changed_text(path: str) -> str | None:
    candidate = ROOT / path
    try:
        if not candidate.is_file():
            return None
        return candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


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

    forbidden_label_paths = []
    for path in changed:
        text = _read_changed_text(path)
        if text is None or "[근거 확인 필요]" not in text:
            continue
        if not (
            path == "butler_pc_core/cards/box3/actual_operation_pipeline.py"
            or path.startswith("butler-desktop/src/")
            or path.startswith("tests/")
            or path == "scripts/verify_box3_unsupported_claim_labeling.py"
        ):
            forbidden_label_paths.append(path)
    if forbidden_label_paths:
        errors.append("B3_LABEL_STRING_OUTSIDE_RUNTIME_UI")

    print(f"BOX3_UNSUPPORTED_LABELING_VERIFY_OK={0 if errors else 1}")
    print(f"BOX3_UNSUPPORTED_LABELING_VERIFY_FAILED={1 if errors else 0}")
    for code in errors:
        print(f"ERROR_CODE={code}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
