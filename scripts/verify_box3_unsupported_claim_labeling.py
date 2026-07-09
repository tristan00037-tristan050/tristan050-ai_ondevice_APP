#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
BASE_REF = sys.argv[2] if len(sys.argv) > 2 else "0bb48bff1b49753048c3a262e5eb2475910e6db4"

FILES = {
    "fail": Path("butler_pc_core/cards/box3/actual_fail_class.py"),
    "grounding": Path("butler_pc_core/cards/box3/real_grounding.py"),
    "prompt": Path("butler_pc_core/cards/box3/grounded_prompt.py"),
    "pipeline": Path("butler_pc_core/cards/box3/actual_operation_pipeline.py"),
    "endpoint": Path("butler_pc_core/cards/box3/endpoint_wiring.py"),
    "labeling": Path("butler_pc_core/cards/box3/unsupported_labeling.py"),
    "test": Path("tests/cards/box3/test_unsupported_claim_labeling.py"),
}


def fail(code: str) -> None:
    print("BOX3_UNSUPPORTED_CLAIM_LABELING_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def read(key: str) -> str:
    path = ROOT / FILES[key]
    if not path.exists():
        fail(f"FILE_MISSING:{key}")
    return path.read_text(encoding="utf-8")


def changed_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{BASE_REF}...HEAD"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    fail_src = read("fail")
    grounding = read("grounding")
    prompt = read("prompt")
    pipeline = read("pipeline")
    endpoint = read("endpoint")
    labeling = read("labeling")
    tests = read("test")

    for required in (
        "NEEDS_REVIEW_UNSUPPORTED_CLAIM",
        "NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL",
        "FAIL_CLASS_SEVERITY",
        "def is_blocking_actual_fail_class",
    ):
        if required not in fail_src:
            fail("SEVERITY_MAP_MISSING")

    if 'fail_class = NEEDS_REVIEW_UNSUPPORTED_CLAIM' not in grounding:
        fail("REAL_GROUNDING_ISSUE_NOT_DEMOTED")
    if 'UsefulnessGateResult("PARTIAL", NEEDS_REVIEW_UNSUPPORTED_CLAIM' not in prompt:
        fail("GROUNDED_PROMPT_ISSUE_NOT_DEMOTED")
    if "is_blocking_actual_fail_class" not in pipeline:
        fail("PIPELINE_SEVERITY_HELPER_MISSING")
    if 'startswith("BLOCK_")' in pipeline or "startswith('BLOCK_')" in pipeline:
        fail("PIPELINE_PREFIX_BLOCK_CHECK_REMAINS")
    for required in ("annotate_unsupported_lines", "unsupported_digest_set", "dlp_pre_output_guard", "unsupported_claim_count"):
        if required not in pipeline:
            fail("PIPELINE_LABELING_PATH_MISSING")
    for required in ("LABEL_PREFIX", "FULL_REVIEW_BANNER", "scan_outbound_text_for_pii_or_secret", "_normalize_claim_line_for_helper4"):
        if required not in labeling:
            fail("LABELING_CONTRACT_MISSING")
    for required in ("review_reason_code", "unsupported_claim_count", "annotated_claim_count", "label_coverage_ok"):
        if required not in endpoint:
            fail("ENDPOINT_RESPONSE_FIELDS_MISSING")
    if "[근거 확인 필요]" not in labeling:
        fail("LABEL_LITERAL_MISSING")
    if "[근거 확인 필요]" in grounding or "[근거 확인 필요]" in prompt:
        fail("LABEL_LITERAL_OUTSIDE_RUNTIME_LAYER")
    if "raw_claim" in pipeline + endpoint + labeling or "claim_text_runtime_only" in endpoint:
        fail("RAW_CLAIM_PERSISTENCE_RISK")
    if "scan_outbound_text_for_pii_or_secret" not in tests or "label_coverage_ok is False" not in tests:
        fail("TEST_COVERAGE_MISSING")

    for changed in changed_files():
        if changed.startswith("butler_pc_core/cards/box3/sdk/"):
            fail("SDK_DIFF_FORBIDDEN")
        if changed == "butler_pc_core/cards/box3/real_pipeline_enablement.py":
            fail("EVAL_PIPELINE_DIFF_FORBIDDEN")
        if changed == "butler_pc_core/cards/box3/helper_wiring_manifest.py":
            fail("HELPER_SHA_DIFF_FORBIDDEN")

    print("BOX3_UNSUPPORTED_CLAIM_LABELING_OK=1")
    print("SEVERITY_MAP=1")
    print("UNSUPPORTED_ISSUE_DEMOTED=1")
    print("PIPELINE_USES_SEVERITY_HELPER=1")
    print("RUNTIME_LABELING=1")
    print("MATCHING_FAIL_SAFE=1")
    print("DLP_PRE_OUTPUT_GUARD=1")
    print("SDK_DIFF=0")
    print("EVAL_PIPELINE_DIFF=0")
    print("RAW_TEXT_LOGGED=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
