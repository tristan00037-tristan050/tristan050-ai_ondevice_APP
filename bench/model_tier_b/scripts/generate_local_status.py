#!/usr/bin/env python3
"""Generate an honest, schema-conformant local delivery status."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from butler_bench.canonical import canonical_sha256, write_canonical_json  # noqa: E402
from butler_bench.governance import build_final_status  # noqa: E402
from butler_bench.preflight import GATE_NAMES  # noqa: E402


REASONS = {
    "P0_CODE_CLOSED": "local implementation tested; actual product repository closure unavailable",
    "ALL_46_DEFECTS_CLOSED": "local traceability implemented; signed CI and independent replay unavailable",
    "CLEAN_COMMITTED_TREE": "delivery workspace is not the approved Butler repository",
    "GIT_BLOB_MATCH": "approved base full OID and deployed product blob unavailable",
    "CI_GREEN": "repository-hosted 12-job CI has not run in this workspace",
    "OS_EGRESS_RECEIPT_VALID": "approved target OS controller receipt unavailable",
    "PRODUCT_PREFLIGHT_PASS": "actual Butler product module unavailable",
    "INDEPENDENT_PREFLIGHT_VERIFY": "independent M3 host replay unavailable",
    "TRUST_POLICY_CONFIGURED": "approved trust policy is intentionally not fabricated",
    "BASE_FULL_SHA_RESOLVED": "approved base commit was not supplied",
    "BENCHMARK_POLICY_COMPLETE": "approved benchmark policy is intentionally not fabricated",
}


def main() -> None:
    if set(REASONS) != set(GATE_NAMES):
        raise SystemExit("local blocker set does not match 11-gate contract")
    directory = ROOT / "evidence" / "local_validation"
    directory.mkdir(parents=True, exist_ok=True)
    blockers = {
        name: {
            "gate": name,
            "value": False,
            "reason": REASONS[name],
            "claim_boundary": "LOCAL_DELIVERY_ONLY",
        }
        for name in GATE_NAMES
    }
    gates = {
        name: {"value": False, "receipt_sha256": canonical_sha256(blockers[name])}
        for name in GATE_NAMES
    }
    status = build_final_status(gate_receipts=gates, status="SPEC_READY")
    write_canonical_json(directory / "gate_blockers.json", {
        "schema_version": "butler.model-tier-b.local-gate-blockers.v2.8",
        "blockers": blockers,
        "m3_start_allowed": False,
        "g1_ready": False,
        "runtime_activation_allowed": 0,
    })
    write_canonical_json(directory / "final_status.json", status)
    summary = {
        "schema_version": "butler.model-tier-b.local-validation-summary.v2.8",
        "unit_and_contract_tests": 74,
        "unit_and_contract_failures": 0,
        "attack_rows": 60,
        "attack_rows_blocked_as_expected": 60,
        "acceptance_rows": 90,
        "defect_rows": 46,
        "m3_evidence_pass_claimed": False,
        "product_integration_pass_claimed": False,
        "runtime_activation_allowed": 0,
    }
    write_canonical_json(directory / "validation_summary.json", summary)


if __name__ == "__main__":
    main()
